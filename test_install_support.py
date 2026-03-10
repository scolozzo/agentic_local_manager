from tools.install_support import available_profiles, ensure_manual_login_fallback


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
