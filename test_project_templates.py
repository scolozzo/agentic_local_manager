from app_core.project_context import resolve_project_context
from app_core.project_templates import get_default_template_id, get_project_template, get_workflow_definition, list_project_templates


class FakeMemoryStore:
    def __init__(self, projects):
        self._projects = projects

    def project_list(self):
        return list(self._projects)


def test_default_template_is_software_delivery_default():
    assert get_default_template_id() == "software_delivery_default"


def test_templates_catalog_contains_initial_templates():
    template_ids = {template["id"] for template in list_project_templates()}
    assert {"software_delivery_default", "software_backend", "software_web", "software_mobile"} <= template_ids


def test_workflow_definition_matches_founder_template():
    workflow = get_workflow_definition("software_delivery_default")
    assert "Todo" in workflow["states"]
    assert "ReadyToMerge -> Merged" in workflow["transitions"]


def test_project_context_uses_selected_template():
    store = FakeMemoryStore([
        {
            "project_id": "ACME",
            "name": "Acme Platform",
            "description": "Reusable project",
            "template_id": "software_web",
            "git_dirs": {"BO": "C:/repos/acme-web"},
            "directives": {"dev-branch": "develop"},
        }
    ])
    context = resolve_project_context(store, "ACME")
    assert context["template_id"] == "software_web"
    assert context["template"]["suggested_preset"] == "web_team"
    assert "BO" in context["workflow"]["states"] or context["workflow"]["states"]


def test_project_context_falls_back_to_default_template():
    context = resolve_project_context(FakeMemoryStore([]), "UNKNOWN")
    assert context["template_id"] == get_project_template(None)["id"]
