from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app_core.agent_config import REPO_ROOT, load_agent_catalog, normalize_agent_definition, save_agent_catalog


_RUNNING: dict[str, subprocess.Popen] = {}
_SCHEDULE_PATH = REPO_ROOT / "config" / "schedule.json"


def load_agents() -> list[dict]:
    catalog = load_agent_catalog()
    return [normalize_agent_definition(agent, catalog) for agent in catalog.get("agents", [])]


def load_specializations() -> dict:
    return load_agent_catalog().get("specializations", {})


def get_agent(agent_id: str) -> dict | None:
    for agent in load_agents():
        if agent.get("id") == agent_id:
            return agent
    return None


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


def start_all() -> dict:
    results = [start_agent(agent["id"]) for agent in load_agents() if agent.get("enabled", True)]
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


def remove_agent(agent_id: str) -> dict:
    catalog = load_agent_catalog()
    before = len(catalog.get("agents", []))
    catalog["agents"] = [agent for agent in catalog.get("agents", []) if agent.get("id") != agent_id]
    save_agent_catalog(catalog)
    return {"ok": len(catalog["agents"]) < before}


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
