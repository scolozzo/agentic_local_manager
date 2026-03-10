from __future__ import annotations


def normalize_stack_key(stack_key: str | None) -> str:
    return (stack_key or "").strip().upper()


def allowed_stacks(project_context: dict) -> list[str]:
    return [normalize_stack_key(stack) for stack in project_context.get("template", {}).get("allowed_stacks", []) if normalize_stack_key(stack)]


def default_stack_for_project(project_context: dict, fallback: str = "BACK") -> str:
    stacks = allowed_stacks(project_context)
    return stacks[0] if stacks else fallback


def validate_stack_for_project(project_context: dict, stack_key: str | None) -> tuple[bool, str]:
    candidate = normalize_stack_key(stack_key) or default_stack_for_project(project_context)
    allowed = allowed_stacks(project_context)
    if not allowed or candidate in allowed:
        return True, candidate
    return False, candidate


def resolve_stack_for_project(project_context: dict, stack_key: str | None) -> str:
    valid, candidate = validate_stack_for_project(project_context, stack_key)
    if valid:
        return candidate
    return default_stack_for_project(project_context)


def validate_project_configuration(project_context: dict, git_dirs: dict | None = None) -> list[str]:
    errors: list[str] = []
    template = project_context.get("template", {})
    allowed = set(allowed_stacks(project_context))
    configured_git_dirs = {normalize_stack_key(key): value for key, value in (git_dirs or project_context.get("git_dirs") or {}).items() if value}

    if allowed and configured_git_dirs:
        invalid = sorted(key for key in configured_git_dirs if key not in allowed)
        if invalid:
            errors.append(f"template disallows stacks: {', '.join(invalid)}")
        if not any(key in allowed for key in configured_git_dirs):
            errors.append("project has no repository configured for an allowed stack")

    required_roles = template.get("required_roles", [])
    if not required_roles:
        errors.append("template has no required roles defined")

    return errors
