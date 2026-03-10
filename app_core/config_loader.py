from __future__ import annotations

import json
from pathlib import Path

from app_core.agent_config import REPO_ROOT


def _load_repos() -> dict:
    path = REPO_ROOT / "config" / "repos.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get_gitlab_project_id(stack_key: str) -> str:
    return _load_repos().get((stack_key or "BACK").upper(), {}).get("project_id", "")


def get_develop_branch(stack_key: str) -> str:
    return _load_repos().get((stack_key or "BACK").upper(), {}).get("develop_branch", "develop")


def get_repo_config(stack_key: str) -> dict:
    return _load_repos().get((stack_key or "BACK").upper(), {})
