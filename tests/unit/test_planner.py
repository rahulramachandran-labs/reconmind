import pytest

from app.agents.planner import heuristic_plan
from app.domain.retail_recon import RetailReconAdapter

A = RetailReconAdapter()


@pytest.mark.parametrize(
    ("question", "intent", "specialists"),
    [
        ("which file wins when a submitter resends the same day?", "answer", []),
        ("How do I tell a renamed column from a dropped one?", "answer", []),
        ("are there any duplicate submissions this week?", "investigate", ["reconciliation"]),
        (
            "did the MOBILE file have a schema problem on 2026-06-16?",
            "investigate",
            ["data_quality"],
        ),
        ("anything wrong with the pipeline?", "investigate", ["reconciliation", "data_quality"]),
        ("show me what happened on 2026-06-18", "investigate", ["reconciliation", "data_quality"]),
        ("explain the severity rubric", "answer", []),
        ("penguins", "unclear", []),
    ],
)
def test_heuristic_routes(question: str, intent: str, specialists: list[str]) -> None:
    d = heuristic_plan(A, "question", question)
    assert d.intent == intent
    assert d.specialists == specialists


def test_scan_uses_every_specialist_with_full_confidence() -> None:
    d = heuristic_plan(A, "scan", None)
    assert d.specialists == ["reconciliation", "data_quality"] and d.confidence == 1.0


def test_unclear_questions_fall_below_the_review_threshold() -> None:
    assert heuristic_plan(A, "question", "penguins").confidence < 0.5


def test_a_template_cites_only_a_matching_past_incident() -> None:
    from app.domain.protocol import Finding
    from app.retrieval.types import RetrievedChunk

    def incident(title: str) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=title,
            doc_id=title,
            title=title,
            path="",
            section="Problem",
            doc_type="incident",
            text="",
            score=1.0,
            rank=1,
        )

    resend = Finding(
        finding_type="duplicate_submission",
        specialist="reconciliation",
        subject="f",
        title="Resent file",
        affected_records=88,
        metrics={
            "changed_rows": 3,
            "landed_after_dag_run": True,
            "business_date": "d",
            "submitter_id": "S1002",
        },
    )
    unrelated = [incident("INC-0438: MOBILE file renamed a dedup-key column")]
    matching = [*unrelated, incident("INC-0427: ECOMM resend double counted web revenue")]
    assert "INC-0438" not in A.fallback_analysis(resend, unrelated).root_cause_hypothesis
    assert "INC-0427" in A.fallback_analysis(resend, matching).root_cause_hypothesis
