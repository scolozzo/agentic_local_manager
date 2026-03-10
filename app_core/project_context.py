from __future__ import annotations

import json

from app_core.agent_config import REPO_ROOT
from app_core.adapters import get_default_adapters
from app_core.project_templates import get_default_template_id, get_project_template, get_workflow_definition
from app_core.project_validation import validate_project_configuration


_ACTIVE_PROJECT_FILE = REPO_ROOT / "config" / "active_project.json"


def get_active_project_id(default: str = "", memory_store=None) -> str:
    file_value = _read_active_project_file(default)
    if file_value:
        return file_value
    if memory_store and hasattr(memory_store, "get_platform_runtime_state"):
        state = memory_store.get_platform_runtime_state("dashboard").get("state", {})
        return state.get("last_project_id", default)
    return default


def set_active_project_id(project_id: str, memory_store=None) -> None:
    _ACTIVE_PROJECT_FILE.write_text(
        json.dumps({"project_id": project_id}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if memory_store and hasattr(memory_store, "save_platform_runtime_state"):
        memory_store.save_platform_runtime_state("dashboard", {"last_project_id": project_id})


def get_active_project_context(memory_store) -> dict:
    return resolve_project_context(memory_store, get_active_project_id(memory_store=memory_store))


def get_project_or_none(memory_store, project_id: str | None = None) -> dict | None:
    resolved_project_id = project_id or get_active_project_id(memory_store=memory_store)
    if not resolved_project_id:
        return None
    return memory_store.get_project(resolved_project_id)


def require_project_context(memory_store, project_id: str | None = None) -> dict:
    resolved_project_id = project_id or get_active_project_id(memory_store=memory_store)
    if not resolved_project_id:
        raise ValueError("Debes crear o seleccionar un proyecto antes de crear/configurar sprints.")
    project = get_project_or_none(memory_store, resolved_project_id)
    if not project:
        raise ValueError(f"El proyecto '{resolved_project_id}' no existe.")
    return resolve_project_context(memory_store, resolved_project_id)


def resolve_project_context(memory_store, project_id: str | None = None) -> dict:
    resolved_project_id = project_id or get_active_project_id(memory_store=memory_store)
    project = get_project_or_none(memory_store, resolved_project_id)
    if not project:
        template_id = get_default_template_id()
        template = get_project_template(template_id)
        context = {
            "project_id": resolved_project_id,
            "name": resolved_project_id or "Sin proyecto",
            "description": "",
            "template_id": template_id,
            "template": template,
            "workflow": get_workflow_definition(template_id),
            "git_dirs": {},
            "directives": {},
            "adapters": get_default_adapters(),
            "exists": False,
        }
        if resolved_project_id:
            context["validation_errors"] = [f"El proyecto '{resolved_project_id}' no existe."]
        else:
            context["validation_errors"] = ["Crea o selecciona un proyecto para habilitar sprints y tablero."]
        return context

    template_id = project.get("template_id") or get_default_template_id()
    template = get_project_template(template_id)
    context = {
        **project,
        "template_id": template_id,
        "template": template,
        "workflow": get_workflow_definition(template_id),
        "adapters": get_default_adapters(),
        "exists": True,
    }
    context["validation_errors"] = validate_project_configuration(context)
    return context


def _read_active_project_file(default: str = "") -> str:
    if not _ACTIVE_PROJECT_FILE.exists():
        return default
    data = json.loads(_ACTIVE_PROJECT_FILE.read_text(encoding="utf-8"))
    return data.get("project_id", default)
