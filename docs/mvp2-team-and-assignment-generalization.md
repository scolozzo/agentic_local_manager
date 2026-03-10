# MVP 2 - Team And Assignment Generalization

## Goal

Generalize team configuration and automatic task assignment while preserving the original local-board assignment behavior.

## Problem Solved

The original assignment behavior assumed a mostly fixed team layout. That limited:

- the number of developers per stack
- stack-specific QA scaling
- reusable team patterns across project types
- future assignment evolution without touching orchestration core logic

## Expected Result

At the end of MVP 2, the system should support:

- multiple developers per stack
- multiple QA roles per stack
- reusable team presets
- assignment eligibility by `role + stack + enabled`
- the original assignment strategy as the default policy

## Scope

- encapsulate the original assignment behavior
- make agent eligibility configurable
- support multiple reusable teams without hardcoding
- preserve the local board workflow

## Exclusions

- broad workflow redesign
- project template generalization
- full adapter decoupling

## Architecture Change

### Assignment policy

Introduce an assignment policy interface with:

- `LocalBoardDefaultAssignmentPolicy`

This policy preserves:

- dependency awareness
- fix-task priority
- sequential task handling
- enabled developer usage
- paused sprint exclusion

### Team model

Introduce reusable team presets such as:

- `default_software_team`
- `backend_only_team`
- `web_team`
- `mobile_team`

Each preset defines:

- included agents or eligibility scope
- supported stacks
- eligibility rules
- suggested role counts

## Acceptance Criteria

- assignment behavior remains equivalent to the existing workflow baseline
- the system supports multiple developers for the same stack
- the system supports stack-specific QA
- team selection is configuration-driven
- the baseline preset remains usable

## Status

Status: `completed`

Implemented in `develop` with:

- [app_core/assignment_policy.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/assignment_policy.py)
- reusable team presets in [config/agent_presets.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/agent_presets.json)
- configurable agent eligibility in [app_core/agent_manager.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/agent_manager.py)
- dashboard visibility for eligibility and stack activation

## Post-MVP Evolution

After the core MVP 2 work, the platform evolved further:

- the active team is no longer switched manually as a global setting
- teams are now assigned at sprint creation time
- sprint runtime derives the active team from the selected sprint
- developer creation is restricted by the active sprint team skill set

