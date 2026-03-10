# MVP 1 - Clean Prompts And Stack Agents

## Goal

Separate role rules, technical stack specialization, and runtime context while preserving the existing local board workflow.

## Problem Solved

The original agent prompts and agent configuration were tightly coupled to one specific system shape. That made it hard to:

- reuse agents across projects
- create specialized agents by stack
- keep prompts clean and maintainable
- scale the configuration model without duplicating instructions

## Expected Result

At the end of MVP 1, the system should define agents by:

- `role`
- `stack`
- `specialization`
- `provider`
- `model`

The final prompt should be composed from:

- base prompt by role
- stack prompt
- optional specialization prompt
- runtime task and project context

## Scope

- Create a layered prompt structure.
- Restructure [config/agents.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/agents.json) for prompt composition.
- Preserve the current team as the default preset.
- Allow new stack-specific agents for backend, web, and mobile.
- Maintain backward compatibility with the existing agent definition model.

## Exclusions

- assignment policy redesign
- board state redesign
- workflow redesign
- project template architecture

## Architecture Change

### Prompt structure

```text
config/prompts/
  base/
    pm.md
    developer.md
    qa.md
    orchestrator.md
  stacks/
    backend.md
    front_web.md
    front_mobile.md
    db.md
    qa_backend.md
    qa_front_web.md
    qa_front_mobile.md
  specializations/
    dev_back.md
    dev_bo_frontend.md
    dev_mob_android.md
    qa_back.md
    qa_bo.md
    qa_mob.md
```

### Agent model

Each agent now supports:

- `id`
- `name`
- `type`
- `role`
- `stack`
- `stack_key`
- `specialization`
- `base_prompt`
- `stack_prompt`
- `specialization_prompt`
- `provider`
- `model`
- `enabled`
- `removable`
- `login` when applicable

### Prompt composition rule

`final_prompt = base_prompt + stack_prompt + specialization_prompt + runtime_context`

## Acceptance Criteria

- Base prompts do not hardcode one specific project.
- Technical prompts preserve stack-specific guidance.
- The system can represent at least:
  - one backend developer
  - one web developer
  - one mobile developer
  - one backend QA
  - one web QA
  - one mobile QA
- No module depends on absolute prompt paths.
- The current team remains representable without behavioral regressions.

## Status

Status: `completed`

Implemented in `develop` with:

- layered prompt directories under [config/prompts](/C:/Trabajo/AgenticLocalManager_Proyect/config/prompts)
- centralized prompt composition in [app_core/agent_config.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/agent_config.py)
- versioned agent catalog in [config/agents.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/agents.json)
- dashboard visibility for role, stack, and specialization metadata

