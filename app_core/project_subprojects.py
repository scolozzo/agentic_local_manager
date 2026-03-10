from __future__ import annotations

from pathlib import Path

from app_core.agent_config import REPO_ROOT

_DEFAULT_SUBPROJECTS = {
    "BACK": {"label": "Backend", "stack_key": "BACK", "substack": "api"},
    "WEB_BACKOFFICE": {"label": "Front Web - Backoffice", "stack_key": "BO", "substack": "backoffice"},
    "WEB_LANDING": {"label": "Front Web - Landing", "stack_key": "BO", "substack": "landing"},
    "ANDROID": {"label": "Mobile - Android", "stack_key": "MOB", "substack": "android"},
    "IOS": {"label": "Mobile - iOS", "stack_key": "MOB", "substack": "ios"},
    "FLUTTER": {"label": "Mobile - Flutter", "stack_key": "MOB", "substack": "flutter"},
}

_STACK_DEFAULT_SKILLS = {
    ("BACK", "api"): ["backend", "db", "qa_backend"],
    ("BO", "backoffice"): ["front_web", "bo_backend", "qa_bo"],
    ("BO", "landing"): ["front_web", "qa_bo"],
    ("MOB", "android"): ["mob_android", "mob_backend", "qa_mob", "ux_android"],
    ("MOB", "ios"): ["mob_android", "mob_backend", "qa_mob", "ux_ios"],
    ("MOB", "flutter"): ["mob_android", "mob_backend", "qa_mob"],
}

_DEFAULT_SUBSTACKS = {
    "BACK": ["api", "db"],
    "BO": ["backoffice", "landing"],
    "MOB": ["android", "ios", "flutter"],
}


def normalize_project_subprojects(git_dirs: dict | None) -> list[dict]:
    subprojects = []
    for subproject_id, raw_value in (git_dirs or {}).items():
        if not raw_value:
            continue
        base = dict(_DEFAULT_SUBPROJECTS.get(subproject_id, {
            "label": subproject_id.replace("_", " ").title(),
            "stack_key": "BACK",
            "substack": "",
        }))
        if isinstance(raw_value, dict):
            repo_url = raw_value.get("repo_url") or raw_value.get("repo_dir") or raw_value.get("path") or ""
            base["rules"] = raw_value.get("rules", [])
            base["stack_key"] = raw_value.get("stack_key") or base["stack_key"]
            base["substack"] = raw_value.get("substack", base["substack"])
            base["stack_name"] = raw_value.get("stack_name", base["stack_key"])
            base["skills"] = raw_value.get("skills", default_skills_for_scope(base["stack_key"], base["substack"]))
            base["dev_model_profile"] = raw_value.get("dev_model_profile", "")
            base["qa_model_profile"] = raw_value.get("qa_model_profile", "")
            workspace_dir = raw_value.get("workspace_dir") or _default_workspace_dir(raw_value.get("project_id", ""), subproject_id)
        else:
            repo_url = str(raw_value)
            base["rules"] = []
            base["stack_name"] = base["stack_key"]
            base["skills"] = default_skills_for_scope(base["stack_key"], base["substack"])
            base["dev_model_profile"] = ""
            base["qa_model_profile"] = ""
            workspace_dir = _default_workspace_dir("", subproject_id)
        base["id"] = subproject_id
        base["repo_url"] = repo_url
        base["repo_dir"] = repo_url
        base["workspace_dir"] = workspace_dir
        subprojects.append(base)
    return subprojects


def get_subproject_definition(subproject_id: str) -> dict:
    base = dict(_DEFAULT_SUBPROJECTS.get(subproject_id, {
        "label": subproject_id.replace("_", " ").title(),
        "stack_key": "BACK",
        "substack": "",
    }))
    base["id"] = subproject_id
    base.setdefault("rules", [])
    base.setdefault("stack_name", base["stack_key"])
    return base


def default_skills_for_scope(stack_key: str | None, substack: str | None = None) -> list[str]:
    normalized_stack = (stack_key or "").strip().upper()
    normalized_substack = (substack or "").strip().lower()
    return list(_STACK_DEFAULT_SKILLS.get((normalized_stack, normalized_substack), []))


def list_substack_options(stack_key: str | None) -> list[str]:
    return list(_DEFAULT_SUBSTACKS.get((stack_key or "").strip().upper(), []))


def upsert_subproject_config(git_dirs: dict | None, subproject_data: dict) -> dict:
    normalized = dict(git_dirs or {})
    subproject_id = (subproject_data.get("id") or "").strip().upper()
    if not subproject_id:
        raise ValueError("Subproject id is required")
    stack_key = (subproject_data.get("stack_key") or "").strip().upper()
    substack = (subproject_data.get("substack") or "").strip().lower()
    normalized[subproject_id] = {
        "label": (subproject_data.get("label") or subproject_id).strip(),
        "repo_url": (subproject_data.get("repo_url") or subproject_data.get("repo_dir") or "").strip(),
        "workspace_dir": (subproject_data.get("workspace_dir") or _default_workspace_dir(subproject_data.get("project_id", ""), subproject_id)).strip(),
        "project_id": (subproject_data.get("project_id") or "").strip(),
        "stack_key": stack_key,
        "substack": substack,
        "stack_name": (subproject_data.get("stack_name") or stack_key).strip(),
        "rules": list(subproject_data.get("rules") or []),
        "skills": list(subproject_data.get("skills") or default_skills_for_scope(stack_key, substack)),
        "dev_model_profile": (subproject_data.get("dev_model_profile") or "").strip(),
        "qa_model_profile": (subproject_data.get("qa_model_profile") or "").strip(),
    }
    return normalized


def _default_workspace_dir(project_id: str, subproject_id: str) -> str:
    project_segment = (project_id or "shared").strip().lower() or "shared"
    subproject_segment = (subproject_id or "subproject").strip().lower() or "subproject"
    return str(Path(REPO_ROOT) / "workspaces" / project_segment / subproject_segment)
