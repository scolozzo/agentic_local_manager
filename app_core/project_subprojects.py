from __future__ import annotations


_DEFAULT_SUBPROJECTS = {
    "BACK": {"label": "Backend", "stack_key": "BACK", "substack": "api"},
    "WEB_BACKOFFICE": {"label": "Front Web - Backoffice", "stack_key": "BO", "substack": "backoffice"},
    "WEB_LANDING": {"label": "Front Web - Landing", "stack_key": "BO", "substack": "landing"},
    "ANDROID": {"label": "Mobile - Android", "stack_key": "MOB", "substack": "android"},
    "IOS": {"label": "Mobile - iOS", "stack_key": "MOB", "substack": "ios"},
    "FLUTTER": {"label": "Mobile - Flutter", "stack_key": "MOB", "substack": "flutter"},
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
            repo_dir = raw_value.get("repo_dir") or raw_value.get("path") or ""
            base["rules"] = raw_value.get("rules", [])
            base["stack_key"] = raw_value.get("stack_key") or base["stack_key"]
            base["substack"] = raw_value.get("substack", base["substack"])
            base["stack_name"] = raw_value.get("stack_name", base["stack_key"])
        else:
            repo_dir = str(raw_value)
            base["rules"] = []
            base["stack_name"] = base["stack_key"]
        base["id"] = subproject_id
        base["repo_dir"] = repo_dir
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
