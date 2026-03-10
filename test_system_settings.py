from pathlib import Path

from app_core import system_settings as system_settings_module


def test_available_model_profiles_only_include_enabled_services(tmp_path):
    original_settings_file = system_settings_module.SETTINGS_FILE
    original_env_file = system_settings_module.ENV_FILE
    system_settings_module.SETTINGS_FILE = Path(tmp_path) / "system_settings.json"
    system_settings_module.ENV_FILE = Path(tmp_path) / ".env"
    try:
        settings = system_settings_module.save_system_settings(
            {
                "llm_services": {
                    "openai_api": {
                        "available": True,
                        "models": ["gpt-4.1"],
                    },
                    "zai_api": {
                        "available": False,
                        "models": ["glm-4.7-flash"],
                    },
                }
            }
        )
        profiles = system_settings_module.list_available_model_profiles(settings)
        assert [item["id"] for item in profiles] == ["openai_api:gpt-4.1"]
    finally:
        system_settings_module.SETTINGS_FILE = original_settings_file
        system_settings_module.ENV_FILE = original_env_file


def test_upsert_env_vars_persists_values(tmp_path):
    original_settings_file = system_settings_module.SETTINGS_FILE
    original_env_file = system_settings_module.ENV_FILE
    system_settings_module.SETTINGS_FILE = Path(tmp_path) / "system_settings.json"
    system_settings_module.ENV_FILE = Path(tmp_path) / ".env"
    try:
        system_settings_module.upsert_env_vars({"OPENAI_API_KEY": "abc123", "ZAI_API_KEY": "zzz"})
        content = system_settings_module.ENV_FILE.read_text(encoding="utf-8")
        assert "OPENAI_API_KEY=abc123" in content
        assert "ZAI_API_KEY=zzz" in content
    finally:
        system_settings_module.SETTINGS_FILE = original_settings_file
        system_settings_module.ENV_FILE = original_env_file


def test_minimax_defaults_match_current_openai_compatible_endpoint():
    service = system_settings_module.DEFAULT_SYSTEM_SETTINGS["llm_services"]["minimax_api"]
    assert service["base_url"] == "https://api.minimax.io/v1"
    assert service["models"] == ["MiniMax-M2.5"]
