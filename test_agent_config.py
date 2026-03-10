from app_core.agent_config import compose_agent_prompt, get_agent, list_agents, load_agent_catalog


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
