from __future__ import annotations

import json

from app_core.agent_config import REPO_ROOT


_TEMPLATES_FILE = REPO_ROOT / "config" / "project_templates.json"
_DEFAULT_TEMPLATE_ID = "software_delivery_default"


def _load_template_catalog() -> dict:
    if not _TEMPLATES_FILE.exists():
        return {"default_template": _DEFAULT_TEMPLATE_ID, "templates": {}}
    data = json.loads(_TEMPLATES_FILE.read_text(encoding="utf-8"))
    data.setdefault("default_template", _DEFAULT_TEMPLATE_ID)
    data.setdefault("templates", {})
    return data


def list_project_templates() -> list[dict]:
    catalog = _load_template_catalog()
    templates = []
    for template_id, template in catalog.get("templates", {}).items():
        item = dict(template)
        item["id"] = template_id
        templates.append(item)
    return templates


def get_default_template_id() -> str:
    return _load_template_catalog().get("default_template", _DEFAULT_TEMPLATE_ID)


def get_project_template(template_id: str | None) -> dict:
    catalog = _load_template_catalog()
    resolved_id = template_id or catalog.get("default_template", _DEFAULT_TEMPLATE_ID)
    template = dict(catalog.get("templates", {}).get(resolved_id, {}))
    if not template:
        resolved_id = catalog.get("default_template", _DEFAULT_TEMPLATE_ID)
        template = dict(catalog.get("templates", {}).get(resolved_id, {}))
    template.setdefault("label", resolved_id)
    template.setdefault("description", "")
    template.setdefault("workflow", {"states": [], "transitions": []})
    template.setdefault("allowed_stacks", [])
    template.setdefault("required_roles", [])
    template.setdefault("suggested_preset", "default_software_team")
    template.setdefault("expected_artifacts", [])
    template["id"] = resolved_id
    return template


def get_workflow_definition(template_id: str | None = None) -> dict:
    return get_project_template(template_id).get("workflow", {"states": [], "transitions": []})
