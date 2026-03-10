import os

from pathlib import Path

from tools.install_support import _render_launcher_script
from tools.install_support import available_profiles, ensure_manual_login_fallback
from tools.install_support import write_json


def test_available_profiles_can_exclude_manual_login():
    settings = {
        "llm_services": {
            "chatgpt_login": {
                "label": "ChatGPT Login",
                "mode": "manual_login",
                "available": True,
                "models": ["chatgpt-login"],
            },
            "openai_api": {
                "label": "OpenAI API",
                "mode": "api",
                "available": True,
                "models": ["gpt-4.1"],
            },
        }
    }

    profiles = available_profiles(settings, include_manual=False)

    assert [item["id"] for item in profiles] == ["openai_api:gpt-4.1"]


def test_available_profiles_include_manual_login_when_requested():
    settings = {
        "llm_services": {
            "chatgpt_login": {
                "label": "ChatGPT Login",
                "mode": "manual_login",
                "available": True,
                "models": ["chatgpt-login"],
            }
        }
    }

    profiles = available_profiles(settings, include_manual=True)

    assert [item["id"] for item in profiles] == ["chatgpt_login:chatgpt-login"]


def test_manual_login_fallback_populates_role_defaults():
    settings = {"llm_services": {}, "role_defaults": {}}

    profile_id = ensure_manual_login_fallback(settings)

    assert profile_id == "chatgpt_login:chatgpt-login"
    assert settings["llm_services"]["chatgpt_login"]["available"] is True
    assert settings["llm_services"]["chatgpt_login"]["manual_only"] is True
    assert settings["role_defaults"] == {
        "developers": profile_id,
        "qa": profile_id,
        "orchestrator": profile_id,
        "pm": profile_id,
    }


def test_write_json_overwrites_existing_readonly_file(tmp_path):
    target = tmp_path / "config" / "system_settings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"old": true}\n', encoding="utf-8")
    os.chmod(target, 0o444)

    write_json(target, {"ok": True})

    assert '"ok": true' in target.read_text(encoding="utf-8").lower()


def test_render_launcher_script_includes_startup_precheck():
    script = _render_launcher_script(Path(r"C:\Agentic\Test"))

    assert 'set "REPO_DIR=C:\\Agentic\\Test"' in script
    assert 'tools\\startup_checks.py' in script
