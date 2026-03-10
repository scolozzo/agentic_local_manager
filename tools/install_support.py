from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from app_core.provider_validation import validate_git_credentials, validate_llm_service
from app_core.system_settings import DEFAULT_SYSTEM_SETTINGS


SOURCE_ROOT = Path(__file__).resolve().parent.parent
SKIP_NAMES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "memory",
    "logs",
    ".mypy_cache",
}
GIT_TOKEN_ENV = {"github": "GITHUB_TOKEN", "gitlab": "GITLAB_TOKEN"}


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
    settings["install"]["launcher_path"] = str(target_root / "Iniciar_Agentic_Manager.cmd")
    return settings


def validate_git(provider: str, token: str, host: str = "") -> dict:
    return validate_git_credentials(provider, token, host)


def validate_service(service_id: str, service: dict, api_key: str = "") -> dict:
    return validate_llm_service(service_id, service, api_key)


def available_profiles(settings: dict) -> list[dict]:
    profiles = []
    for service_id, service in settings.get("llm_services", {}).items():
        if not service.get("available"):
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


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_env(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in sorted(values.items()) if value]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def create_desktop_shortcut(launcher_path: Path, working_dir: Path) -> None:
    desktop = Path.home() / "Desktop" / "Agentic Local Manager.lnk"
    launcher_path = launcher_path.resolve()
    working_dir = working_dir.resolve()
    ps_script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$shortcut = $shell.CreateShortcut('{desktop}'); "
        "$shortcut.TargetPath = 'cmd.exe'; "
        f"$shortcut.Arguments = '/c \"\"{launcher_path}\"\"'; "
        f"$shortcut.WorkingDirectory = '{working_dir}'; "
        f"$shortcut.IconLocation = '{launcher_path},0'; "
        "$shortcut.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        check=True,
        cwd=str(working_dir),
    )

