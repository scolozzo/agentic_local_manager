from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_core.system_settings import load_system_settings
from app_core.provider_validation import validate_git_credentials


def main() -> int:
    settings = load_system_settings()
    git_settings = settings.get("git", {})
    provider = (git_settings.get("provider") or "").strip()
    if not provider:
        return 0

    token = _resolve_git_token(provider)
    host = (git_settings.get("host") or "").strip()
    if not token:
        return _prompt_open_installer("No se encontró el token Git configurado. ¿Querés abrir el instalador para actualizarlo?")

    result = validate_git_credentials(provider, token, host)
    if result.get("ok"):
        return 0
    return _prompt_open_installer("La credencial Git ya no es válida. ¿Querés abrir el instalador para actualizarla?")


def _resolve_git_token(provider: str) -> str:
    env_key = {"github": "GITHUB_TOKEN", "gitlab": "GITLAB_TOKEN"}.get(provider.lower(), "")
    if not env_key:
        return ""
    return os.environ.get(env_key, "").strip() or _read_env_value(env_key)


def _read_env_value(key: str) -> str:
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return ""
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        current_key, value = line.split("=", 1)
        if current_key.strip() == key:
            return value.strip()
    return ""


def _prompt_open_installer(message: str) -> int:
    root = tk.Tk()
    root.withdraw()
    try:
        should_open = messagebox.askyesno("Agentic Manager", message)
    finally:
        root.destroy()
    if should_open:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO_ROOT / "Instalar_Agentic_Manager.ps1")],
            cwd=str(REPO_ROOT),
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
