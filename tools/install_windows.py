from __future__ import annotations

import json
import sys
from pathlib import Path

from install_support import (
    GIT_TOKEN_ENV,
    SOURCE_ROOT,
    available_profiles,
    build_default_settings,
    copy_repo,
    create_desktop_shortcut,
    write_launcher_script,
    validate_git,
    validate_service,
    write_env,
    write_json,
)


def main() -> int:
    print("Agentic Local Manager Windows installer")
    print("=" * 48)

    target_root = _prompt_install_dir()
    overwrite = False
    if target_root.exists():
        overwrite = input(f"{target_root} already exists. Overwrite installable content? [y/N]: ").strip().lower() == "y"
    copy_repo(SOURCE_ROOT, target_root, overwrite=overwrite)

    settings = build_default_settings(target_root)
    env_values: dict[str, str] = {}

    settings["git"], git_env = _configure_git()
    env_values.update(git_env)

    llm_services, llm_env = _configure_llm_services(settings["llm_services"])
    settings["llm_services"] = llm_services
    env_values.update(llm_env)
    settings["role_defaults"] = _select_role_defaults(settings)

    launcher_path = write_launcher_script(target_root)
    write_json(target_root / "config" / "system_settings.json", settings)
    write_env(target_root / ".env", env_values)
    create_desktop_shortcut(launcher_path, target_root)

    print("\nInstallation completed successfully.")
    print(f"Installed to: {target_root}")
    print("A desktop shortcut was created.")
    return 0


def _prompt_install_dir() -> Path:
    default_dir = Path.home() / "AgenticLocalManager"
    raw = input(f"Install directory [{default_dir}]: ").strip()
    target = Path(raw) if raw else default_dir
    return target.expanduser().resolve()


def _configure_git() -> tuple[dict, dict[str, str]]:
    providers = {"1": "github", "2": "gitlab"}
    provider = providers.get(input("Git provider [1=GitHub, 2=GitLab]: ").strip(), "github")
    default_host = "https://api.github.com" if provider == "github" else "https://gitlab.com"
    host = input(f"Host/API base [{default_host}]: ").strip() or default_host
    while True:
        token = input(f"Access token for {provider}: ").strip()
        result = validate_git(provider, token, host)
        if result.get("ok"):
            return {
                "provider": provider,
                "host": result.get("host", host),
                "username": result.get("username", ""),
                "validated": True,
                "validated_at": result.get("validated_at", ""),
            }, {GIT_TOKEN_ENV[provider]: token}
        print(result.get("error", "Git validation failed."))
        if input("Retry? [Y/n]: ").strip().lower() == "n":
            return {
                "provider": provider,
                "host": host,
                "username": "",
                "validated": False,
                "validated_at": "",
            }, {}


def _configure_llm_services(default_services: dict) -> tuple[dict, dict[str, str]]:
    services = json.loads(json.dumps(default_services))
    env_values: dict[str, str] = {}
    for service_id, service in services.items():
        answer = input(f"Enable {service['label']}? [y/N]: ").strip().lower()
        if answer != "y":
            service["available"] = False
            service["validated"] = False
            continue
        if service.get("mode") == "manual_login":
            service["available"] = True
            service["validated"] = False
            service["manual_only"] = True
            continue
        token = input(f"API key for {service['label']}: ").strip()
        validation = validate_service(service_id, service, token)
        service.update({k: v for k, v in validation.items() if k not in {"ok", "error", "message"}})
        if validation.get("ok"):
            service["available"] = True
            service["validated"] = True
            if service.get("api_key_env"):
                env_values[service["api_key_env"]] = token
        else:
            print(validation.get("error") or validation.get("message") or "Validation failed.")
            service["available"] = False
            service["validated"] = False
    return services, env_values


def _select_role_defaults(settings: dict) -> dict:
    profiles = available_profiles(settings)
    if not profiles:
        return dict(settings.get("role_defaults", {}))
    for index, item in enumerate(profiles, start=1):
        print(f"{index}. {item['label']}")
    return {
        "developers": _pick_profile("Default model profile for the 3 developers", profiles),
        "qa": _pick_profile("Default model profile for QA", profiles, preferred_terms=("minimax", "flash", "turbo")),
        "orchestrator": _pick_profile("Default model profile for Orchestrator", profiles),
        "pm": _pick_profile("Default model profile for PM", profiles, preferred_terms=("flash", "turbo", "mini")),
    }


def _pick_profile(prompt: str, profiles: list[dict], preferred_terms: tuple[str, ...] = ()) -> str:
    default_index = 1
    if preferred_terms:
        for idx, item in enumerate(profiles, start=1):
            lowered = item["label"].lower()
            if any(term in lowered for term in preferred_terms):
                default_index = idx
                break
    raw = input(f"{prompt} [{default_index}]: ").strip()
    try:
        index = int(raw or str(default_index))
    except ValueError:
        index = default_index
    index = max(1, min(index, len(profiles)))
    return profiles[index - 1]["id"]


if __name__ == "__main__":
    raise SystemExit(main())
