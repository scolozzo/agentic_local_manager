from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable

from app_core.agent_config import (
    REPO_ROOT,
    load_agent_catalog,
    load_agent_presets,
    normalize_agent_definition,
    save_agent_catalog,
    save_agent_presets,
)


_RUNNING: dict[str, subprocess.Popen] = {}
_SCHEDULE_PATH = REPO_ROOT / "config" / "schedule.json"
_STACK_KEYS = ("BACK", "BO", "MOB")
_SUBSTACK_ALIASES = {
    "": "",
    "api": "api",
    "db": "db",
    "backoffice": "backoffice",
    "landing": "landing",
    "android": "android",
    "ios": "ios",
    "flutter": "flutter",
}


def _normalize_agents(catalog: dict) -> list[dict]:
    return [normalize_agent_definition(agent, catalog) for agent in catalog.get("agents", [])]


def load_agents() -> list[dict]:
    return _normalize_agents(load_agent_catalog())


def load_specializations() -> dict:
    return load_agent_catalog().get("specializations", {})


def list_presets() -> dict:
    return load_agent_presets().get("presets", {})


def get_active_preset_name() -> str:
    presets = load_agent_presets()
    active = presets.get("active_preset") or presets.get("default_preset") or "default_software_team"
    if active in presets.get("presets", {}):
        return active
    return presets.get("default_preset", "default_software_team")


def get_active_preset() -> dict:
    presets = load_agent_presets()
    active_name = get_active_preset_name()
    preset = dict(presets.get("presets", {}).get(active_name, {}))
    preset.setdefault("label", active_name)
    preset.setdefault("supported_stacks", list(_STACK_KEYS))
    preset.setdefault("eligibility", [])
    preset.setdefault("suggested_counts", {})
    preset["id"] = active_name
    return preset


def set_active_preset(preset_name: str) -> dict:
    presets = load_agent_presets()
    if preset_name not in presets.get("presets", {}):
        return {"ok": False, "error": "Preset not found"}
    presets["active_preset"] = preset_name
    save_agent_presets(presets)
    return {"ok": True, "active_preset": preset_name}


def get_agent(agent_id: str) -> dict | None:
    for agent in load_agents():
        if agent.get("id") == agent_id:
            return agent
    return None


def _to_iterable(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _as_stack_key(value: str | None) -> str:
    return (value or "").strip().upper()


def _as_substack_key(value: str | None) -> str:
    return _SUBSTACK_ALIASES.get((value or "").strip().lower(), (value or "").strip().lower())


def _matches_any(candidate: str, options: Iterable[str]) -> bool:
    values = [item for item in options if item not in ("", "*", "any", "ANY")]
    if not values:
        return True
    return candidate in values


def _preset_includes_agent(agent: dict, preset: dict) -> bool:
    agent_ids = preset.get("agents")
    if agent_ids:
        return agent.get("id") in agent_ids
    rules = preset.get("eligibility", [])
    if not rules:
        return True
    role = agent.get("role", "")
    stack_key = agent.get("stack_key", "")
    for rule in rules:
        if _matches_any(role, _to_iterable(rule.get("roles"))) and _matches_any(stack_key, _to_iterable(rule.get("stacks"))):
            return True
    return False


def explain_agent_eligibility(
    agent: dict,
    *,
    role: str | None = None,
    stack_key: str | None = None,
    preset_name: str | None = None,
) -> dict:
    preset = dict(list_presets().get(preset_name or get_active_preset_name(), get_active_preset()))
    preset.setdefault("supported_stacks", list(_STACK_KEYS))
    reasons: list[str] = []
    eligible = True
    candidate_role = agent.get("role", "")
    candidate_stack = _as_stack_key(agent.get("stack_key"))
    requested_stack = _as_stack_key(stack_key)

    if not agent.get("enabled", True):
        eligible = False
        reasons.append("disabled")

    if role and candidate_role != role:
        eligible = False
        reasons.append(f"role mismatch ({candidate_role})")

    if requested_stack and requested_stack not in preset.get("supported_stacks", list(_STACK_KEYS)):
        eligible = False
        reasons.append(f"preset excludes stack {requested_stack}")

    if not _preset_includes_agent(agent, preset):
        eligible = False
        reasons.append(f"preset excludes agent {agent.get('id')}")

    if requested_stack and candidate_role in {"developer", "qa"} and candidate_stack != requested_stack:
        eligible = False
        reasons.append(f"stack mismatch ({candidate_stack or 'NONE'})")

    if eligible:
        if requested_stack:
            reasons.append(f"eligible for {candidate_role}:{requested_stack}")
        else:
            reasons.append("eligible")

    return {
        "eligible": eligible,
        "reasons": reasons,
        "preset": preset.get("id") or preset_name or get_active_preset_name(),
    }


def list_eligible_agents(
    *,
    role: str | None = None,
    stack_key: str | None = None,
    preset_name: str | None = None,
) -> list[dict]:
    eligible_agents = []
    for agent in load_agents():
        eligibility = explain_agent_eligibility(agent, role=role, stack_key=stack_key, preset_name=preset_name)
        if eligibility["eligible"]:
            eligible_agents.append({**agent, "eligibility": eligibility})
    return eligible_agents


def get_team_status() -> dict:
    return get_team_status_for(None)


def get_team_status_for(active_team_id: str | None) -> dict:
    presets_cfg = load_agent_presets()
    active_name = active_team_id or get_active_preset_name()
    presets = []
    for preset_id, preset in presets_cfg.get("presets", {}).items():
        preset_data = dict(preset)
        preset_data.setdefault("label", preset_id)
        preset_data.setdefault("supported_stacks", list(_STACK_KEYS))
        preset_data.setdefault("suggested_counts", {})
        preset_data.setdefault("skills", [])
        preset_data.setdefault("substacks", [])
        preset_data.setdefault("stack_key", preset_data.get("supported_stacks", [""])[0] if preset_data.get("supported_stacks") else "")
        preset_data["id"] = preset_id
        preset_data["active"] = preset_id == active_name
        presets.append(preset_data)
    return {"active_preset": active_name, "presets": presets}


def get_agents_with_eligibility(*, stack_key: str | None = None, preset_name: str | None = None) -> list[dict]:
    agents = []
    for agent in load_agents():
        eligibility = explain_agent_eligibility(agent, stack_key=stack_key, preset_name=preset_name)
        agents.append({**agent, "eligibility": eligibility})
    return agents


def get_log(agent_id: str, lines: int = 80) -> str:
    agent = get_agent(agent_id) or {}
    log_file = REPO_ROOT / agent.get("log_file", f"{agent_id}.log")
    if not log_file.exists():
        return ""
    content = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def get_current_task(agent_id: str) -> str:
    return "En espera"


def _agent_command(agent: dict) -> list[str]:
    script = agent.get("script")
    cmd = ["python", script]
    if agent.get("type") == "dev":
        cmd.append(agent["id"])
    return cmd


def start_agent(agent_id: str) -> dict:
    agent = get_agent(agent_id)
    if not agent:
        return {"ok": False, "error": "Agent not found"}
    if agent_id in _RUNNING and _RUNNING[agent_id].poll() is None:
        return {"ok": True, "message": "Already running"}
    process = subprocess.Popen(_agent_command(agent), cwd=REPO_ROOT)
    _RUNNING[agent_id] = process
    return {"ok": True}


def stop_agent(agent_id: str) -> dict:
    process = _RUNNING.get(agent_id)
    if process and process.poll() is None:
        process.terminate()
    _RUNNING.pop(agent_id, None)
    return {"ok": True}


def start_all(preset_name: str | None = None) -> dict:
    results = [start_agent(agent["id"]) for agent in list_eligible_agents(preset_name=preset_name or get_active_preset_name())]
    return {"ok": all(result.get("ok") for result in results)}


def stop_all() -> dict:
    for agent in list(_RUNNING):
        stop_agent(agent)
    return {"ok": True}


def is_running(agent_id: str) -> bool:
    process = _RUNNING.get(agent_id)
    return bool(process and process.poll() is None)


def add_agent(agent_data: dict) -> dict:
    catalog = load_agent_catalog()
    normalized = normalize_agent_definition(agent_data, catalog)
    agents = [agent for agent in catalog.get("agents", []) if agent.get("id") != normalized.get("id")]
    agents.append(normalized)
    catalog["agents"] = agents
    save_agent_catalog(catalog)
    return {"ok": True, "agent": normalized}


def update_agent(agent_id: str, changes: dict) -> dict:
    catalog = load_agent_catalog()
    updated = None
    agents = []
    for agent in catalog.get("agents", []):
        if agent.get("id") == agent_id:
            merged = {**agent, **changes}
            updated = normalize_agent_definition(merged, catalog)
            agents.append(updated)
        else:
            agents.append(agent)
    if updated is None:
        return {"ok": False, "error": "Agent not found"}
    catalog["agents"] = agents
    save_agent_catalog(catalog)
    return {"ok": True, "agent": updated}


def set_agent_enabled(agent_id: str, enabled: bool) -> dict:
    return update_agent(agent_id, {"enabled": bool(enabled)})


def set_agents_enabled_for_stack(stack_key: str, enabled: bool, roles: tuple[str, ...] = ("developer", "qa")) -> dict:
    catalog = load_agent_catalog()
    updated_agents = []
    affected_ids: list[str] = []
    for agent in catalog.get("agents", []):
        normalized = normalize_agent_definition(agent, catalog)
        if normalized.get("role") in roles and normalized.get("stack_key") == _as_stack_key(stack_key):
            normalized["enabled"] = bool(enabled)
            affected_ids.append(normalized["id"])
            updated_agents.append(normalized)
        else:
            updated_agents.append(agent)
    catalog["agents"] = updated_agents
    save_agent_catalog(catalog)
    return {"ok": True, "stack_key": _as_stack_key(stack_key), "enabled": bool(enabled), "affected": affected_ids}


def remove_agent(agent_id: str) -> dict:
    agent = get_agent(agent_id)
    if agent and not agent.get("removable", True):
        return {"ok": False, "error": "Agent is locked by sprint team"}
    catalog = load_agent_catalog()
    before = len(catalog.get("agents", []))
    catalog["agents"] = [agent for agent in catalog.get("agents", []) if agent.get("id") != agent_id]
    save_agent_catalog(catalog)
    return {"ok": len(catalog["agents"]) < before}


def list_team_presets(stack_key: str | None = None, substack: str | None = None) -> list[dict]:
    requested_stack = _as_stack_key(stack_key)
    requested_substack = _as_substack_key(substack)
    teams = []
    for team in get_team_status_for(None)["presets"]:
        team_stack = _as_stack_key(team.get("stack_key"))
        team_substacks = [_as_substack_key(item) for item in team.get("substacks", [])]
        if requested_stack and team_stack and team_stack != requested_stack:
            continue
        if requested_substack and team_substacks and requested_substack not in team_substacks:
            continue
        teams.append(team)
    return teams


def get_team_preset(team_id: str | None) -> dict | None:
    if not team_id:
        return None
    return next((team for team in get_team_status_for(team_id)["presets"] if team.get("id") == team_id), None)


def suggest_team_for_scope(stack_key: str | None, substack: str | None = None) -> dict | None:
    teams = list_team_presets(stack_key=stack_key, substack=substack)
    requested_substack = _as_substack_key(substack)
    if requested_substack:
        teams.sort(
            key=lambda team: (
                0 if requested_substack in [_as_substack_key(item) for item in team.get("substacks", [])] else 1,
                len(team.get("substacks", [])) or 99,
            )
        )
    return teams[0] if teams else None


def validate_agent_for_team(agent_data: dict, team_id: str | None) -> tuple[bool, str]:
    if not team_id:
        return True, ""
    team = get_team_preset(team_id)
    if not team:
        return False, "Team not found"
    normalized = normalize_agent_definition(agent_data)
    if normalized.get("role") != "developer":
        return True, ""
    allowed_skills = set(team.get("skills", []))
    specialization = normalized.get("specialization", "")
    if specialization not in allowed_skills:
        return False, f"El team '{team.get('label', team_id)}' no permite el skill '{specialization}'."
    return True, ""


def system_running() -> bool:
    return any(is_running(agent["id"]) for agent in load_agents())


def get_schedule() -> dict:
    if not _SCHEDULE_PATH.exists():
        return {"enabled": False, "start_time": "", "stop_time": ""}
    return json.loads(_SCHEDULE_PATH.read_text(encoding="utf-8"))


def save_schedule(schedule: dict) -> None:
    _SCHEDULE_PATH.write_text(json.dumps(schedule, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def start_scheduler() -> None:
    return None
