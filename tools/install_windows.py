from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SOURCE_ROOT))

from app_core.system_settings import DEFAULT_SYSTEM_SETTINGS  # noqa: E402
from app_core.provider_validation import validate_git_credentials, validate_llm_service  # noqa: E402


SKIP_NAMES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "memory",
    "logs",
    ".mypy_cache",
}
GIT_TOKEN_ENV = {"github": "GITHUB_TOKEN", "gitlab": "GITLAB_TOKEN"}


def main() -> int:
    print("Instalador de Agentic Local Manager para Windows")
    print("=" * 56)

    target_root = _prompt_install_dir()
    _copy_repo(SOURCE_ROOT, target_root)

    settings = json.loads(json.dumps(DEFAULT_SYSTEM_SETTINGS))
    settings["install"]["install_dir"] = str(target_root)
    settings["install"]["launcher_path"] = str(target_root / "Iniciar_Agentic_Manager.cmd")

    env_values: dict[str, str] = {}
    settings["git"], git_env = _configure_git()
    env_values.update(git_env)

    llm_services, llm_env = _configure_llm_services(settings["llm_services"])
    settings["llm_services"] = llm_services
    env_values.update(llm_env)
    settings["role_defaults"] = _select_role_defaults(settings)

    _write_json(target_root / "config" / "system_settings.json", settings)
    _write_env(target_root / ".env", env_values)
    _create_desktop_shortcut(target_root / "Iniciar_Agentic_Manager.cmd", target_root)

    print("\nInstalacion finalizada.")
    print(f"Directorio: {target_root}")
    print("Se creo un acceso directo en el escritorio.")
    return 0


def _prompt_install_dir() -> Path:
    default_dir = Path.home() / "AgenticLocalManager"
    raw = input(f"Directorio de instalacion [{default_dir}]: ").strip()
    target = Path(raw) if raw else default_dir
    return target.expanduser().resolve()


def _copy_repo(source: Path, target: Path) -> None:
    if target.exists():
        answer = input(f"El directorio {target} ya existe. Sobrescribir contenido instalable? [s/N]: ").strip().lower()
        if answer != "s":
            print("Instalacion cancelada.")
            raise SystemExit(1)
        _clean_target(target)
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name in SKIP_NAMES:
            continue
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*SKIP_NAMES))
        else:
            shutil.copy2(item, destination)


def _clean_target(target: Path) -> None:
    for item in target.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def _configure_git() -> tuple[dict, dict[str, str]]:
    print("\nConfiguracion Git")
    providers = {"1": "github", "2": "gitlab"}
    provider = providers.get(input("Proveedor [1=GitHub, 2=GitLab]: ").strip(), "github")
    default_host = "https://api.github.com" if provider == "github" else "https://gitlab.com"
    host = input(f"Host/API base [{default_host}]: ").strip() or default_host
    while True:
        token = input(f"Token de acceso de {provider}: ").strip()
        result = validate_git_credentials(provider, token, host)
        if result.get("ok"):
            print(f"Credenciales OK para {result.get('username') or provider}.")
            git_settings = {
                "provider": provider,
                "host": result.get("host", host),
                "username": result.get("username", ""),
                "validated": True,
                "validated_at": result.get("validated_at", ""),
            }
            return git_settings, {GIT_TOKEN_ENV[provider]: token}
        print(f"Error validando git: {result.get('error', 'desconocido')}")
        if input("Reintentar? [S/n]: ").strip().lower() == "n":
            return {
                "provider": provider,
                "host": host,
                "username": "",
                "validated": False,
                "validated_at": "",
            }, {}


def _configure_llm_services(default_services: dict) -> tuple[dict, dict[str, str]]:
    print("\nConfiguracion de servicios LLM")
    services = json.loads(json.dumps(default_services))
    env_values: dict[str, str] = {}
    for service_id, service in services.items():
        answer = input(f"Habilitar {service['label']}? [s/N]: ").strip().lower()
        if answer != "s":
            service["available"] = False
            service["validated"] = False
            continue
        if service.get("mode") == "manual_login":
            service["available"] = True
            service["validated"] = False
            service["manual_only"] = True
            continue
        token = input(f"API key para {service['label']}: ").strip()
        validation = validate_llm_service(service_id, service, token)
        service.update({k: v for k, v in validation.items() if k not in {"ok", "error", "message"}})
        if validation.get("ok"):
            print(f"{service['label']} validado.")
            env_key = service.get("api_key_env")
            if env_key:
                env_values[env_key] = token
            service["available"] = True
            service["validated"] = True
        else:
            print(f"No se pudo validar {service['label']}: {validation.get('error') or validation.get('message')}")
            service["available"] = False
            service["validated"] = False
    return services, env_values


def _select_role_defaults(settings: dict) -> dict:
    profiles = []
    for service_id, service in settings.get("llm_services", {}).items():
        if not service.get("available"):
            continue
        for model in service.get("models", []):
            profiles.append((f"{service_id}:{model}", f"{service['label']} -> {model}"))
    if not profiles:
        return dict(settings.get("role_defaults", {}))
    print("\nPerfiles disponibles")
    for idx, (_, label) in enumerate(profiles, start=1):
        print(f"  {idx}. {label}")

    defaults = {}
    defaults["developers"] = _pick_profile("Perfil para los 3 developers", profiles)
    defaults["qa"] = _pick_profile("Perfil para QA (conviene el mas economico)", profiles, preferred_terms=("minimax", "flash", "turbo"))
    defaults["orchestrator"] = _pick_profile("Perfil para Orchestrator", profiles)
    defaults["pm"] = _pick_profile("Perfil para PM (conviene economico o free)", profiles, preferred_terms=("flash", "turbo", "mini"))
    return defaults


def _pick_profile(prompt: str, profiles: list[tuple[str, str]], preferred_terms: tuple[str, ...] = ()) -> str:
    default_index = 1
    if preferred_terms:
        for idx, (_, label) in enumerate(profiles, start=1):
            lowered = label.lower()
            if any(term in lowered for term in preferred_terms):
                default_index = idx
                break
    raw = input(f"{prompt} [{default_index}]: ").strip()
    try:
        index = int(raw or str(default_index))
    except ValueError:
        index = default_index
    index = max(1, min(index, len(profiles)))
    return profiles[index - 1][0]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_env(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in sorted(values.items()) if value]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _create_desktop_shortcut(launcher_path: Path, working_dir: Path) -> None:
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


if __name__ == "__main__":
    raise SystemExit(main())
