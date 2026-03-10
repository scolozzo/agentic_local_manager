# MVP 3 - Project Templates And Platform Core

## Goal

Turn the system into a reusable platform foundation for multiple software delivery project shapes while keeping software delivery as the primary supported template.

## Problem Solved

Even with agents and a local board already in place, the system was still centered on a single project pattern. What was missing:

- project templates
- reusable project context
- clearer separation between platform core and integrations
- project-aware workflow visibility

## Expected Result

At the end of MVP 3, the platform should support:

- versioned project templates
- project-aware workflow and stack validation
- reusable project runtime context
- a stable base for backend, web, and mobile delivery

## Scope

- introduce project templates
- map projects to templates
- preserve the local board as the default runtime store
- expose project and workflow context in the dashboard

## Exclusions

- full domain abstraction for every possible project type
- mandatory replacement of Telegram, GitLab, or the dashboard
- complex multi-tenant platform behavior

## Architecture Change

### Template catalog

The initial template catalog includes:

- `software_delivery_default`
- `software_backend`
- `software_web`
- `software_mobile`

Each template defines:

- workflow
- allowed stacks
- required roles
- suggested preset
- expected artifacts

### Project runtime context

Projects now resolve through:

- [app_core/project_templates.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_templates.py)
- [app_core/project_context.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_context.py)
- [app_core/project_validation.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_validation.py)

## Acceptance Criteria

- the system still runs with `software_delivery_default` without a functional regression
- backend, web, and mobile template variants exist
- project selection and workflow visibility are dashboard-visible
- local board storage remains the default source of truth

## Status

Status: `completed`

Implemented in `develop` with:

- versioned template catalog in [config/project_templates.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/project_templates.json)
- project runtime restore in [app_core/project_context.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_context.py)
- local storage support for project runtime in [app_core/memory_store.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/memory_store.py)
- dashboard-level project selection and template visibility in [dashboard.py](/C:/Trabajo/AgenticLocalManager_Proyect/dashboard.py)

## Post-MVP Evolution

After MVP 3 was merged, the platform added:

- persistent restore of the last active `project + sprint + team + subproject`
- subproject-aware repo configuration
- sprint binding to `project_id + subproject_id + team_id`
- reusable teams by stack and substack
- Windows installer and system-level LLM/git configuration persistence
- dashboard onboarding that hides the board and agents until project and subproject setup is complete
