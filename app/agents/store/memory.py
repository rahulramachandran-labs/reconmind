"""The run store without a database: tests, and local runs with no DATABASE_URL."""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.agents.schemas import (
    STATUS_AFTER_REVIEW,
    WRITE_UP_FIELDS,
    IncidentReport,
    fingerprint,
)


class MemoryRunStore:
    """Same surface, no database. Used by tests and when DATABASE_URL is unset."""

    def __init__(self) -> None:
        self.runs: dict[uuid.UUID, dict[str, Any]] = {}
        self.reports: dict[uuid.UUID, dict[str, Any]] = {}
        self.ledger: list[dict[str, Any]] = []

    def create_run(
        self,
        run_id: uuid.UUID,
        trigger: str,
        question: str | None,
        adapter: str,
        trace_id: str,
        session_id: uuid.UUID | None = None,
    ) -> None:
        self.runs[run_id] = {
            "id": str(run_id),
            "trigger": trigger,
            "question": question,
            "adapter": adapter,
            "status": "running",
            "plan": {},
            "summary": None,
            "error": None,
            "trace_url": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
            "latency_ms": 0,
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": None,
            "llm_calls": 0,
        }

    def save_plan(self, run_id: uuid.UUID, plan: dict[str, Any]) -> None:
        self.runs.setdefault(run_id, {})["plan"] = plan

    def save_reports(
        self, run_id: uuid.UUID, reports: list[IncidentReport]
    ) -> list[IncidentReport]:
        out = []
        for r in reports:
            existing = next(
                (
                    x
                    for x in self.reports.values()
                    if fingerprint(x["finding_type"], x["title"]) == r.fingerprint
                ),
                None,
            )
            if existing is not None:
                existing["seen_count"] = existing.get("seen_count", 1) + 1
                if r.model_analysis and not existing.get("model_analysis"):
                    existing.update(r.model_dump(mode="json", include=WRITE_UP_FIELDS))
                self.ledger.append({"action": "finding.seen_again", "subject": existing["id"]})
                out.append(
                    IncidentReport(
                        **{k: v for k, v in existing.items() if k in IncidentReport.model_fields}
                    ).model_copy(update={"repeat": True})
                )
                continue
            self.reports[r.id] = r.model_dump(mode="json") | {"review_decision": None}
            self.ledger.append({"action": "finding.created", "subject": str(r.id)})
            out.append(r)
        return out

    def reopen(self, report_id: uuid.UUID, note: str | None, actor: str) -> dict[str, Any] | None:
        r = self.reports.get(report_id)
        if r is None or r["status"] == "pending_review":
            return None
        self.ledger.append({"action": "finding.reopened", "subject": str(report_id), "by": actor})
        r.update(status="pending_review", review_decision=None, review_note=None)
        return r

    def known_report(self, fp: str) -> dict[str, Any] | None:
        return next(
            (x for x in self.reports.values() if fingerprint(x["finding_type"], x["title"]) == fp),
            None,
        )

    def record_decision(
        self, report_id: uuid.UUID, decision: str, note: str | None, reviewer: str
    ) -> uuid.UUID | None:
        r = self.reports.get(report_id)
        if r is None or r["status"] != "pending_review":
            return None
        r.update(review_decision=decision, review_note=note, reviewed_by=reviewer)
        return uuid.UUID(r["run_id"])

    def pending_decisions(self, run_id: uuid.UUID) -> tuple[dict[str, dict[str, Any]], int]:
        pending = [
            r
            for r in self.reports.values()
            if r["run_id"] == str(run_id) and r["status"] == "pending_review"
        ]
        decided = {
            r["id"]: {
                "decision": r["review_decision"],
                "note": r.get("review_note"),
                "reviewer": r.get("reviewed_by"),
            }
            for r in pending
            if r["review_decision"]
        }
        return decided, len(pending) - len(decided)

    def apply_decisions(
        self, run_id: uuid.UUID, decisions: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        out = []
        for rid, d in decisions.items():
            r = self.reports.get(uuid.UUID(rid))
            if r is None:
                continue
            r.update(
                status=STATUS_AFTER_REVIEW[d["decision"]],
                review_decision=d["decision"],
                review_note=d.get("note"),
            )
            self.ledger.append({"action": f"review.{d['decision']}", "subject": rid})
            out.append({"id": rid, "status": r["status"], "decision": d["decision"]})
        return out

    def update_writeups(
        self, report_id: uuid.UUID, patch: dict[str, Any], actor: str
    ) -> dict[str, Any] | None:
        r = self.reports.get(report_id)
        if r is None:
            return None
        r.update(patch)
        self.ledger.append({"action": "finding.rewritten", "subject": str(report_id), "by": actor})
        return r

    def mark(self, run_id: uuid.UUID, status: str) -> None:
        self.runs[run_id]["status"] = status

    def finish_run(
        self,
        run_id: uuid.UUID,
        status: str,
        summary: str | None,
        totals: dict[str, Any],
        latency_ms: int,
        trace_url: str | None,
        error: str | None = None,
    ) -> None:
        run = self.runs[run_id]
        run.update(status=status, summary=summary, error=error, trace_url=trace_url)
        run["llm_calls"] = run.get("llm_calls", 0) + totals["llm_calls"]
        run["cost_usd"] += totals["cost_usd"]
        run["latency_ms"] = (run["latency_ms"] or 0) + latency_ms

    def get_run_row(self, run_id: uuid.UUID) -> dict[str, Any] | None:
        return self.runs.get(run_id)

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(self.runs.values()))[:limit]

    def get_run(self, run_id: uuid.UUID) -> dict[str, Any] | None:
        run = self.runs.get(run_id)
        if run is None:
            return None
        return run | {
            "steps": [],
            "reports": [r for r in self.reports.values() if r["run_id"] == str(run_id)],
        }

    def list_incidents(
        self, status: str | None = None, severity: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        out = [
            r
            for r in self.reports.values()
            if (not status or r["status"] == status) and (not severity or r["severity"] == severity)
        ]
        return out[:limit]

    def get_incident(self, report_id: uuid.UUID) -> dict[str, Any] | None:
        return self.reports.get(report_id)

    def paused_plan_runs(self) -> list[dict[str, Any]]:
        return [r for r in self.runs.values() if r["status"] == "paused_plan"]

    def usage_on(self, day: Any) -> dict[str, Any]:
        runs = list(self.runs.values())
        return {
            "day": str(day),
            "runs": len(runs),
            "llm_calls": sum(r.get("llm_calls", 0) for r in runs),
            "tokens": 0,
            "cost_usd": round(sum(r.get("cost_usd", 0.0) for r in runs), 6),
            "providers": [],
            "last_scan": next((r for r in reversed(runs) if r["trigger"] == "scan"), None),
        }

    def open_findings(self) -> dict[str, Any]:
        live = [r for r in self.reports.values() if r["status"] != "rejected"]
        by = {sev: sum(1 for r in live if r["severity"] == sev) for sev in ("S1", "S2", "S3", "S4")}
        return {
            "since": None,
            "by_severity": by,
            "pending_review": sum(1 for r in live if r["status"] == "pending_review"),
            "items": [{k: r[k] for k in ("id", "severity", "title", "status")} for r in live],
        }
