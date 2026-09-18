import pytest

from app.agents.nodes import heuristic_plan
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
