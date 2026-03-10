from app_core.agent_manager import get_team_preset, list_team_presets, suggest_team_for_scope, validate_agent_for_team


def test_team_presets_can_be_filtered_by_stack_and_substack():
    teams = list_team_presets(stack_key="BO", substack="backoffice")
    team_ids = {team["id"] for team in teams}
    assert "web_backoffice_team" in team_ids
    assert "mobile_android_team" not in team_ids


def test_suggest_team_for_scope_returns_reusable_team():
    team = suggest_team_for_scope("MOB", "android")
    assert team is not None
    assert team["id"] == "mobile_android_team"


def test_validate_agent_for_team_rejects_unknown_skill():
    ok, error = validate_agent_for_team(
        {
            "id": "dev_custom",
            "type": "dev",
            "role": "developer",
            "stack": "backend",
            "stack_key": "BACK",
            "specialization": "front_web",
        },
        "backend_only_team",
    )
    assert ok is False
    assert "no permite el skill" in error


def test_validate_agent_for_team_accepts_allowed_skill():
    team = get_team_preset("web_backoffice_team")
    ok, error = validate_agent_for_team(
        {
            "id": "dev_bo",
            "type": "dev",
            "role": "developer",
            "stack": "front_web",
            "stack_key": "BO",
            "specialization": "front_web",
        },
        team["id"],
    )
    assert ok is True
    assert error == ""
