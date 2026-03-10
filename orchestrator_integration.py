import os
import re
import sys
import requests

# Ensure veloxiq package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_core.git_tools import sync_feature_with_develop
from app_core.token_logger import TokenLogger
from app_core.state_manager import StateManager
from app_core.memory_store import MemoryStore
from app_core.config_loader import get_gitlab_project_id, get_develop_branch
from app_core.agent_config import load_repo_env
from app_core.assignment_policy import LocalBoardDefaultAssignmentPolicy

# Load environment
from dotenv import load_dotenv
load_repo_env()

# GitLab config (global fallback; per-stack config is in config/repos.json)
GITLAB_URL = "https://gitlab.com/api/v4"
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def _gl_headers():
    return {"PRIVATE-TOKEN": GITLAB_TOKEN}

# Token Logger
_token_logger = TokenLogger()

# Memory Store + State Manager (local board backend)
_memory_store = MemoryStore()
_state_manager = StateManager(memory_store=_memory_store)

_assignment_policy = LocalBoardDefaultAssignmentPolicy(
    memory_store=_memory_store,
    state_manager=_state_manager,
    notify_pm_event=lambda task_id, event_type, details: notify_pm_event(task_id, event_type, details),
)


def notify_pm_event(task_id, event_type, details):
    """Post internal event as local board comment."""
    _memory_store.board_add_comment(
        task_id, "orchestrator",
        f"[INTERNAL_EVENT] TYPE:{event_type} DETAILS:{details}"
    )


def _get_project_id_for_task(task: dict) -> str:
    """Resolve GitLab project_id from task's stack (falls back to env var)."""
    stack = (task.get("stack") or "BACK").upper()
    return get_gitlab_project_id(stack)


def _get_develop_branch_for_task(task: dict) -> str:
    stack = (task.get("stack") or "BACK").upper()
    return get_develop_branch(stack)


def _get_branch_for_task(task_id: str) -> str:
    """Find git branch for a task by scanning its board comments."""
    comments = _memory_store.board_get_comments(task_id)
    for c in reversed(comments):
        m = re.search(r'Branch creada?: `([^`]+)`', c.get("text", ""))
        if m:
            return m.group(1)
    safe = task_id.lower().replace(" ", "-")
    if task_id.upper().startswith("FIX-"):
        return f"fix/{safe}"
    return f"feature/{safe}"


def _is_fix_task(task_id: str) -> bool:
    return task_id.upper().startswith("FIX-")


def _get_parent_feature_branch(task_id: str) -> str:
    """For FIX- tasks, find parent task id and return its branch."""
    # FIX-VEL-3-1234567 -> parent is VEL-3
    parts = task_id.upper().split("-")
    if len(parts) >= 3:
        parent_id = f"{parts[1]}-{parts[2]}"
        return _get_branch_for_task(parent_id)
    return "develop"


def assign_pending_tasks():
    print("Orchestrator: Scanning backlog for autonomous assignment...", flush=True)

    # Collect paused sprint IDs so orchestrator skips their tasks
    paused_sprints = {
        s["sprint_id"] for s in _memory_store.sprint_list()
        if s.get("status") == "paused"
    }

    # Detect deadlocked tasks (from state_transitions audit log)
    stuck_tasks = _state_manager.detect_deadlock(timeout_minutes=5)
    for stuck in stuck_tasks:
        print(
            f"Orchestrator: [WARN] Deadlock: {stuck['task_id']} stuck on {stuck['state']}"
            f" for {stuck['duration_min']}m",
            flush=True,
        )
        notify_pm_event(
            stuck["task_id"], "DEADLOCK_ALERT",
            f"Task stuck on {stuck['state']} for {stuck['duration_min']}m by {stuck['agent_id']}.",
        )
        result = _state_manager.transition(
            task_id=stuck["task_id"],
            target_state="Blocked",
            agent_id="orchestrator",
            reason="Auto-blocked due to deadlock detection",
            max_retries=2,
        )
        if result["ok"]:
            print(f"Orchestrator: [OK] Blocked {stuck['task_id']}", flush=True)
        else:
            # If task doesn't exist in local board, remove from state tracking
            _memory_store.purge_task_transitions(stuck["task_id"])
            _memory_store.mark_task_not_found(stuck["task_id"], "orchestrator")

    stats = _assignment_policy.assign_pending_tasks()
    print(
        f"Orchestrator: {stats.get('todo', 0)} Todo tasks,"
        f" {stats.get('busy', 0)} devs busy, {stats.get('free', 0)} free.",
        flush=True,
    )
    print(f"Orchestrator: Assigned {stats.get('assigned', 0)} tasks this cycle", flush=True)


def handle_fixing_tasks():
    """
    Lifecycle manager for tasks in Fixing state.
    Rules:
    1. No Fix sub-tasks + dev assigned -> dev works directly (nothing to do)
    2. No Fix sub-tasks + no dev -> revert to QA so QA creates fix tasks
    3. Fix sub-tasks in Todo -> assign to free devs
    4. All Fix sub-tasks Merged -> log (QA advances to ReadyToMerge)
    """
    fixing_tasks = _memory_store.board_get_tasks_by_state("Fixing")
    if not fixing_tasks:
        return

    print(f"Orchestrator: handle_fixing_tasks -- checking {len(fixing_tasks)} Fixing tasks...", flush=True)
    stats = _assignment_policy.assign_fixing_tasks()
    if stats.get("assigned"):
        print(f"Orchestrator: handle_fixing_tasks assigned {stats['assigned']} Fix tasks", flush=True)


def handle_orchestration():
    """Merge tasks that are ReadyToMerge into their correct target branch."""
    ready_tasks = _memory_store.board_get_tasks_by_state("ReadyToMerge")

    for task in ready_tasks:
        task_id = task["task_id"]
        print(f"Orchestrator: Merging {task_id}...", flush=True)

        # Resolve branch and target based on task type and stack
        feature_branch = _get_branch_for_task(task_id)
        project_id = _get_project_id_for_task(task)

        if _is_fix_task(task_id):
            # Fix branches merge into their parent feature branch
            target_branch = _get_parent_feature_branch(task_id)
        else:
            # Feature branches merge into develop (stack-specific)
            target_branch = _get_develop_branch_for_task(task)

        print(
            f"Orchestrator: {task_id} -> merge '{feature_branch}' into '{target_branch}'"
            f" (project {project_id or 'local'})",
            flush=True,
        )

        if project_id and GITLAB_TOKEN:
            result = sync_feature_with_develop(
                feature_branch=feature_branch,
                project_id=project_id,
                gitlab_url=GITLAB_URL,
                token=GITLAB_TOKEN,
                telegram_bot_token=TELEGRAM_BOT_TOKEN,
                telegram_chat_id=TELEGRAM_CHAT_ID,
                target_branch=target_branch,
            )
            if result["status"] == "synced":
                notify_pm_event(
                    task_id, "MERGE_COMPLETED",
                    f"Merged '{feature_branch}' into '{target_branch}' for {task_id}.",
                )
                _state_manager.transition(task_id, "Merged", "orchestrator",
                                          reason=f"GitLab merge into {target_branch} completed")
                print(f"Orchestrator: {task_id} merged successfully.", flush=True)
            elif result["status"] == "conflicts":
                print(f"Orchestrator: {task_id} has conflicts -- notified via Telegram.", flush=True)
                _state_manager.transition(task_id, "Blocked", "orchestrator",
                                          reason="Merge conflicts detected")
            else:
                print(f"Orchestrator: {task_id} sync error: {result.get('error')}", flush=True)
        else:
            # No GitLab config: simulate merge
            notify_pm_event(
                task_id, "MERGE_COMPLETED",
                f"Simulated merge '{feature_branch}' into '{target_branch}' for {task_id}.",
            )
            _state_manager.transition(task_id, "Merged", "orchestrator",
                                      reason=f"Simulated merge into {target_branch}")
            print(f"Orchestrator: {task_id} marked as Merged (simulated).", flush=True)


def handle_blocked_tasks():
    """
    Recover Blocked tasks that were auto-blocked by deadlock detection (no human action needed).
    Rule:
      - If Blocked task's last comment is an [INTERNAL_EVENT] TYPE:DEADLOCK_ALERT from orchestrator
        AND no human comment exists after it → re-queue to Todo (clear assignee).
      - Tasks blocked manually by PM (comment by "pm") are NOT touched.
    """
    blocked = _memory_store.board_get_tasks_by_state("Blocked")
    if not blocked:
        return

    for task in blocked:
        task_id = task["task_id"]
        comments = _memory_store.board_get_comments(task_id)
        if not comments:
            continue

        last = comments[-1]
        # Only auto-recover if the last action was an orchestrator deadlock block
        if (last["author"] == "orchestrator"
                and "TYPE:DEADLOCK_ALERT" in last["text"]
                and "DETAILS:" in last["text"]):
            print(
                f"Orchestrator: [RECOVER] {task_id} was auto-blocked by deadlock"
                f" -> re-queuing to Todo",
                flush=True,
            )
            _memory_store.board_assign_and_set_state(task_id, "", "Todo")
            _memory_store.board_add_comment(
                task_id, "orchestrator",
                "[RECOVERY] Task re-queued to Todo after deadlock auto-block."
            )
            notify_pm_event(
                task_id, "TASK_RECOVERED",
                f"{task_id} recovered from Blocked (deadlock) -> Todo."
            )


if __name__ == "__main__":
    print("Orchestrator active (Local Board Mode)", flush=True)

    import time
    while True:
        try:
            handle_blocked_tasks()     # recover auto-blocked tasks first
            assign_pending_tasks()
            handle_fixing_tasks()
            handle_orchestration()
        except Exception as e:
            print(f"Loop error: {e}")
        time.sleep(30)
