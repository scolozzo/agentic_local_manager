# MVP Roadmap

This document tracks the evolution of the platform across the three original MVPs and the additional manager feature set that is now part of `develop`.

## General Goal

Generalize the original local multi-agent delivery system without losing:

- the local board execution model
- the existing PM, Orchestrator, Developer, and QA role split
- the default assignment behavior
- stack-aware prompts and agent specialization
- git-integrated software delivery as the primary supported workflow

## Migration Principles

- Preserve compatibility first, extend behavior second.
- Keep the local board as the default source of truth.
- Move hardcoded behavior into configuration where practical.
- Separate role, stack, specialization, project context, and team context.
- Keep platform-wide rules independent from project-specific state.

## MVP Sequence

### MVP 1

Prompt cleanup and configurable stack-specialized agents.

Reference:

- [mvp1-clean-prompts-and-stack-agents.md](/C:/Trabajo/AgenticLocalManager_Proyect/docs/mvp1-clean-prompts-and-stack-agents.md)

### MVP 2

Reusable teams and assignment generalization.

Reference:

- [mvp2-team-and-assignment-generalization.md](/C:/Trabajo/AgenticLocalManager_Proyect/docs/mvp2-team-and-assignment-generalization.md)

### MVP 3

Project templates and platform core.

Reference:

- [mvp3-project-templates-and-platform-core.md](/C:/Trabajo/AgenticLocalManager_Proyect/docs/mvp3-project-templates-and-platform-core.md)

## Execution Order

1. Complete MVP 1 while preserving the current team and prompt behavior.
2. Complete MVP 2 while preserving the assignment baseline.
3. Complete MVP 3 only after MVP 1 and MVP 2 are stable.

## Current Status

Updated on `2026-03-10`.

- `MVP 1`: completed and merged into `develop`
- `MVP 2`: completed and merged into `develop`
- `MVP 3`: completed and merged into `develop`
- additional manager feature set: completed and merged into `develop`
- Windows installer and launcher flow: implemented on `develop`
- project-first onboarding and subproject onboarding: implemented on `develop`

## Current System State In `develop`

The current system includes:

- layered prompt composition by role, stack, and specialization
- reusable assignment policy with the original local-board behavior as default
- reusable team presets by stack and substack
- project templates and project runtime restore
- sprint creation bound to `project + subproject + team`
- developer skill constraints based on the active sprint team
- platform-wide coding, git, and token optimization rules
- installer-driven global configuration for git and LLM services
- dashboard onboarding that blocks board usage until project and subproject setup exist

## Current Deliverable

At this point the platform provides:

- reusable base prompts and stack prompts
- configurable agents and reusable team presets
- project and subproject runtime context
- local storage-backed sprint execution
- project-aware dashboard filtering and restore
- placeholder-safe installer and launcher support for Windows

## Follow-up Direction

The main remaining platform-level gap is runtime provider abstraction. The installer and system settings already persist multi-provider choices, but PM, Developer, QA, and Orchestrator runtime loops still need deeper provider routing to fully exploit that configuration.

