"""Where ReproBot's settings come from.

Two sources are combined into one `RunConfig`:

* `Settings`: environment variables (and an optional local `.env` file) that belong
  to whoever runs ReproBot, such as the model and API keys.
* `RepoConfig`: an optional `.reprobot.yml` in the target repo, with settings that
  belong to that project, such as the budget or the install command.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from reprobot.models import Budget, RunConfig

REPO_CONFIG_FILENAME = ".reprobot.yml"


class ConfigError(Exception):
    """Settings are missing or invalid. The message says what to fix."""


# ---------- Environment ----------


class Settings(BaseSettings):
    """Settings read from environment variables, e.g. `REPROBOT_MODEL`.

    API keys are `SecretStr`, so they show as `**********` when printed or logged.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    reprobot_model: str | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    github_token: SecretStr | None = None


# ---------- .reprobot.yml ----------


class _RepoModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TriggerConfig(_RepoModel):
    """What starts a run on GitHub (used by the GitHub Action, Phase 4)."""

    label: str = "needs-repro"
    command: str = "/repro"


class RepoConfig(_RepoModel):
    """Per-repo settings from `.reprobot.yml`. Every field is optional."""

    trigger: TriggerConfig = TriggerConfig()
    language: Literal["python", "typescript"] | None = None  # auto-detected if None
    install: str | None = None  # overrides the adapter's install command
    test_command: str | None = None  # overrides the adapter's test command, uses {test_id}
    test_dir: str | None = None
    budget: Budget | None = None  # fields left out keep their defaults
    open_pr: Literal["suggest", "auto", "never"] = "suggest"


def load_repo_config(repo_dir: Path) -> RepoConfig:
    """Read `.reprobot.yml` from the repo root. A missing or empty file gives the defaults.

    Raises ConfigError if the file is not valid YAML or has unknown or invalid fields.
    """
    path = repo_dir / REPO_CONFIG_FILENAME
    if not path.is_file():
        return RepoConfig()

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{REPO_CONFIG_FILENAME} is not valid YAML: {exc}") from exc

    if data is None:
        return RepoConfig()
    if not isinstance(data, dict):
        raise ConfigError(f"{REPO_CONFIG_FILENAME} must be a mapping of keys to values.")

    try:
        return RepoConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{REPO_CONFIG_FILENAME} has invalid settings:\n{exc}") from exc


# ---------- Combine ----------


def build_run_config(
    settings: Settings, repo_config: RepoConfig, model: str | None = None
) -> RunConfig:
    """Combine environment and repo settings into the `RunConfig` for one run.

    `model` (e.g. from a CLI flag) wins over `REPROBOT_MODEL`. The budget comes from
    `.reprobot.yml` if it sets one, otherwise the defaults.
    """
    chosen = model or settings.reprobot_model
    if not chosen:
        raise ConfigError(
            "No model set. Set REPROBOT_MODEL, e.g. REPROBOT_MODEL=anthropic:<model>."
        )
    provider, _, name = chosen.partition(":")
    if not provider or not name:
        raise ConfigError(f"Model must look like 'provider:model', got {chosen!r}.")

    return RunConfig(model=chosen, budget=repo_config.budget or Budget())
