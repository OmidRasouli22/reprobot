from pathlib import Path

import pytest

from reprobot.config import (
    ConfigError,
    RepoConfig,
    Settings,
    build_run_config,
    load_repo_config,
)
from reprobot.models import Budget

ENV_VARS = [
    "REPROBOT_MODEL",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "GITHUB_TOKEN",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Each test starts with none of our env vars set and no .env file nearby."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def write_repo_config(repo: Path, text: str) -> Path:
    (repo / ".reprobot.yml").write_text(text, encoding="utf-8")
    return repo


# ---------- Settings ----------


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPROBOT_MODEL", "anthropic:some-model")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-123")

    settings = Settings()

    assert settings.reprobot_model == "anthropic:some-model"
    assert settings.anthropic_api_key is not None
    assert settings.anthropic_api_key.get_secret_value() == "sk-secret-123"


def test_settings_hide_api_keys_when_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-123")
    settings = Settings()
    assert "sk-secret-123" not in repr(settings)
    assert "sk-secret-123" not in str(settings.model_dump())


def test_settings_read_dotenv_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("REPROBOT_MODEL=openai_compat:qwen-coder\n")
    assert Settings().reprobot_model == "openai_compat:qwen-coder"


def test_settings_default_to_none() -> None:
    settings = Settings()
    assert settings.reprobot_model is None
    assert settings.anthropic_api_key is None


# ---------- load_repo_config ----------


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    config = load_repo_config(tmp_path)
    assert config == RepoConfig()
    assert config.trigger.label == "needs-repro"
    assert config.open_pr == "suggest"


def test_empty_file_gives_defaults(tmp_path: Path) -> None:
    assert load_repo_config(write_repo_config(tmp_path, "")) == RepoConfig()


def test_full_example_from_spec(tmp_path: Path) -> None:
    write_repo_config(
        tmp_path,
        """
trigger:
  label: needs-repro
  command: /repro
language: python
install: "uv pip install -e .[dev]"
test_command: "pytest -q {test_id}"
test_dir: tests/
budget:
  max_steps: 30
  max_cost_usd: 0.5
  max_minutes: 15
open_pr: suggest
""",
    )
    config = load_repo_config(tmp_path)
    assert config.language == "python"
    assert config.install == "uv pip install -e .[dev]"
    assert config.test_command == "pytest -q {test_id}"
    assert config.budget == Budget(max_steps=30, max_cost_usd=0.5, max_minutes=15)


def test_partial_budget_keeps_other_defaults(tmp_path: Path) -> None:
    write_repo_config(tmp_path, "budget:\n  max_steps: 10\n")
    budget = load_repo_config(tmp_path).budget
    assert budget is not None
    assert budget.max_steps == 10
    assert budget.max_cost_usd == 0.50


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("budget: [unclosed", "not valid YAML"),
        ("- just\n- a list\n", "must be a mapping"),
        ("max_steps: 10\n", "invalid settings"),  # typo: belongs under budget
        ("language: rust\n", "invalid settings"),
        ("budget:\n  max_steps: -1\n", "invalid settings"),
    ],
)
def test_bad_files_raise_config_error(tmp_path: Path, text: str, message: str) -> None:
    write_repo_config(tmp_path, text)
    with pytest.raises(ConfigError, match=message):
        load_repo_config(tmp_path)


# ---------- build_run_config ----------


def test_model_comes_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPROBOT_MODEL", "anthropic:some-model")
    config = build_run_config(Settings(), RepoConfig())
    assert config.model == "anthropic:some-model"
    assert config.budget == Budget()


def test_model_argument_wins_over_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPROBOT_MODEL", "anthropic:some-model")
    config = build_run_config(Settings(), RepoConfig(), model="openai_compat:qwen-coder")
    assert config.model == "openai_compat:qwen-coder"


def test_missing_model_is_a_clear_error() -> None:
    with pytest.raises(ConfigError, match="REPROBOT_MODEL"):
        build_run_config(Settings(), RepoConfig())


@pytest.mark.parametrize("bad", ["just-a-name", ":model", "anthropic:"])
def test_model_must_be_provider_colon_name(bad: str) -> None:
    with pytest.raises(ConfigError, match="provider:model"):
        build_run_config(Settings(), RepoConfig(), model=bad)


def test_repo_budget_is_used() -> None:
    repo = RepoConfig(budget=Budget(max_steps=5))
    config = build_run_config(Settings(), repo, model="anthropic:m")
    assert config.budget.max_steps == 5
