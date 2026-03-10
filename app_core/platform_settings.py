from __future__ import annotations

import json
from pathlib import Path

_SETTINGS_FILE = Path(__file__).resolve().parent.parent / "config" / "platform_settings.json"

_DEFAULT_SETTINGS = {
    "coding_rules": [
        "Preservar patrones existentes del repositorio antes de introducir nuevos.",
        "Mantener cambios pequenos, enfocados y compatibles hacia atras.",
        "Agregar pruebas o validaciones cuando el cambio afecte comportamiento.",
        "Evitar comentarios innecesarios y codigo muerto.",
    ],
    "git_rules": [
        "Trabajar sobre ramas de feature y fusionar a develop cuando la validacion pase.",
        "No reescribir historia compartida ni usar comandos destructivos sobre trabajo ajeno.",
        "Usar nombres de ramas y commits claros y orientados a la funcionalidad.",
        "Respetar el flujo feature -> develop -> release definido por la plataforma.",
    ],
    "token_optimization_rules": [
        "Minimizar contexto redundante en prompts y llamadas LLM.",
        "Preferir rutas locales, status router y cache antes de escalar a LLM.",
        "Usar solo el contexto de proyecto, sprint y task estrictamente necesario.",
        "Evitar llamadas repetidas con la misma informacion si ya existe estado local.",
    ],
}


def load_platform_settings() -> dict:
    if not _SETTINGS_FILE.exists():
        save_platform_settings(_DEFAULT_SETTINGS)
        return dict(_DEFAULT_SETTINGS)
    data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    for key, value in _DEFAULT_SETTINGS.items():
        data.setdefault(key, list(value))
    return data


def save_platform_settings(settings: dict) -> dict:
    normalized = {
        "coding_rules": _normalize_lines(settings.get("coding_rules", [])),
        "git_rules": _normalize_lines(settings.get("git_rules", [])),
        "token_optimization_rules": _normalize_lines(settings.get("token_optimization_rules", [])),
    }
    _SETTINGS_FILE.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return normalized


def render_platform_rules_prompt() -> str:
    settings = load_platform_settings()
    sections = []
    for title, key in (
        ("Reglas globales de codificacion", "coding_rules"),
        ("Reglas globales de git y ramas", "git_rules"),
        ("Reglas globales de optimizacion de tokens", "token_optimization_rules"),
    ):
        rules = settings.get(key, [])
        if rules:
            sections.append(title + ":\n- " + "\n- ".join(rules))
    return "\n\n".join(sections).strip()


def _normalize_lines(value) -> list[str]:
    if isinstance(value, str):
        lines = [line.strip() for line in value.splitlines()]
    else:
        lines = [str(item).strip() for item in value]
    return [line for line in lines if line]
