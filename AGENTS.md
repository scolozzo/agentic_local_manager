# Project Workflow Rules For Codex

These rules apply to future Codex sessions working in this repository.

## Branching Rules

- Always start new feature work from `develop`.
- New feature branches must use this format:
  - `feature/<short_description>`
- New fix branches must use this format:
  - `fix/fix-<short_error_description>-<feature_branch_name>`
- A fix branch must always start from the branch where the issue was detected.
- Do not reuse old feature or fix branch names for unrelated work.

## Commit Rules

- After completing a task, always commit the changes on the current working branch.
- Do not leave completed task work uncommitted unless the user explicitly asks for that.
- Use concise commit messages that describe the change category and outcome.

## Fix Workflow

- When working on a fix branch:
  - implement the fix on the fix branch
  - run the relevant tests
  - report the results
  - ask the user for authorization before merging the fix into the local base branch
- After the user authorizes the merge:
  - merge the fix branch into its local base branch
  - push the updated base branch
  - push the fix branch as well
  - if the base branch is a feature branch, keep that feature branch updated remotely too

## Merge Rules

- Do not merge a fix branch into its base branch without explicit user approval.
- When a fix is merged, always mention which branch was the base branch.
- After any approved merge, push all relevant updated branches to remote.

## Default Execution Rule

- Unless the user explicitly requests a different flow, follow this branch discipline by default.

