"""Where runs, reports and review decisions are kept."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, cast, func, select, update
from sqlalchemy.types import Date

from app.agents.schemas import IncidentReport, fingerprint
from app.db.models import AgentRun, AgentStep, AuditLedger
from app.db.models import IncidentReport as ReportRow
from app.db.session import session_scope

STATUS_FOR = {"approve": "published", "annotate": "published", "reject": "rejected"}


def _row_to_run(r: AgentRun, **extra: Any) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "trigger": r.trigger,
        "question": r.question,
        "adapter": r.adapter,
        "status": r.status,
        "plan": r.plan,
        "summary": r.summary,
        "error": r.error,
        "trace_url": r.trace_url,
        "prompt_tokens": r.prompt_tokens,
        "completion_tokens": r.completion_tokens,
        "cost_usd": float(r.cost_usd or 0),
        "latency_ms": r.latency_ms,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        **extra,
    }


def _row_to_report(r: ReportRow) -> dict[str, Any]:
    return r.report | {
        "status": r.status,
        "seen_count": r.seen_count,
        "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None,
        "review_decision": r.review_decision,
        "review_note": r.review_note,
        "reviewed_by": r.reviewed_by,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


class SqlRunStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # writes used by the graph ------------------------------------------------

    def create_run(
        self,
        run_id: uuid.UUID,
        trigger: str,
        question: str | None,
        adapter: str,
        trace_id: str,
        session_id: uuid.UUID | None = None,
    ) -> None:
        with session_scope(self.engine) as s:
            s.add(
                AgentRun(
                    id=run_id,
                    trigger=trigger,
                    question=question,
                    adapter=adapter,
                    session_id=session_id,
                    status="running",
                    trace_id=trace_id,
                )
            )

    def save_plan(self, run_id: uuid.UUID, plan: dict[str, Any]) -> None:
        with session_scope(self.engine) as s:
            s.execute(update(AgentRun).where(AgentRun.id == run_id).values(plan=plan))

    def save_reports(
        self, run_id: uuid.UUID, reports: list[IncidentReport]
    ) -> list[IncidentReport]:
        """Store new findings; a finding an earlier scan already reported is counted
        as seen again instead. Returns what was recorded, repeats marked."""
        out = []
        now = datetime.now(UTC)
        with session_scope(self.engine) as s:
            for r in reports:
                fp = r.fingerprint
                existing = s.scalars(
                    select(ReportRow)
                    .where(ReportRow.fingerprint == fp)
                    .order_by(ReportRow.created_at.desc())
                    .limit(1)
                ).first()
                if existing is not None:
                    existing.seen_count = (existing.seen_count or 1) + 1
                    existing.last_seen_at = now
                    s.add(
                        AuditLedger(
                            actor=f"agent:{r.specialist}",
                            action="finding.seen_again",
                            subject=str(existing.id),
                            payload={"run_id": str(run_id), "seen_count": existing.seen_count},
                        )
                    )
                    out.append(
                        IncidentReport(**existing.report).model_copy(
                            update={
                                "status": existing.status,
                                "seen_count": existing.seen_count,
                                "repeat": True,
                            }
                        )
                    )
                    continue
                s.add(
                    ReportRow(
                        id=r.id,
                        run_id=run_id,
                        finding_type=r.finding_type,
                        severity=r.severity,
                        title=r.title,
                        status=r.status,
                        report=r.model_dump(mode="json"),
                        fingerprint=fp,
                        seen_count=1,
                        last_seen_at=now,
                    )
                )
                s.add(
                    AuditLedger(
                        actor=f"agent:{r.specialist}",
                        action="finding.created",
                        subject=str(r.id),
                        payload={
                            "run_id": str(run_id),
                            "severity": r.severity,
                            "finding_type": r.finding_type,
                            "status": r.status,
                        },
                    )
                )
                out.append(r)
        return out

    def record_decision(
        self, report_id: uuid.UUID, decision: str, note: str | None, reviewer: str
    ) -> uuid.UUID | None:
        """Store a reviewer's call. Returns the run id, or None if nothing is pending."""
        with session_scope(self.engine) as s:
            row = s.get(ReportRow, report_id)
            if row is None or row.status != "pending_review":
                return None
            row.review_decision, row.review_note = decision, note
            row.reviewed_by, row.reviewed_at = reviewer, datetime.now(UTC)
            return row.run_id

    def pending_decisions(self, run_id: uuid.UUID) -> tuple[dict[str, dict[str, Any]], int]:
        with session_scope(self.engine) as s:
            rows = s.scalars(
                select(ReportRow).where(
                    ReportRow.run_id == run_id, ReportRow.status == "pending_review"
                )
            ).all()
            decided = {
                str(r.id): {
                    "decision": r.review_decision,
                    "note": r.review_note,
                    "reviewer": r.reviewed_by,
                }
                for r in rows
                if r.review_decision
            }
            return decided, len(rows) - len(decided)

    def apply_decisions(
        self, run_id: uuid.UUID, decisions: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        out = []
        with session_scope(self.engine) as s:
            for report_id, d in decisions.items():
                row = s.get(ReportRow, uuid.UUID(report_id))
                if row is None or row.run_id != run_id:
                    continue
                row.status = STATUS_FOR[d["decision"]]
                row.review_decision, row.review_note = d["decision"], d.get("note")
                row.reviewed_by = d.get("reviewer") or row.reviewed_by
                row.reviewed_at = row.reviewed_at or datetime.now(UTC)
                s.add(
                    AuditLedger(
                        actor=f"human:{row.reviewed_by or 'reviewer'}",
                        action=(
                            f"review.{d['decision']}d"
                            if d["decision"] != "annotate"
                            else "review.annotated"
                        ),
                        subject=report_id,
                        payload={
                            "run_id": str(run_id),
                            "note": d.get("note"),
                            "status": row.status,
                        },
                    )
                )
                out.append({"id": report_id, "status": row.status, "decision": d["decision"]})
        return out

    def mark(self, run_id: uuid.UUID, status: str) -> None:
        with session_scope(self.engine) as s:
            s.execute(update(AgentRun).where(AgentRun.id == run_id).values(status=status))

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
        with session_scope(self.engine) as s:
            run = s.get(AgentRun, run_id)
            if run is None:
                return
            run.status, run.summary, run.error = status, summary, error
            run.trace_url = trace_url or run.trace_url
            run.prompt_tokens = (run.prompt_tokens or 0) + totals["prompt_tokens"]
            run.completion_tokens = (run.completion_tokens or 0) + totals["completion_tokens"]
            run.cost_usd = Decimal(str(float(run.cost_usd or 0) + totals["cost_usd"]))
            run.latency_ms = (run.latency_ms or 0) + latency_ms
            if status != "paused":
                run.finished_at = datetime.now(UTC)

    # reads for the API ---------------------------------------------------------

    def get_run_row(self, run_id: uuid.UUID) -> dict[str, Any] | None:
        with session_scope(self.engine) as s:
            r = s.get(AgentRun, run_id)
            return _row_to_run(r) if r else None

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with session_scope(self.engine) as s:
            counts: dict[uuid.UUID, int] = {
                run_id: n
                for run_id, n in s.execute(
                    select(AgentStep.run_id, func.count())
                    .where(AgentStep.kind == "llm")
                    .group_by(AgentStep.run_id)
                ).all()
            }
            runs = s.scalars(
                select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit)
            ).all()
            return [_row_to_run(r, llm_calls=counts.get(r.id, 0)) for r in runs]

    def get_run(self, run_id: uuid.UUID) -> dict[str, Any] | None:
        with session_scope(self.engine) as s:
            r = s.get(AgentRun, run_id)
            if r is None:
                return None
            steps = s.scalars(
                select(AgentStep).where(AgentStep.run_id == run_id).order_by(AgentStep.id)
            ).all()
            reports = s.scalars(select(ReportRow).where(ReportRow.run_id == run_id)).all()
            return _row_to_run(
                r,
                steps=[
                    {
                        "node": st.node,
                        "kind": st.kind,
                        "name": st.name,
                        "provider": st.provider,
                        "model": st.model,
                        "prompt_version": st.prompt_version,
                        "latency_ms": st.latency_ms,
                        "prompt_tokens": st.prompt_tokens,
                        "completion_tokens": st.completion_tokens,
                        "cost_usd": float(st.cost_usd or 0),
                        "error": st.error,
                        "started_at": st.started_at.isoformat(),
                        "input": st.input,
                        "output": st.output,
                    }
                    for st in steps
                ],
                reports=[_row_to_report(x) for x in reports],
            )

    def list_incidents(
        self, status: str | None = None, severity: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        with session_scope(self.engine) as s:
            q = select(ReportRow).order_by(ReportRow.last_seen_at.desc()).limit(limit)
            if status:
                q = q.where(ReportRow.status == status)
            if severity:
                q = q.where(ReportRow.severity == severity)
            return [_row_to_report(r) for r in s.scalars(q).all()]

    def get_incident(self, report_id: uuid.UUID) -> dict[str, Any] | None:
        with session_scope(self.engine) as s:
            r = s.get(ReportRow, report_id)
            return _row_to_report(r) if r else None

    def usage_on(self, day: Any) -> dict[str, Any]:
        with session_scope(self.engine) as s:
            runs = s.scalar(
                select(func.count())
                .select_from(AgentRun)
                .where(cast(AgentRun.started_at, Date) == day)
            )
            rows = s.execute(
                select(
                    AgentStep.provider,
                    AgentStep.model,
                    func.count(),
                    func.sum(AgentStep.prompt_tokens + AgentStep.completion_tokens),
                    func.sum(AgentStep.cost_usd),
                )
                .where(AgentStep.kind == "llm", cast(AgentStep.started_at, Date) == day)
                .group_by(AgentStep.provider, AgentStep.model)
            ).all()
            last_scan = s.scalars(
                select(AgentRun)
                .where(AgentRun.trigger == "scan")
                .order_by(AgentRun.started_at.desc())
                .limit(1)
            ).first()
        providers = [
            {
                "provider": p or "failed",
                "model": m,
                "calls": n,
                "tokens": int(t or 0),
                "cost_usd": float(c or 0),
            }
            for p, m, n, t, c in rows
        ]
        return {
            "day": str(day),
            "runs": runs or 0,
            "llm_calls": sum(p["calls"] for p in providers),
            "tokens": sum(p["tokens"] for p in providers),
            "cost_usd": round(sum(p["cost_usd"] for p in providers), 6),
            "providers": providers,
            "last_scan": _row_to_run(last_scan) if last_scan else None,
        }

    def open_findings(self) -> dict[str, Any]:
        """What the latest scan saw, minus anything a reviewer rejected."""
        with session_scope(self.engine) as s:
            since = s.scalar(
                select(AgentRun.started_at)
                .where(AgentRun.trigger == "scan", AgentRun.status != "failed")
                .order_by(AgentRun.started_at.desc())
                .limit(1)
            )
            q = select(ReportRow).where(ReportRow.status != "rejected")
            if since is not None:
                q = q.where(ReportRow.last_seen_at >= since)
            rows = s.scalars(q).all()
            pending = s.scalar(
                select(func.count())
                .select_from(ReportRow)
                .where(ReportRow.status == "pending_review")
            )
        by = {sev: 0 for sev in ("S1", "S2", "S3", "S4")}
        for r in rows:
            by[r.severity] += 1
        return {
            "since": since.isoformat() if since else None,
            "by_severity": by,
            "pending_review": pending or 0,
            "items": [
                {
                    "id": str(r.id),
                    "severity": r.severity,
                    "title": r.title,
                    "status": r.status,
                    "seen_count": r.seen_count,
                }
                for r in sorted(rows, key=lambda r: r.severity)
            ],
        }

    def paused_plan_runs(self) -> list[dict[str, Any]]:
        with session_scope(self.engine) as s:
            runs = s.scalars(
                select(AgentRun)
                .where(AgentRun.status == "paused_plan")
                .order_by(AgentRun.started_at.desc())
            ).all()
            return [_row_to_run(r) for r in runs]


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
                status=STATUS_FOR[d["decision"]],
                review_decision=d["decision"],
                review_note=d.get("note"),
            )
            self.ledger.append({"action": f"review.{d['decision']}", "subject": rid})
            out.append({"id": rid, "status": r["status"], "decision": d["decision"]})
        return out

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
