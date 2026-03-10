import os
import re
import sys
import requests

# Ensure veloxiq package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from VeloxIq.git_tools import sync_feature_with_develop
from VeloxIq.token_logger import TokenLogger
from VeloxIq.state_manager import StateManager
from VeloxIq.memory_store import MemoryStore
from VeloxIq.config_loader import get_gitlab_project_id, get_develop_branch

# Load environment
from dotenv import load_dotenv
env_path = r"C:\Users\Lenovo\.gemini\antigravity\scratch\VeloxIq\.env"
load_dotenv(env_path)

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

_DONE_STATES = {"Merged", "ReadyToMerge"}

def _deps_met(task: dict) -> bool:
    """Return True if all task dependencies are in a done state (Merged/ReadyToMerge)."""
    deps = task.get("depends_on", [])
    if not deps:
        return True
    for dep_id in deps:
        dep_task = _memory_store.board_get_task(dep_id)
        if not dep_task or dep_task["state"] not in _DONE_STATES:
            return False
    return True


_FALLBACK_DEVS = ["botidev1", "botidev2", "botidev3"]

def _get_active_devs() -> list[str]:
    """Return board-assignee login names of enabled dev agents."""
    try:
        from VeloxIq.agent_manager import load_agents
        agents = load_agents()
        return [
            a.get("login", a["id"])
            for a in agents
            if a.get("type", "dev") == "dev" and a.get("enabled", True)
        ]
    except Exception:
        return _FALLBACK_DEVS


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

    # Priority fix tasks from memory store
    fix_tasks = _memory_store.get_fix_tasks_by_priority()
    fix_critical = [t for t in fix_tasks if t["priority"] == "Critical"]
    fix_grave    = [t for t in fix_tasks if t["priority"] == "Grave"]
    if fix_critical or fix_grave:
        print(f"Orchestrator: Found {len(fix_critical)} Critical + {len(fix_grave)} Grave Fix tasks", flush=True)

    # Busy devs = those with an InProgress task
    busy_devs = _memory_store.board_get_busy_assignees("InProgress")
    free_devs = [d for d in _get_active_devs() if d not in busy_devs]

    if not free_devs:
        print("Orchestrator: All developers are busy. Skipping assignment.", flush=True)
        return

    # Filter by active sprint if one exists
    active_sprint = _memory_store.sprint_get_active()
    sprint_id = active_sprint["sprint_id"] if active_sprint else ""

    # Get assignable tasks (Todo state, unassigned)
    todo_tasks = _memory_store.board_get_tasks_by_state("Todo", sprint_id=sprint_id)
    assignable = [t for t in todo_tasks if t.get("assignee", "") in ("", "orchestrator")]
    # Skip tasks from paused sprints
    assignable = [t for t in assignable if t.get("sprint_id", "") not in paused_sprints]

    # Filter out tasks whose dependencies are not yet Merged
    assignable = [t for t in assignable if _deps_met(t)]

    # Sort by priority (High > Medium > Low) then FIFO within same priority
    _PRIORITY_ORDER = {"High": 0, "Critical": 0, "Medium": 1, "Grave": 1, "Low": 2, "Mejora": 2}

    def task_order(t):
        prio = _PRIORITY_ORDER.get(t.get("priority", "Medium"), 1)
        try:
            seq = int(t["task_id"].split("-")[-1])
        except Exception:
            seq = 999
        return (prio, seq)

    assignable.sort(key=task_order)
    print(
        f"Orchestrator: {len(assignable)} Todo tasks, {len(busy_devs)} devs busy,"
        f" {len(free_devs)} free.",
        flush=True,
    )

    # Check if any sequential (parallel=False) task is already InProgress in this sprint
    sequential_in_progress = False
    if sprint_id:
        inprog = _memory_store.board_get_tasks_by_state("InProgress", sprint_id=sprint_id)
        sequential_in_progress = any(not t.get("parallel", True) for t in inprog)

    assigned_dev_index = 0
    assigned_count = 0

    def try_assign(task_id):
        nonlocal assigned_dev_index, assigned_count, sequential_in_progress
        if assigned_dev_index >= len(free_devs):
            return False

        task = _memory_store.board_get_task(task_id)
        is_parallel = task.get("parallel", True) if task else True

        # Sequential tasks: skip if another sequential task is already running
        if not is_parallel and sequential_in_progress:
            print(
                f"Orchestrator: [SKIP] {task_id} is sequential but another sequential task is running",
                flush=True,
            )
            return False

        dev_login = free_devs[assigned_dev_index]

        # Race condition check
        is_race, err = _state_manager.check_concurrent_assignment(task_id, "orchestrator")
        if is_race:
            print(f"Orchestrator: [WARN] Race condition on {task_id}: {err}", flush=True)
            return False

        result = _state_manager.transition(
            task_id=task_id,
            target_state=f"InProgress assignee {dev_login}",
            agent_id="orchestrator",
            reason=f"Auto-assigned to {dev_login}",
            max_retries=3,
        )
        if result["ok"]:
            notify_pm_event(task_id, "WORK_STARTED", f"Auto-asignado a {dev_login}")
            assigned_dev_index += 1
            assigned_count += 1
            if not is_parallel:
                sequential_in_progress = True
            return True
        return False

    # Priority 1: Critical fix tasks
    for ft in fix_critical[:len(free_devs)]:
        try_assign(ft["fix_task_id"])

    # Priority 2: Grave fix tasks
    for ft in fix_grave[:len(free_devs)]:
        try_assign(ft["fix_task_id"])

    # Priority 3: Normal Todo tasks (only if no unresolved critical/grave)
    unresolved = fix_critical[assigned_count:] + fix_grave[assigned_count:]
    if not unresolved:
        for task in assignable:
            if assigned_dev_index >= len(free_devs):
                break
            try_assign(task["task_id"])

    print(f"Orchestrator: Assigned {assigned_count} tasks this cycle", flush=True)


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

    busy_devs = _memory_store.board_get_busy_assignees("InProgress")
    free_devs = [d for d in _get_active_devs() if d not in busy_devs]

    _fix_assigned = 0

    for task in fixing_tasks:
        task_id = task["task_id"]
        fix_tasks_in_db = _memory_store.get_fix_tasks_for_task(task_id)

        if not fix_tasks_in_db:
            assignee = task.get("assignee", "")
            if assignee in _get_active_devs():
                print(
                    f"Orchestrator: {task_id} Fixing -> @{assignee} assigned, working directly",
                    flush=True,
                )
            else:
                # No fix sub-tasks, no dev -> revert to QA for review
                print(
                    f"Orchestrator: {task_id} Fixing with no Fix sub-tasks and no dev"
                    f" -> reverting to QA for review",
                    flush=True,
                )
                ok = _state_manager.transition(task_id, "QA", "orchestrator",
                                               reason="No Fix sub-tasks created, QA to review")
                if ok["ok"]:
                    notify_pm_event(
                        task_id, "FIXING_REVERTED",
                        f"No Fix tasks for {task_id}. Reverted to QA to create Fix tasks.",
                    )
                    print(f"Orchestrator: [OK] {task_id} reverted to QA", flush=True)
            continue

        # Check state of each Fix task in local board
        done_states = {"Merged", "ReadyToMerge", "Blocked"}
        pending_fix_ids = []
        all_done = True

        for ft in fix_tasks_in_db:
            ft_task = _memory_store.board_get_task(ft["fix_task_id"])
            if ft_task is None:
                # Fix task removed -> treat as done, clean up link
                _memory_store.delete_fix_task_link(ft["fix_task_id"])
                continue
            if ft_task["state"] not in done_states:
                all_done = False
                if ft_task["state"] == "Todo":
                    pending_fix_ids.append(ft["fix_task_id"])

        if all_done:
            print(
                f"Orchestrator: {task_id} -- all {len(fix_tasks_in_db)} Fix tasks done"
                f" (QA will advance to ReadyToMerge)",
                flush=True,
            )
        elif pending_fix_ids:
            for ft_id in pending_fix_ids:
                if not free_devs:
                    break
                dev = free_devs.pop(0)
                print(f"Orchestrator: Assigning Fix task {ft_id} (for {task_id}) to @{dev}", flush=True)
                result = _state_manager.transition(
                    task_id=ft_id,
                    target_state=f"InProgress assignee {dev}",
                    agent_id="orchestrator",
                    reason=f"Fix task for {task_id} -- auto-assigned",
                    max_retries=2,
                )
                if result["ok"]:
                    _fix_assigned += 1

    if _fix_assigned:
        print(f"Orchestrator: handle_fixing_tasks assigned {_fix_assigned} Fix tasks", flush=True)


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
