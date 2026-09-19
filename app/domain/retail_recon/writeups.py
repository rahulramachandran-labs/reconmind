"""The retail severity rubric and the wording of incident write-ups.

``fallback_analysis`` is the template the specialists use when no model is
available; with a model, it is the calibrated prior the model's answer is
capped against.
"""

from app.domain.protocol import Finding, FindingAnalysis, Severity
from app.domain.retail_recon.rules import KEY_DRIFT_S2_RATE, VOLUME_DROP, VOLUME_DROP_S1
from app.retrieval.types import RetrievedChunk


def severity(finding: Finding) -> Severity:
    m = finding.metrics
    if finding.finding_type == "key_drift":
        return "S2" if (finding.affected_rate or 0) > KEY_DRIFT_S2_RATE else "S3"
    if finding.finding_type == "duplicate_submission":
        return "S2" if m.get("landed_after_dag_run") else "S3"
    if finding.finding_type == "schema_drift":
        if m.get("change") == "add":
            return "S4"
        return "S1" if m.get("dedup_key_affected") else "S2"
    if finding.finding_type == "volume_anomaly":
        change = m.get("pct_change", 0)
        if change <= -VOLUME_DROP_S1:
            return "S1"
        return "S2" if change <= -VOLUME_DROP else "S3"
    return "S3"


def problem_statement(finding: Finding) -> str:
    m = finding.metrics
    if finding.finding_type == "key_drift":
        return (
            f"Location {m['location_id']} is reporting sales under two outlet ids: its "
            f"canonical {m['canonical_outlet_id']} and {m['reported_outlet_id']}, which "
            f"outlet_location_map does not map to it. {m['rows']} of {m['rows_in_window']} "
            f"deduplicated rows ({finding.affected_rate:.1%}) between {m['first_seen']} and "
            f"{m['last_seen']} are affected, so store-level numbers for this location "
            "are split."
        )
    if finding.finding_type == "duplicate_submission":
        when = "after" if m["landed_after_dag_run"] else "before"
        return (
            f"{m['submitter_id']} resent its {m['business_date']} file. "
            f"{m['winning_file']} repeats {m['duplicate_keys']} dedup keys from "
            f"{m['superseded_file']}, and {m['changed_rows']} of them carry a different qty or "
            f"amount. The resend landed {when} that night's DAG run, so the superseded rows "
            f"{'reached' if m['landed_after_dag_run'] else 'did not reach'} fct_daily_sales."
        )
    if finding.finding_type == "schema_drift":
        return (
            f"{m['file']} ({m['business_date']}) does not match the raw.transactions contract: "
            f"missing {m['missing_columns']}, unexpected {m['unexpected_columns']}. "
            f"{finding.affected_records} rows landed with the missing column null"
            + (
                "; that column is part of the dedup key, so dedup cannot run for this batch."
                if m["dedup_key_affected"]
                else "."
            )
        )
    if finding.finding_type == "volume_anomaly":
        late = m.get("minutes_after_sla")
        return (
            f"{m['submitter_id']}'s {m['business_date']} file {m['file']} has "
            f"{m['rows']} rows, "
            f"{abs(m['pct_change']):.0%} {'below' if m['pct_change'] < 0 else 'above'} its "
            f"trailing 7-day average of {m['trailing_avg_7d']}"
            + (
                f", and it landed {late} minutes after the submitter SLA."
                if late and late > 0
                else "."
            )
        )
    return finding.title


def retrieval_query(finding: Finding) -> str:
    m = finding.metrics
    return {
        "key_drift": "location reporting under two outlet ids key drift fix outlet_alias",
        "duplicate_submission": "resend duplicate submission latest file wins dedupe reprocess",
        "schema_drift": (
            f"renamed column {' '.join(m.get('missing_columns', []))} "
            f"{' '.join(m.get('unexpected_columns', []))} ContractViolation validate_schema"
        ),
        "volume_anomaly": "volume drop below trailing average late truncated file",
    }.get(finding.finding_type, finding.title)


def fallback_analysis(finding: Finding, sources: list[RetrievedChunk]) -> FindingAnalysis:
    m = finding.metrics
    precedent = next((s.title.split(":")[0] for s in sources if s.doc_type == "incident"), None)
    like = f" This matches the pattern in {precedent}." if precedent else ""
    if finding.finding_type == "key_drift":
        return FindingAnalysis(
            root_cause_hypothesis=(
                f"Whole baskets ({m['baskets']}) from {m['submitters']} submitter(s) carry "
                f"{m['reported_outlet_id']}, so the id is set at the register or export "
                f"profile rather than corrupted row by row; {m['reported_outlet_id']} looks "
                f"like a transposition of {m['canonical_outlet_id']}.{like}"
            ),
            recommended_fix=[
                "Confirm the correct outlet id with the submitter before changing anything.",
                f"Add {m['reported_outlet_id']} -> {m['canonical_outlet_id']} to outlet_alias "
                f"for {m['first_seen']} to {m['last_seen']}; never edit raw rows.",
                "Rebuild stg_transactions and fct_daily_sales for the affected dates.",
                "Ask the submitter to fix the export profile at source and record the ticket.",
            ],
            confidence=0.6,
            open_questions=[
                "Which registers or export profiles carry the wrong id?",
                f"Did the drift start on {m['first_seen']} or earlier than the scan window?",
            ],
        )
    if finding.finding_type == "duplicate_submission":
        corrected = m["changed_rows"] > 0
        return FindingAnalysis(
            root_cause_hypothesis=(
                (
                    f"A deliberate correction: {m['changed_rows']} rows changed qty or amount, "
                    "so the later file is the one to trust. "
                    if corrected
                    else "An accidental re-export: no values changed. "
                )
                + (
                    "It landed after dedupe_transactions had run, so nothing removed the older "
                    "copies before publish."
                    if m["landed_after_dag_run"]
                    else "Dedupe ran after it landed, so published numbers are correct."
                )
                + like
            ),
            recommended_fix=[
                f"Reprocess {m['business_date']} with reprocess=true so dedupe_transactions "
                "runs again and the latest file wins.",
                "Check publish_metrics against the resend's trailer count.",
                "Tell finance how many rows changed value, not just how many were duplicated.",
            ],
            confidence=0.75 if corrected else 0.6,
            open_questions=[f"Why did {m['submitter_id']} resend: correction or re-run?"],
        )
    if finding.finding_type == "schema_drift":
        rename = m["renames"][0] if m["renames"] else None
        return FindingAnalysis(
            root_cause_hypothesis=(
                (
                    f"The submitter's export renamed {rename[0]} to {rename[1]}: one "
                    "contracted column is missing and one similarly named column appeared "
                    "in the same batch. "
                    if rename
                    else "The export changed its header against the contract. "
                )
                + "The loader maps by name, so the rows landed with the column null."
                + like
            ),
            recommended_fix=[
                "Do not change the contract to match the file.",
                f"Ask {m['submitter_id']} to resend {m['business_date']} with the "
                "contracted header.",
                "Reprocess the day once the resend lands; latest-file-wins supersedes the "
                "null-key rows.",
            ],
            confidence=0.8 if rename else 0.6,
            open_questions=["Did the submitter ship a new export library or config?"],
        )
    if finding.finding_type == "volume_anomaly":
        late = (m.get("minutes_after_sla") or 0) > 0
        return FindingAnalysis(
            root_cause_hypothesis=(
                (
                    "A late and light file together is the signature of a truncated upstream "
                    "export: the transfer shipped whatever was there once its retry window "
                    "ran out."
                    if late and m["pct_change"] < 0
                    else "Volume moved outside its normal band without a timing signal."
                )
                + like
            ),
            recommended_fix=[
                "Check whether the drop is spread across all outlets (truncation) or a few "
                "(stores offline).",
                "Compare the loaded row count with the file trailer.",
                f"If truncated, request a full resend from {m['submitter_id']} and "
                f"reprocess {m['business_date']}.",
            ],
            confidence=0.65 if late else 0.45,
            open_questions=[
                "Was it a known low day (holiday, planned closures)?",
                "Is the drop spread evenly across outlets?",
            ],
        )
    return FindingAnalysis(
        root_cause_hypothesis="No template for this finding type; needs a human look.",
        recommended_fix=["Review the evidence attached to the finding."],
        confidence=0.3,
    )
