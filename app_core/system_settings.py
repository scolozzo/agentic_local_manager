from __future__ import annotations

import json
from pathlib import Path

from app_core.agent_config import REPO_ROOT


SETTINGS_FILE = REPO_ROOT / "config" / "system_settings.json"
ENV_FILE = REPO_ROOT / ".env"

DEFAULT_SYSTEM_SETTINGS = {
    "install": {
        "install_dir": str(REPO_ROOT),
        "launcher_path": str(REPO_ROOT / "Iniciar_Agentic_Manager.cmd"),
    },
    "git": {
        "provider": "",
        "host": "",
        "username": "",
        "validated": False,
        "validated_at": "",
    },
    "llm_services": {
        "chatgpt_login": {
            "label": "ChatGPT Login",
            "mode": "manual_login",
            "available": False,
            "validated": False,
            "models": ["chatgpt-login"],
        },
        "openai_api": {
            "label": "OpenAI API",
            "mode": "api",
            "available": False,
            "validated": False,
            "base_url": "https://api.openai.com/v1",
            "api_key_env": "OPENAI_API_KEY",
            "models": ["gpt-4.1", "o4-mini"],
        },
        "codex_api": {
            "label": "Codex API",
            "mode": "api",
            "available": False,
            "validated": False,
            "base_url": "https://api.openai.com/v1",
            "api_key_env": "OPENAI_API_KEY",
            "models": ["codex-5.3", "codex-5.4"],
        },
        "zai_api": {
            "label": "Z.AI API",
            "mode": "api",
            "available": False,
            "validated": False,
            "base_url": "https://api.z.ai/api/paas/v4",
            "api_key_env": "ZAI_API_KEY",
            "models": ["glm-4.7-flash", "glm-4.7", "glm-5"],
        },
        "qwen_api": {
            "label": "Qwen API",
            "mode": "api",
            "available": False,
            "validated": False,
            "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            "api_key_env": "QWEN_API_KEY",
            "models": ["qwen-max", "qwen-plus", "qwen-turbo"],
        },
        "minimax_api": {
            "label": "MiniMax API",
            "mode": "api",
            "available": False,
            "validated": False,
            "base_url": "https://api.minimax.io/v1",
            "api_key_env": "MINIMAX_API_KEY",
            "models": ["MiniMax-M2.5"],
        },
    },
    "role_defaults": {
        "developers": "",
        "qa": "",
        "orchestrator": "",
        "pm": "",
    },
}


def load_system_settings() -> dict:
    if not SETTINGS_FILE.exists():
        save_system_settings(DEFAULT_SYSTEM_SETTINGS)
        return json.loads(json.dumps(DEFAULT_SYSTEM_SETTINGS))
    data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    merged = json.loads(json.dumps(DEFAULT_SYSTEM_SETTINGS))
    _deep_merge(merged, data)
    return merged


def save_system_settings(settings: dict) -> dict:
    merged = json.loads(json.dumps(DEFAULT_SYSTEM_SETTINGS))
    _deep_merge(merged, settings or {})
    SETTINGS_FILE.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return merged


def list_available_model_profiles(settings: dict | None = None) -> list[dict]:
    cfg = settings or load_system_settings()
    profiles: list[dict] = []
    for service_id, service in cfg.get("llm_services", {}).items():
        if not service.get("available"):
            continue
        for model in service.get("models", []):
            profiles.append(
                {
                    "id": f"{service_id}:{model}",
                    "service_id": service_id,
                    "service_label": service.get("label", service_id),
                    "model": model,
                    "mode": service.get("mode", "api"),
                }
            )
    return profiles


def upsert_env_vars(values: dict[str, str]) -> None:
    current = _read_env()
    for key, value in values.items():
        if value:
            current[key] = value
    lines = [f"{key}={value}" for key, value in sorted(current.items())]
    ENV_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _read_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _deep_merge(target: dict, source: dict) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value
