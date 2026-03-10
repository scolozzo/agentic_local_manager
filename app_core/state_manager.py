from __future__ import annotations

from app_core.memory_store import MemoryStore


class StateManager:
    def __init__(self, memory_store: MemoryStore | None = None) -> None:
        self.memory_store = memory_store or MemoryStore()

    def transition(self, task_id: str, target_state: str, agent_id: str, reason: str = "",
                   max_retries: int = 1, retry_delay: int = 0) -> dict:
        state = target_state
        assignee = None
        if target_state.startswith("InProgress assignee "):
            state = "InProgress"
            assignee = target_state.split("InProgress assignee ", 1)[1].strip()
        if assignee is not None:
            self.memory_store.board_assign_and_set_state(task_id, assignee, state)
        else:
            self.memory_store.board_update_state(task_id, state)
        return {"ok": True, "attempts": 1, "error": None, "final_state": state}

    def detect_deadlock(self, timeout_minutes: int = 5) -> list[dict]:
        return []

    def check_concurrent_assignment(self, task_id: str, agent_id: str) -> tuple[bool, str]:
        return False, ""
