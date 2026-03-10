from app_core.agent_config import compose_agent_prompt, get_agent, list_agents, load_agent_catalog
from app_core.agent_manager import explain_agent_eligibility, get_team_status, list_eligible_agents


def test_agents_use_v2_catalog():
    catalog = load_agent_catalog()
    assert catalog["version"] == 2
    assert catalog["default_preset"] == "default_software_team"
    assert catalog["agents"]


def test_default_team_contains_backend_dev_and_qa_shapes():
    agents = {agent["id"]: agent for agent in list_agents()}
    assert agents["dev1"]["role"] == "developer"
    assert agents["dev1"]["stack"] == "backend"
    assert agents["qa"]["role"] == "qa"
    assert agents["qa"]["specialization"] == "qa_backend"


def test_prompt_composition_includes_layers():
    prompt = compose_agent_prompt("dev1", runtime_context="RUNTIME_CONTEXT")
    assert "Developer" in prompt
    assert "Backend Stack" in prompt
    assert "BE Developer Agent" in prompt
    assert "RUNTIME_CONTEXT" in prompt


def test_agent_lookup_returns_prompt_paths():
    agent = get_agent("pm")
    assert agent is not None
    assert agent["base_prompt"] == "config/prompts/base/pm.md"


def test_team_status_defaults_to_default_software_team():
    status = get_team_status()
    assert status["active_preset"] == "default_software_team"
    assert any(preset["id"] == "backend_only_team" for preset in status["presets"])


def test_backend_only_team_filters_non_backend_agents():
    qa_agent = get_agent("qa")
    assert qa_agent is not None
    eligibility = explain_agent_eligibility(qa_agent, role="qa", stack_key="BACK", preset_name="backend_only_team")
    assert eligibility["eligible"] is True

    qa_for_bo = explain_agent_eligibility(qa_agent, role="qa", stack_key="BO", preset_name="backend_only_team")
    assert qa_for_bo["eligible"] is False
    assert any("preset excludes stack BO" in reason or "stack mismatch" in reason for reason in qa_for_bo["reasons"])


def test_list_eligible_agents_respects_role_and_stack():
    eligible = list_eligible_agents(role="developer", stack_key="BACK", preset_name="default_software_team")
    ids = {agent["id"] for agent in eligible}
    assert {"dev1", "dev2", "dev3"}.issubset(ids)
