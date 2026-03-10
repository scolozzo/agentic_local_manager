from __future__ import annotations

import json
from typing import Any

from app_core.memory_store import MemoryStore


def parse_plan(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _parse_markdown_plan(text)


def _parse_markdown_plan(text: str) -> dict[str, Any] | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    sprint_id = "sprint_imported"
    name = lines[0].lstrip("# ").strip()
    tasks = []
    for line in lines[1:]:
        if not line.startswith("-"):
            continue
        body = line[1:].strip()
        if ":" in body:
            task_id, summary = body.split(":", 1)
        else:
            task_id, summary = body, body
        tasks.append({"id": task_id.strip(), "summary": summary.strip(), "depends_on": [], "parallel": True})
    if not tasks:
        return None
    return {"sprint_id": sprint_id, "name": name, "stack": "BACK", "tasks": tasks}


def create_sprint_from_plan(plan: dict[str, Any], memory_store: MemoryStore) -> dict[str, int]:
    sprint_id = plan.get("sprint_id", "")
    name = plan.get("name", sprint_id)
    stack = plan.get("stack", "BACK")
    project_id = plan.get("project_id", "SEGURO")
    tasks_created = 0
    tasks_skipped = 0

    con = memory_store._connect()
    con.execute(
        "INSERT OR REPLACE INTO sprints (sprint_id, name, stack, project_id, status) VALUES (?, ?, ?, ?, COALESCE((SELECT status FROM sprints WHERE sprint_id = ?), 'active'))",
        (sprint_id, name, stack, project_id, sprint_id),
    )
    con.commit()
    con.close()

    for task in plan.get("tasks", []):
        task_id = task.get("id", "")
        if not task_id:
            continue
        if memory_store.board_get_task(task_id):
            tasks_skipped += 1
            continue
        memory_store.board_create_task(
            task_id=task_id,
            summary=task.get("summary", task_id),
            description=task.get("description", ""),
            state="Todo",
            priority=task.get("priority", "Medium"),
            stack=task.get("stack", stack),
            sprint_id=sprint_id,
            acceptance_criteria=task.get("acceptance_criteria", []),
            depends_on=task.get("depends_on", []),
            parallel=task.get("parallel", True),
        )
        tasks_created += 1
    return {"tasks_created": tasks_created, "tasks_skipped": tasks_skipped}


def describe_execution_plan(plan: dict[str, Any]) -> str:
    tasks = plan.get("tasks", [])
    lines = [f"- {task.get('id', '?')}: {task.get('summary', '')}" for task in tasks]
    return "\n".join(lines)
