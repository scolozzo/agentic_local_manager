from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
import sys


SOURCE_ROOT = Path(__file__).resolve().parent.parent
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from app_core.provider_validation import validate_git_credentials, validate_llm_service
from app_core.system_settings import DEFAULT_SYSTEM_SETTINGS

SKIP_NAMES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "memory",
    "logs",
    ".mypy_cache",
}
GIT_TOKEN_ENV = {"github": "GITHUB_TOKEN", "gitlab": "GITLAB_TOKEN"}
MANUAL_LOGIN_SERVICE_ID = "chatgpt_login"
MANUAL_LOGIN_PROFILE_ID = "chatgpt_login:chatgpt-login"
LAUNCHER_FILENAME = "Iniciar_Agentic_Manager.cmd"


def copy_repo(source: Path, target: Path, overwrite: bool = False) -> None:
    if target.exists():
        if not overwrite:
            raise FileExistsError(f"Target directory already exists: {target}")
        clean_target(target)
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name in SKIP_NAMES:
            continue
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*SKIP_NAMES))
        else:
            shutil.copy2(item, destination)


def clean_target(target: Path) -> None:
    for item in target.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def build_default_settings(target_root: Path) -> dict:
    settings = json.loads(json.dumps(DEFAULT_SYSTEM_SETTINGS))
    settings["install"]["install_dir"] = str(target_root)
    settings["install"]["launcher_path"] = str(target_root / LAUNCHER_FILENAME)
    return settings


def validate_git(provider: str, token: str, host: str = "") -> dict:
    return validate_git_credentials(provider, token, host)


def validate_service(service_id: str, service: dict, api_key: str = "") -> dict:
    return validate_llm_service(service_id, service, api_key)


def available_profiles(settings: dict, include_manual: bool = True) -> list[dict]:
    profiles = []
    for service_id, service in settings.get("llm_services", {}).items():
        if not service.get("available"):
            continue
        if not include_manual and service.get("mode") == "manual_login":
            continue
        for model in service.get("models", []):
            profiles.append(
                {
                    "id": f"{service_id}:{model}",
                    "label": f"{service.get('label', service_id)} -> {model}",
                    "service_id": service_id,
                    "model": model,
                }
            )
    return profiles


def ensure_manual_login_fallback(settings: dict) -> str:
    service = settings.setdefault("llm_services", {}).setdefault(
        MANUAL_LOGIN_SERVICE_ID,
        {
            "label": "ChatGPT Login",
            "mode": "manual_login",
            "available": True,
            "validated": False,
            "manual_only": True,
            "models": ["chatgpt-login"],
        },
    )
    service["available"] = True
    service["validated"] = False
    service["manual_only"] = True
    role_defaults = settings.setdefault("role_defaults", {})
    for role in ("developers", "qa", "orchestrator", "pm"):
        role_defaults[role] = MANUAL_LOGIN_PROFILE_ID
    return MANUAL_LOGIN_PROFILE_ID


def write_json(path: Path, payload: dict) -> None:
    _prepare_path_for_write(path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_env(path: Path, values: dict[str, str]) -> None:
    _prepare_path_for_write(path)
    lines = [f"{key}={value}" for key, value in sorted(values.items()) if value]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _prepare_path_for_write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            os.chmod(path, 0o666)
        except OSError:
            pass
        try:
            subprocess.run(
                ["attrib", "-r", "-h", "-s", str(path)],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            pass


def create_desktop_shortcut(launcher_path: Path, working_dir: Path) -> str | None:
    launcher_path = launcher_path.resolve()
    working_dir = working_dir.resolve()
    ps_script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        "$desktop = $shell.SpecialFolders('Desktop'); "
        "$shortcut = $shell.CreateShortcut((Join-Path $desktop 'Agentic Local Manager.lnk')); "
        "$shortcut.TargetPath = 'cmd.exe'; "
        f"$shortcut.Arguments = '/c \"\"{launcher_path}\"\"'; "
        f"$shortcut.WorkingDirectory = '{working_dir}'; "
        f"$shortcut.IconLocation = '{launcher_path},0'; "
        "$shortcut.Save()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            check=True,
            cwd=str(working_dir),
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        return str(exc)
    return None


def write_launcher_script(target_root: Path) -> Path:
    launcher_path = target_root / LAUNCHER_FILENAME
    launcher_content = _render_launcher_script(target_root.resolve())
    launcher_path.write_text(launcher_content, encoding="utf-8", newline="\r\n")
    return launcher_path


def _render_launcher_script(repo_dir: Path) -> str:
    repo_dir_str = str(repo_dir)
    return (
        "@echo off\n"
        "setlocal\n\n"
        f"set \"REPO_DIR={repo_dir_str}\"\n"
        "set \"DASHBOARD_PORT=8888\"\n"
        "set \"DASHBOARD_URL=http://localhost:%DASHBOARD_PORT%\"\n"
        "set \"DASHBOARD_HEALTH_URL=http://127.0.0.1:%DASHBOARD_PORT%/\"\n\n"
        "cd /d \"%REPO_DIR%\" || (\n"
        "  echo No se pudo acceder al repositorio: %REPO_DIR%\n"
        "  pause\n"
        "  exit /b 1\n"
        ")\n\n"
        "set \"PYTHON_EXE=\"\n"
        "set \"PYTHON_ARGS=\"\n"
        "where py >nul 2>nul && (\n"
        "  set \"PYTHON_EXE=py\"\n"
        "  set \"PYTHON_ARGS=-3\"\n"
        ")\n"
        "if not defined PYTHON_EXE (\n"
        "  where python >nul 2>nul && set \"PYTHON_EXE=python\"\n"
        ")\n\n"
        "if not defined PYTHON_EXE (\n"
        "  echo No se encontro Python en PATH.\n"
        "  echo Instala Python o agrega el ejecutable a PATH antes de iniciar el sistema.\n"
        "  pause\n"
        "  exit /b 1\n"
        ")\n\n"
        "\"%PYTHON_EXE%\" %PYTHON_ARGS% tools\\startup_checks.py\n"
        "if errorlevel 1 exit /b 1\n\n"
        "call :check_dashboard\n"
        "if errorlevel 1 (\n"
        "  echo Iniciando dashboard en %DASHBOARD_URL% ...\n"
        "  start \"Agentic Manager Dashboard\" /D \"%REPO_DIR%\" \"%PYTHON_EXE%\" %PYTHON_ARGS% dashboard.py\n"
        "  call :wait_dashboard\n"
        "  if errorlevel 1 (\n"
        "    echo El dashboard no respondio correctamente en %DASHBOARD_URL%.\n"
        "    echo Ejecuta manualmente: cd /d \"%REPO_DIR%\" ^&^& \"%PYTHON_EXE%\" %PYTHON_ARGS% dashboard.py\n"
        "    pause\n"
        "    exit /b 1\n"
        "  )\n"
        ") else (\n"
        "  echo El dashboard ya estaba corriendo y responde en %DASHBOARD_URL%.\n"
        ")\n\n"
        "start \"\" %DASHBOARD_URL%\n"
        "exit /b 0\n\n"
        ":check_dashboard\n"
        "powershell -NoProfile -ExecutionPolicy Bypass -Command ^\n"
        "  \"try { $r = Invoke-WebRequest -UseBasicParsing '%DASHBOARD_HEALTH_URL%' -TimeoutSec 3; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }\"\n"
        "exit /b %errorlevel%\n\n"
        ":wait_dashboard\n"
        "for /l %%I in (1,1,20) do (\n"
        "  call :check_dashboard\n"
        "  if not errorlevel 1 exit /b 0\n"
        "  timeout /t 1 /nobreak >nul\n"
        ")\n"
        "exit /b 1\n"
    )

