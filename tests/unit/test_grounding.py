from app.agents.specialists import ungrounded
from app.domain.protocol import FindingAnalysis

SHOWN = (
    '{"title": "LOC-0517 also reporting as OUT-1071 (3.0% of rows)", "rows_in_window": 8,373, '
    '"winning_file": "S1002_20260612_1120_ECOMM.txt", "minutes_after_sla": 161} '
    "<passage>INC-0438: MOBILE file renamed a dedup-key column</passage>"
)


def analysis(text: str, *fix: str) -> FindingAnalysis:
    return FindingAnalysis(
        root_cause_hypothesis=text, recommended_fix=list(fix), confidence=0.6, open_questions=[]
    )


def test_numbers_times_and_ids_from_the_facts_or_passages_pass() -> None:
    ok = analysis(
        "OUT-1071 looks like a transposition, as in INC-0438: 3.0% of 8,373 rows, "
        "161 minutes late, resent at 11:20.",
        "Rebuild for the affected dates.",
    )
    assert ungrounded(ok, SHOWN) is None


def test_invented_details_are_named_back_to_the_model() -> None:
    bad = analysis("The resend at 12:20 hit a 5400 s sensor timeout.", "Alias OUT-9999.")
    problem = ungrounded(bad, SHOWN)
    assert problem is not None
    assert "12:20" in problem and "5400" in problem and "OUT-9999" in problem
    assert "11:20" not in problem


def test_small_counts_and_severities_are_not_claims() -> None:
    assert ungrounded(analysis("Two of 4 submitters; an S1 for 3 rows.", "Resend."), SHOWN) is None
