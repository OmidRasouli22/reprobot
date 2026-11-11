from pathlib import Path

import pytest
from pydantic import ValidationError

from reprobot.models import (
    Budget,
    IssueInput,
    ReproResult,
    RunConfig,
    Step,
    ToolCallRecord,
    Verdict,
)


def make_result(**overrides: object) -> ReproResult:
    fields: dict[str, object] = {
        "verdict": Verdict.REPRODUCED,
        "confidence": "high",
        "test_file": "tests/test_dates.py",
        "test_code": "def test_x():\n    assert False\n",
        "test_output": "1 failed",
        "failure_reason": "parse_date accepted Feb 30",
        "suspected_location": "dates/parse.py:12",
        "summary": "The test shows parse_date accepts an invalid date.",
        "attempts": 2,
        "cost_usd": 0.12,
        "duration_s": 95.0,
        "run_id": "run-1",
    }
    fields.update(overrides)
    return ReproResult.model_validate(fields)


# ---------- IssueInput ----------


def test_issue_input_defaults() -> None:
    issue = IssueInput(
        repo_url="https://github.com/o/r", issue_number=7, title="Bug", body="It breaks"
    )
    assert issue.comments == []
    assert issue.commit is None


def test_issue_input_comment_lists_are_not_shared() -> None:
    a = IssueInput(repo_url="r", issue_number=None, title="a", body="")
    b = IssueInput(repo_url="r", issue_number=None, title="b", body="")
    a.comments.append("hi")
    assert b.comments == []


def test_issue_input_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        IssueInput(repo_url="r", issue_number=1, title="t", body="b", labels=["bug"])  # type: ignore[call-arg]


# ---------- RunConfig and Budget ----------


def test_run_config_defaults_match_spec() -> None:
    config = RunConfig(model="anthropic:some-model")
    assert config.budget == Budget(
        max_steps=30, max_tokens=400_000, max_cost_usd=0.50, max_minutes=15
    )
    assert config.tool_output_max_chars == 8_000
    assert config.runs_dir == Path("runs")


def test_run_config_requires_model() -> None:
    with pytest.raises(ValidationError):
        RunConfig()  # type: ignore[call-arg]


@pytest.mark.parametrize("field", ["max_steps", "max_tokens", "max_cost_usd", "max_minutes"])
def test_budget_limits_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError):
        Budget.model_validate({field: 0})


def test_budget_typo_is_an_error() -> None:
    with pytest.raises(ValidationError):
        Budget.model_validate({"max_step": 10})


# ---------- Verdict and ReproResult ----------


def test_verdict_values_are_plain_strings() -> None:
    assert [v.value for v in Verdict] == ["reproduced", "not_reproduced", "setup_failed", "error"]
    assert isinstance(Verdict.REPRODUCED, str)
    assert f"{Verdict.SETUP_FAILED}" == "setup_failed"


def test_repro_result_json_round_trip() -> None:
    result = make_result()
    restored = ReproResult.model_validate_json(result.model_dump_json())
    assert restored == result
    assert '"verdict":"reproduced"' in result.model_dump_json()


def test_repro_result_allows_empty_fields_when_not_reproduced() -> None:
    result = make_result(
        verdict=Verdict.NOT_REPRODUCED,
        confidence=None,
        test_file=None,
        test_code=None,
        test_output=None,
        failure_reason=None,
        suspected_location=None,
    )
    assert result.verdict is Verdict.NOT_REPRODUCED


def test_repro_result_rejects_unknown_confidence() -> None:
    with pytest.raises(ValidationError):
        make_result(confidence="very high")


def test_repro_result_rejects_negative_cost() -> None:
    with pytest.raises(ValidationError):
        make_result(cost_usd=-1)


# ---------- Step ----------


def test_step_json_round_trip_with_tool_calls() -> None:
    step = Step(
        index=0,
        input_tokens=1200,
        output_tokens=80,
        cost_usd=0.004,
        text="Let me look at the parser.",
        tool_calls=[
            ToolCallRecord(
                id="call_1",
                name="read_file",
                arguments={"path": "dates/parse.py", "start_line": 1, "end_line": 40},
                result="1 | def parse_date(s):",
            )
        ],
    )
    restored = Step.model_validate_json(step.model_dump_json())
    assert restored == step
    assert restored.timestamp.tzinfo is not None
