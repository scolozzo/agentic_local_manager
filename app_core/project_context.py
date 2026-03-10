from __future__ import annotations

import json

from app_core.agent_config import REPO_ROOT
from app_core.adapters import get_default_adapters
from app_core.project_templates import get_default_template_id, get_project_template, get_workflow_definition
from app_core.project_validation import validate_project_configuration


_ACTIVE_PROJECT_FILE = REPO_ROOT / "config" / "active_project.json"


def get_active_project_id(default: str = "SEGURO") -> str:
    if not _ACTIVE_PROJECT_FILE.exists():
        return default
    data = json.loads(_ACTIVE_PROJECT_FILE.read_text(encoding="utf-8"))
    return data.get("project_id", default)


def set_active_project_id(project_id: str) -> None:
    _ACTIVE_PROJECT_FILE.write_text(
        json.dumps({"project_id": project_id}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_active_project_context(memory_store) -> dict:
    return resolve_project_context(memory_store, get_active_project_id())


def resolve_project_context(memory_store, project_id: str | None = None) -> dict:
    resolved_project_id = project_id or get_active_project_id()
    project = next((item for item in memory_store.project_list() if item.get("project_id") == resolved_project_id), None)
    if not project:
        template_id = get_default_template_id()
        template = get_project_template(template_id)
        context = {
            "project_id": resolved_project_id,
            "name": resolved_project_id,
            "description": "",
            "template_id": template_id,
            "template": template,
            "workflow": get_workflow_definition(template_id),
            "git_dirs": {},
            "directives": {},
            "adapters": get_default_adapters(),
        }
        context["validation_errors"] = validate_project_configuration(context)
        return context

    template_id = project.get("template_id") or get_default_template_id()
    template = get_project_template(template_id)
    context = {
        **project,
        "template_id": template_id,
        "template": template,
        "workflow": get_workflow_definition(template_id),
        "adapters": get_default_adapters(),
    }
    context["validation_errors"] = validate_project_configuration(context)
    return context
