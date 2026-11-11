"""Core data models shared by every part of ReproBot.

These are the shapes of data that cross boundaries: what goes into a run
(`IssueInput`, `RunConfig`), what comes out (`ReproResult`), and what is
recorded along the way (`Step`).
"""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    """Base for all models: unknown fields are an error, not silently ignored."""

    model_config = ConfigDict(extra="forbid")


# ---------- Input ----------


class IssueInput(_Model):
    """A bug report to reproduce."""

    repo_url: str  # https://github.com/owner/repo
    issue_number: int | None
    title: str
    body: str
    comments: list[str] = []
    commit: str | None = None  # default branch head if None


# ---------- Configuration ----------


class Budget(_Model):
    """Hard limits for one run. Hitting any of them ends the run as not_reproduced."""

    max_steps: int = Field(default=30, gt=0)
    max_tokens: int = Field(default=400_000, gt=0)
    max_cost_usd: float = Field(default=0.50, gt=0)
    max_minutes: float = Field(default=15, gt=0)


class RunConfig(_Model):
    """Settings for one run."""

    model: str  # "provider:model", e.g. "anthropic:<model>" or "openai_compat:qwen-coder"
    budget: Budget = Budget()
    tool_output_max_chars: int = Field(default=8_000, gt=0)
    runs_dir: Path = Path("runs")


# ---------- Output ----------


class Verdict(StrEnum):
    """The final outcome of a run."""

    REPRODUCED = "reproduced"
    NOT_REPRODUCED = "not_reproduced"
    SETUP_FAILED = "setup_failed"
    ERROR = "error"  # internal failure of ReproBot


class ReproResult(_Model):
    """The final result of a run, shown to users and saved as result.json."""

    verdict: Verdict
    confidence: Literal["high", "medium", "low"] | None
    test_file: str | None  # path inside the repo
    test_code: str | None  # only the new test function(s)
    test_output: str | None  # trimmed output of the failing run
    failure_reason: str | None  # verifier explanation
    suspected_location: str | None  # e.g. 'utils/dates.py:42'
    summary: str  # 2 to 4 sentences for humans
    attempts: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    duration_s: float = Field(ge=0)
    run_id: str


# ---------- Trajectory ----------


class ToolCallRecord(_Model):
    """One tool call the agent made during a step, and what it got back."""

    id: str
    name: str
    arguments: dict[str, Any]
    result: str  # already truncated


class Step(_Model):
    """One turn of the agent loop: one LLM call plus the tool calls it asked for.

    Saved as one line of runs/<run_id>/trace.jsonl.
    """

    index: int = Field(ge=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    text: str = ""  # what the LLM wrote, if anything
    tool_calls: list[ToolCallRecord] = []
