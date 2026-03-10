from __future__ import annotations

from dataclasses import dataclass

from app_core.agent_manager import list_eligible_agents


_DONE_STATES = {"Merged", "ReadyToMerge"}
_PRIORITY_ORDER = {"High": 0, "Critical": 0, "Medium": 1, "Grave": 1, "Low": 2, "Mejora": 2}


@dataclass
class AssignmentPolicy:
    memory_store: object
    state_manager: object
    notify_pm_event: callable

    def assign_pending_tasks(self) -> dict:
        raise NotImplementedError

    def assign_fixing_tasks(self) -> dict:
        raise NotImplementedError


class LocalBoardDefaultAssignmentPolicy(AssignmentPolicy):
    def _deps_met(self, task: dict) -> bool:
        deps = task.get("depends_on", [])
        if not deps:
            return True
        for dep_id in deps:
            dep_task = self.memory_store.board_get_task(dep_id)
            if not dep_task or dep_task["state"] not in _DONE_STATES:
                return False
        return True

    def _stack_key_for_task(self, task: dict | None) -> str:
        return ((task or {}).get("stack") or "BACK").upper()

    def _task_order(self, task: dict) -> tuple[int, int]:
        prio = _PRIORITY_ORDER.get(task.get("priority", "Medium"), 1)
        try:
            seq = int(task["task_id"].split("-")[-1])
        except Exception:
            seq = 999
        return prio, seq

    def _collect_available_developers(self) -> tuple[list[str], set[str]]:
        busy_devs = set(self.memory_store.board_get_busy_assignees("InProgress"))
        available = []
        for agent in list_eligible_agents(role="developer"):
            login = agent.get("login", agent["id"])
            if login not in busy_devs:
                available.append(login)
        return available, busy_devs

    def _find_free_dev_for_stack(self, stack_key: str, free_devs: list[str]) -> str | None:
        eligible = [
            agent.get("login", agent["id"])
            for agent in list_eligible_agents(role="developer", stack_key=stack_key)
        ]
        for login in free_devs:
            if login in eligible:
                return login
        return None

    def assign_pending_tasks(self) -> dict:
        paused_sprints = {
            sprint["sprint_id"] for sprint in self.memory_store.sprint_list()
            if sprint.get("status") == "paused"
        }

        fix_tasks = self.memory_store.get_fix_tasks_by_priority()
        fix_critical = [task for task in fix_tasks if task["priority"] == "Critical"]
        fix_grave = [task for task in fix_tasks if task["priority"] == "Grave"]

        free_devs, busy_devs = self._collect_available_developers()
        if not free_devs:
            return {"assigned": 0, "busy": len(busy_devs), "free": 0}

        active_sprint = self.memory_store.sprint_get_active()
        sprint_id = active_sprint["sprint_id"] if active_sprint else ""
        todo_tasks = self.memory_store.board_get_tasks_by_state("Todo", sprint_id=sprint_id)
        assignable = [task for task in todo_tasks if task.get("assignee", "") in ("", "orchestrator")]
        assignable = [task for task in assignable if task.get("sprint_id", "") not in paused_sprints]
        assignable = [task for task in assignable if self._deps_met(task)]
        assignable.sort(key=self._task_order)

        sequential_in_progress = False
        if sprint_id:
            in_progress = self.memory_store.board_get_tasks_by_state("InProgress", sprint_id=sprint_id)
            sequential_in_progress = any(not task.get("parallel", True) for task in in_progress)

        assigned_count = 0

        def try_assign(task_id: str) -> bool:
            nonlocal assigned_count, sequential_in_progress
            task = self.memory_store.board_get_task(task_id)
            if not task:
                return False

            if not task.get("parallel", True) and sequential_in_progress:
                return False

            dev_login = self._find_free_dev_for_stack(self._stack_key_for_task(task), free_devs)
            if not dev_login:
                return False

            is_race, _ = self.state_manager.check_concurrent_assignment(task_id, "orchestrator")
            if is_race:
                return False

            result = self.state_manager.transition(
                task_id=task_id,
                target_state=f"InProgress assignee {dev_login}",
                agent_id="orchestrator",
                reason=f"Auto-assigned to {dev_login}",
                max_retries=3,
            )
            if not result["ok"]:
                return False

            self.notify_pm_event(task_id, "WORK_STARTED", f"Auto-asignado a {dev_login}")
            free_devs.remove(dev_login)
            assigned_count += 1
            if not task.get("parallel", True):
                sequential_in_progress = True
            return True

        for fix_task in fix_critical:
            if not free_devs:
                break
            try_assign(fix_task["fix_task_id"])

        for fix_task in fix_grave:
            if not free_devs:
                break
            try_assign(fix_task["fix_task_id"])

        unresolved = [
            fix_task for fix_task in [*fix_critical, *fix_grave]
            if (self.memory_store.board_get_task(fix_task["fix_task_id"]) or {}).get("state") == "Todo"
        ]
        if not unresolved:
            for task in assignable:
                if not free_devs:
                    break
                try_assign(task["task_id"])

        return {"assigned": assigned_count, "busy": len(busy_devs), "free": len(free_devs), "todo": len(assignable)}

    def assign_fixing_tasks(self) -> dict:
        fixing_tasks = self.memory_store.board_get_tasks_by_state("Fixing")
        if not fixing_tasks:
            return {"assigned": 0, "fixing": 0}

        free_devs, _ = self._collect_available_developers()
        fix_assigned = 0
        active_dev_logins = {agent.get("login", agent["id"]) for agent in list_eligible_agents(role="developer")}

        for task in fixing_tasks:
            task_id = task["task_id"]
            fix_tasks_in_db = self.memory_store.get_fix_tasks_for_task(task_id)

            if not fix_tasks_in_db:
                assignee = task.get("assignee", "")
                if assignee not in active_dev_logins:
                    ok = self.state_manager.transition(
                        task_id,
                        "QA",
                        "orchestrator",
                        reason="No Fix sub-tasks created, QA to review",
                    )
                    if ok["ok"]:
                        self.notify_pm_event(
                            task_id,
                            "FIXING_REVERTED",
                            f"No Fix tasks for {task_id}. Reverted to QA to create Fix tasks.",
                        )
                continue

            done_states = {"Merged", "ReadyToMerge", "Blocked"}
            pending_fix_ids = []
            all_done = True

            for fix_task in fix_tasks_in_db:
                linked_task = self.memory_store.board_get_task(fix_task["fix_task_id"])
                if linked_task is None:
                    self.memory_store.delete_fix_task_link(fix_task["fix_task_id"])
                    continue
                if linked_task["state"] not in done_states:
                    all_done = False
                    if linked_task["state"] == "Todo":
                        pending_fix_ids.append(fix_task["fix_task_id"])

            if all_done:
                continue

            for fix_task_id in pending_fix_ids:
                fix_task = self.memory_store.board_get_task(fix_task_id)
                dev_login = self._find_free_dev_for_stack(self._stack_key_for_task(fix_task), free_devs)
                if not dev_login:
                    break
                result = self.state_manager.transition(
                    task_id=fix_task_id,
                    target_state=f"InProgress assignee {dev_login}",
                    agent_id="orchestrator",
                    reason=f"Fix task for {task_id} -- auto-assigned",
                    max_retries=2,
                )
                if result["ok"]:
                    free_devs.remove(dev_login)
                    fix_assigned += 1

        return {"assigned": fix_assigned, "fixing": len(fixing_tasks)}
