# Agentic Local Manager

Local multi-agent project orchestration platform for software delivery workflows. The system combines a local SQLite board, reusable agent teams, project and subproject context, dashboard-based operations, and git-integrated execution loops.

## Overview

The platform coordinates these core roles:

- `PM`: receives requests, creates or imports execution plans, and manages sprint creation.
- `Orchestrator`: assigns tasks, tracks blockers, and manages merge progression.
- `Developers`: execute assigned work for the active sprint and subproject scope.
- `QA`: reviews completed work, creates fix tasks, and certifies outputs.

## Branch Policy

- `feature/gui_windows_installer` is a Windows-specific fork line.
- This branch must not be merged into `develop`.
- Only project-level fixes that are explicitly selected and re-applied without installer-specific files may be promoted to `develop`.

The current `develop` branch supports:

- reusable prompt composition by `role + stack + specialization`
- reusable team presets by `stack + substack`
- project templates and project runtime restore
- per-project subprojects with repo, skills, and default model profiles
- global platform rules that apply to every agent
- Windows installation and launcher flow

## Current Platform Model

The runtime model is:

`project -> subproject -> sprint -> team -> agents`

Key rules:

- a project must exist before the board is operational
- a project becomes operational after at least one subproject is created
- every sprint belongs to one project and one subproject
- every sprint is bound to one reusable team
- developers added to a sprint are limited to skills allowed by that sprint team
- PM is global; orchestrator is global by default; developer and QA defaults can be attached to each subproject

## Installation

### Windows installer

Use:

```powershell
.\Instalar_Agentic_Manager.ps1
```

The installer currently:

- lets the user choose the install directory
- copies the manager files to that directory
- validates GitHub or GitLab credentials
- allows enabling supported LLM services
- validates API-based services when possible
- writes placeholder-safe configuration and `.env`
- creates a desktop shortcut that points to the launcher

Files involved:

- [Instalar_Agentic_Manager.ps1](/C:/Trabajo/AgenticLocalManager_Proyect/Instalar_Agentic_Manager.ps1)
- [tools/install_windows.py](/C:/Trabajo/AgenticLocalManager_Proyect/tools/install_windows.py)
- [Iniciar_Agentic_Manager.cmd](/C:/Trabajo/AgenticLocalManager_Proyect/Iniciar_Agentic_Manager.cmd)

### Manual local start

```powershell
python dashboard.py
```

Then open `http://localhost:8888`.

## Configuration Layers

### Global platform settings

Global rules are stored in:

- [config/platform_settings.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/platform_settings.json)
- [config/system_settings.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/system_settings.json)

They include:

- coding policies
- git and branch policies
- token optimization rules
- validated git provider settings
- available LLM services
- default model profiles for global roles

### Environment placeholders

The repository does not store real secrets. Use:

- [.env.example](/C:/Trabajo/AgenticLocalManager_Proyect/.env.example)

Expected variables include:

- `GITHUB_TOKEN`
- `GITLAB_TOKEN`
- `OPENAI_API_KEY`
- `ZAI_API_KEY`
- `QWEN_API_KEY`
- `MINIMAX_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

### Agent catalog and team presets

Agent metadata and reusable teams are stored in:

- [config/agents.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/agents.json)
- [config/agent_presets.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/agent_presets.json)

## Dashboard Behavior

The dashboard lives in [dashboard.py](/C:/Trabajo/AgenticLocalManager_Proyect/dashboard.py).

Current behavior:

- if no project exists, the dashboard only exposes project creation
- if a project exists but has no subprojects, the dashboard guides the user into subproject creation
- once a subproject exists, the board and agent sections become available
- the dashboard restores the last active `project + sprint + team + subproject` context
- the dashboard exposes the current platform logic and global rules directly in the UI

## Project And Subproject Model

Projects now store:

- `project_id`
- `name`
- `description`
- `template_id`
- `git_dirs` as subproject-backed repo configuration

Subprojects currently define:

- label
- repo directory
- stack key
- substack
- skill set
- default developer model profile
- default QA model profile

Relevant modules:

- [app_core/project_context.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_context.py)
- [app_core/project_subprojects.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_subprojects.py)
- [app_core/project_templates.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_templates.py)
- [app_core/project_validation.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_validation.py)

## Core Modules

### Runtime and storage

- [app_core/memory_store.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/memory_store.py)
- [app_core/state_manager.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/state_manager.py)
- [app_core/sprint_manager.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/sprint_manager.py)
- [app_core/status_router.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/status_router.py)

### Agent configuration and policies

- [app_core/agent_config.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/agent_config.py)
- [app_core/agent_manager.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/agent_manager.py)
- [app_core/assignment_policy.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/assignment_policy.py)
- [app_core/platform_settings.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/platform_settings.py)
- [app_core/system_settings.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/system_settings.py)
- [app_core/provider_validation.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/provider_validation.py)

### Integrations

- [pm_integration.py](/C:/Trabajo/AgenticLocalManager_Proyect/pm_integration.py)
- [orchestrator_integration.py](/C:/Trabajo/AgenticLocalManager_Proyect/orchestrator_integration.py)
- [developer_integration.py](/C:/Trabajo/AgenticLocalManager_Proyect/developer_integration.py)
- [qa_integration.py](/C:/Trabajo/AgenticLocalManager_Proyect/qa_integration.py)
- [app_core/git_tools.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/git_tools.py)

## Current Limit

The installer and settings layer already support a broader provider model, but the runtime execution loops are still primarily wired around the current Z.AI and MiniMax paths. The system now persists the multi-provider selection model, but full runtime routing across every declared provider is still a follow-up step.

## Tests

Current validated test set:

```powershell
python -m pytest test_project_templates.py test_system_settings.py test_agent_config.py test_assignment_policy.py test_agent_teams.py
```

## Status

As of `2026-03-10`, `develop` includes:

- `MVP 1` completed
- `MVP 2` completed
- `MVP 3` completed
- manager feature set completed
- Windows installer and launcher added
- project-first and subproject-first onboarding added
