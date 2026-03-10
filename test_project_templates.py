from app_core.project_context import resolve_project_context
from app_core.project_templates import get_default_template_id, get_project_template, get_workflow_definition, list_project_templates
from app_core.project_validation import default_stack_for_project, resolve_stack_for_project, validate_project_configuration, validate_stack_for_project


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


def test_project_validation_detects_invalid_stack_configuration():
    context = {
        "template": {"allowed_stacks": ["BO"], "required_roles": ["pm", "developer"]},
        "git_dirs": {"BACK": "C:/repos/backend"},
    }
    errors = validate_project_configuration(context)
    assert any("template disallows stacks: BACK" in error for error in errors)


def test_project_stack_resolution_uses_template_default():
    context = {
        "template": {"allowed_stacks": ["MOB"], "required_roles": ["pm"]},
        "git_dirs": {},
    }
    ok, candidate = validate_stack_for_project(context, "BACK")
    assert ok is False
    assert candidate == "BACK"
    assert default_stack_for_project(context) == "MOB"
    assert resolve_stack_for_project(context, "BACK") == "MOB"
