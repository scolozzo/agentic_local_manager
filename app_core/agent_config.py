from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path

from dotenv import load_dotenv
from app_core.platform_settings import render_platform_rules_prompt


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
PROMPTS_DIR = CONFIG_DIR / "prompts"
AGENTS_FILE = CONFIG_DIR / "agents.json"
PRESETS_FILE = CONFIG_DIR / "agent_presets.json"
DEFAULT_FALLBACKS = {
    "pm": "You are a project manager. Respond concisely.",
    "developer": "You are a software developer. Implement the assigned task.",
    "qa": "You are a QA engineer. Approve or reject with concise reasoning.",
    "orchestrator": "You are an orchestration agent. Coordinate work and blockers.",
}
ROLE_BY_TYPE = {
    "pm": "pm",
    "dev": "developer",
    "qa": "qa",
    "orchestrator": "orchestrator",
}
STACK_LABEL_BY_KEY = {
    "BACK": "backend",
    "BO": "front_web",
    "MOB": "front_mobile",
}
STACK_KEY_BY_LABEL = {value: key for key, value in STACK_LABEL_BY_KEY.items()}


def load_repo_env() -> None:
    load_dotenv(REPO_ROOT / ".env")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_agent_catalog(catalog: dict) -> None:
    AGENTS_FILE.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_agent_presets(presets: dict) -> None:
    PRESETS_FILE.write_text(json.dumps(presets, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_agent_catalog() -> dict:
    catalog = _read_json(AGENTS_FILE)
    catalog.setdefault("version", 2)
    catalog.setdefault("default_preset", "default_software_team")
    catalog.setdefault("agents", [])
    catalog.setdefault("roles", {})
    catalog.setdefault("stacks", {})
    catalog.setdefault("specializations", {})
    catalog.setdefault("providers", {})
    return catalog


def load_agent_presets() -> dict:
    presets = _read_json(PRESETS_FILE)
    presets.setdefault("default_preset", "default_software_team")
    presets.setdefault("active_preset", presets.get("default_preset", "default_software_team"))
    presets.setdefault("presets", {})
    return presets


def resolve_repo_path(path_like: str | None) -> Path | None:
    if not path_like:
        return None
    path = Path(path_like)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def read_prompt_file(path_like: str | None) -> str:
    path = resolve_repo_path(path_like)
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def infer_role(agent: dict) -> str:
    return (agent.get("role") or ROLE_BY_TYPE.get(agent.get("type", ""), agent.get("type", "")) or "").strip()


def infer_stack_key(agent: dict) -> str:
    stack_key = (agent.get("stack_key") or "").upper()
    if stack_key:
        return stack_key
    stack_value = (agent.get("stack") or "").strip()
    if stack_value.upper() in STACK_LABEL_BY_KEY:
        return stack_value.upper()
    return STACK_KEY_BY_LABEL.get(stack_value, "BACK")


def infer_stack_label(agent: dict) -> str:
    stack = (agent.get("stack") or "").strip()
    if stack and stack.lower() in STACK_KEY_BY_LABEL:
        return stack.lower()
    return STACK_LABEL_BY_KEY.get(infer_stack_key(agent), "backend")


def infer_base_prompt(agent: dict, catalog: dict) -> str | None:
    explicit = agent.get("base_prompt")
    if explicit:
        return explicit
    role = infer_role(agent)
    role_cfg = catalog.get("roles", {}).get(role, {})
    return role_cfg.get("prompt")


def infer_stack_prompt(agent: dict, catalog: dict) -> str | None:
    explicit = agent.get("stack_prompt")
    if explicit:
        return explicit
    specialization_key = agent.get("specialization")
    specialization = catalog.get("specializations", {}).get(specialization_key, {})
    legacy_prompt = specialization.get("stack_prompt")
    if legacy_prompt:
        return legacy_prompt
    stack_cfg = catalog.get("stacks", {}).get(infer_stack_label(agent), {})
    role = infer_role(agent)
    prompts = stack_cfg.get("prompts", {})
    if role == "developer":
        return prompts.get("developer")
    if role == "qa":
        return prompts.get("qa")
    return None


def infer_specialization_prompt(agent: dict, catalog: dict) -> str | None:
    explicit = agent.get("specialization_prompt")
    if explicit:
        return explicit
    specialization_key = agent.get("specialization")
    specialization = catalog.get("specializations", {}).get(specialization_key, {})
    return specialization.get("prompt")


def normalize_agent_definition(agent: dict, catalog: dict | None = None) -> dict:
    catalog = catalog or load_agent_catalog()
    normalized = deepcopy(agent)
    normalized["role"] = infer_role(normalized)
    normalized["stack_key"] = infer_stack_key(normalized)
    normalized["stack"] = infer_stack_label(normalized)
    normalized["base_prompt"] = infer_base_prompt(normalized, catalog)
    normalized["stack_prompt"] = infer_stack_prompt(normalized, catalog)
    normalized["specialization_prompt"] = infer_specialization_prompt(normalized, catalog)
    normalized.setdefault("enabled", True)
    normalized.setdefault("removable", True)
    return normalized


def list_agents() -> list[dict]:
    catalog = load_agent_catalog()
    return [normalize_agent_definition(agent, catalog) for agent in catalog.get("agents", [])]


def get_agent(agent_id: str) -> dict | None:
    for agent in list_agents():
        if agent.get("id") == agent_id:
            return agent
    return None


def compose_agent_prompt(agent: dict | str, runtime_context: str = "") -> str:
    catalog = load_agent_catalog()
    agent_def = get_agent(agent) if isinstance(agent, str) else normalize_agent_definition(agent, catalog)
    if not agent_def:
        return runtime_context.strip()
    platform_rules = render_platform_rules_prompt()
    parts = [
        read_prompt_file(agent_def.get("base_prompt")),
        read_prompt_file(agent_def.get("stack_prompt")),
        read_prompt_file(agent_def.get("specialization_prompt")),
        platform_rules,
        runtime_context.strip(),
    ]
    final_prompt = "\n\n".join(part for part in parts if part)
    if final_prompt:
        return final_prompt
    return DEFAULT_FALLBACKS.get(agent_def.get("role", ""), "You are a helpful assistant.")


def get_agent_model(agent_id: str, env_var: str | None = None, default: str = "") -> str:
    agent = get_agent(agent_id)
    if env_var:
        env_value = os.getenv(env_var)
        if env_value:
            return env_value
    if agent and agent.get("model"):
        return agent["model"]
    return default


def get_agent_provider(agent_id: str, default: str = "") -> str:
    agent = get_agent(agent_id)
    if agent and agent.get("provider"):
        return agent["provider"]
    return default
