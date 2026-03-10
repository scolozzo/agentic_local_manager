import os
import sys
import requests
import json
import time
from dotenv import load_dotenv
from datetime import datetime

# Ensure veloxiq package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from VeloxIq.token_logger import TokenLogger, LLMCall
from VeloxIq.reasoning_control import get_llm_params, classify_qa_task
from VeloxIq.memory_store import MemoryStore
from VeloxIq.state_manager import StateManager

# Load environment
env_path = r"C:\Users\Lenovo\.gemini\antigravity\scratch\VeloxIq\.env"
load_dotenv(env_path)

# Z.AI config
ZAI_API_KEY = os.getenv("ZAI_API_KEY")
ZAI_API_BASE = os.getenv("ZAI_API_BASE", "https://api.z.ai/api/paas/v4")

# MiniMax config
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
MINIMAX_API_BASE = os.getenv("MINIMAX_API_BASE", "https://api.minimax.chat/v1")

QA_MODEL = os.getenv("ZAI_MODEL_QA", "minimax-m2.5-standard")

if QA_MODEL.startswith("minimax"):
    _QA_API_BASE = MINIMAX_API_BASE
    _QA_API_KEY = MINIMAX_API_KEY or ZAI_API_KEY
else:
    _QA_API_BASE = ZAI_API_BASE
    _QA_API_KEY = ZAI_API_KEY

LOGIN = "botiQA"

# Token Logger
_token_logger = TokenLogger()

# Memory Store + State Manager (local board backend)
_memory_store = MemoryStore()
_state_manager = StateManager(memory_store=_memory_store)

# System prompt cache
_cached_qa_prompt: str | None = None


def _get_qa_system_prompt() -> str:
    global _cached_qa_prompt
    if _cached_qa_prompt is not None:
        return _cached_qa_prompt
    try:
        with open(
            r"C:\Users\Lenovo\.gemini\antigravity\scratch\config\prompts\qa_back.md",
            "r", encoding="utf-8"
        ) as f:
            _cached_qa_prompt = f.read()
    except Exception:
        _cached_qa_prompt = "Expert QA Engineer. Reply concisely with APPROVED or REJECTED."
    return _cached_qa_prompt


def parse_qa_review_for_issues(qa_review: str) -> list[dict]:
    """Parse QA review and extract issues with priorities."""
    issues = []
    current_priority = "Mejora"
    for line in qa_review.split('\n'):
        line = line.strip()
        if "[CRITICAL]" in line.upper():
            current_priority = "Critical"
            line = line.replace("[CRITICAL]", "").replace("[critical]", "").strip()
        elif "[GRAVE]" in line.upper():
            current_priority = "Grave"
            line = line.replace("[GRAVE]", "").replace("[grave]", "").strip()
        elif "[MEJORA]" in line.upper():
            current_priority = "Mejora"
            line = line.replace("[MEJORA]", "").replace("[mejora]", "").strip()
        if line and line.startswith("- "):
            issues.append({"title": line[2:], "priority": current_priority})

    if not issues:
        issues.append({"title": "General fixes required", "priority": "Grave"})
    return issues


def create_fix_task(fixing_task_id, issue_title, issue_description, priority="Mejora"):
    """Create a Fix task in the local board linked to the Fixing task."""
    fix_task_id = f"FIX-{fixing_task_id}-{int(time.time())}"

    _memory_store.board_create_task(
        task_id=fix_task_id,
        summary=f"Fix {fixing_task_id}: {issue_title}",
        description=issue_description,
        state="Todo",
        priority=priority,
    )
    # Register link so orchestrator can assign
    _memory_store.save_fix_task_link(
        fix_task_id=fix_task_id,
        fixing_task_id=fixing_task_id,
        priority=priority,
        original_state="QA",
    )
    print(f"[QA] Created Fix task {fix_task_id} (Priority: {priority})", flush=True)
    return fix_task_id


def generate_qa_review(issue_summary, issue_details, task_id="", acceptance_criteria=None):
    url = f"{_QA_API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {_QA_API_KEY}",
        "Content-Type": "application/json",
    }
    ac_list = acceptance_criteria or []
    ac_text = ""
    if ac_list:
        ac_text = "\n\nCriterios de Aceptacion (verifica CADA UNO antes de decidir):\n"
        ac_text += "\n".join(f"- {c}" for c in ac_list)
    prompt = (
        f"Perform a QA review for the implementation of this task: {issue_summary}.\n"
        f"Implementation notes: {issue_details}{ac_text}\n"
        f"Decide if it's 'APPROVED' or 'REJECTED'. "
        f"If REJECTED, tag each issue as [CRITICAL], [GRAVE] or [MEJORA]."
    )
    system_prompt = _get_qa_system_prompt()
    system_msg: dict = {"role": "system", "content": system_prompt}
    if QA_MODEL.startswith("minimax"):
        system_msg["cache_control"] = {"type": "ephemeral"}

    task_type = classify_qa_task(is_full_review=True)
    llm_params = get_llm_params(task_type, QA_MODEL)

    data = {**llm_params, "messages": [system_msg, {"role": "user", "content": prompt}]}

    try:
        r = requests.post(url, headers=headers, json=data, timeout=60)
        res = r.json()
        if "choices" in res and len(res["choices"]) > 0:
            content = res["choices"][0]["message"]["content"]
            usage = res.get("usage", {})
            input_tok = usage.get("prompt_tokens", 0)
            output_tok = usage.get("completion_tokens", 0)
            reasoning_tok = usage.get("reasoning_tokens", 0)
            cost = TokenLogger.calculate_cost(QA_MODEL, input_tok, output_tok, reasoning_tok)
            _token_logger.log_call(LLMCall(
                agent_name="QA", model=QA_MODEL,
                input_tokens=input_tok, output_tokens=output_tok,
                reasoning_tokens=reasoning_tok, cost_usd=cost,
                task_id=task_id, call_type="qa_review",
                sprint_id="sprint_01", timestamp=datetime.now().isoformat(),
            ))
            return content
        return f"Error: No choices in AI response: {json.dumps(res)}"
    except Exception as e:
        return f"Error analyzing: {e}"


def check_fixing_tasks_completion():
    """
    Check all Fixing tasks. If ALL linked Fix tasks are in done states,
    advance the Fixing task to ReadyToMerge.
    """
    fixing_tasks = _memory_store.board_get_tasks_by_state("Fixing")
    if not fixing_tasks:
        return

    done_states = {"Merged", "ReadyToMerge", "Blocked"}

    for task in fixing_tasks:
        task_id = task["task_id"]
        fix_tasks_in_db = _memory_store.get_fix_tasks_for_task(task_id)

        if not fix_tasks_in_db:
            continue

        all_done = True
        pending_count = 0

        for ft in fix_tasks_in_db:
            ft_task = _memory_store.board_get_task(ft["fix_task_id"])
            if ft_task is None:
                # Fix task was deleted -> remove link, treat as done
                _memory_store.delete_fix_task_link(ft["fix_task_id"])
                continue
            if ft_task["state"] not in done_states:
                all_done = False
                pending_count += 1

        if all_done:
            print(
                f"[QA] {task_id}: all {len(fix_tasks_in_db)} Fix tasks done"
                f" -> advancing to ReadyToMerge",
                flush=True,
            )
            result = _state_manager.transition(
                task_id=task_id,
                target_state="ReadyToMerge",
                agent_id="qa",
                reason=f"All {len(fix_tasks_in_db)} Fix tasks merged.",
                max_retries=3,
            )
            if result["ok"]:
                _memory_store.board_add_comment(
                    task_id, LOGIN,
                    f"[QA] All {len(fix_tasks_in_db)} Fix tasks verified as Merged.\n"
                    f"Advancing to ReadyToMerge for Orchestrator to finalize.",
                )
            else:
                print(
                    f"[QA] [WARN] Failed to advance {task_id} to ReadyToMerge:"
                    f" {result['error']}",
                    flush=True,
                )
        else:
            print(
                f"[QA] {task_id}: {pending_count}/{len(fix_tasks_in_db)} Fix tasks still pending",
                flush=True,
            )


def qa_loop():
    print(f"QA Agent {LOGIN} starting loop (Local Board Mode)...", flush=True)

    while True:
        try:
            # Review tasks in "QA" state (was "Fixed" in YouTrack)
            qa_tasks = _memory_store.board_get_tasks_by_state("QA")

            for task in qa_tasks:
                task_id = task["task_id"]
                print(f"[QA] Analyzing {task_id}...", flush=True)

                # Find "Trabajo finalizado" comment for implementation details
                comments = _memory_store.board_get_comments(task_id)
                details = "No details found."
                for c in comments:
                    if "Trabajo finalizado" in c["text"]:
                        details = c["text"]

                review = generate_qa_review(
                    task["summary"], details, task_id=task_id,
                    acceptance_criteria=task.get("acceptance_criteria", []),
                )
                is_approved = "APPROVED" in review.upper()

                report = f"QA Review por {LOGIN}\n\n{review}"
                _memory_store.board_add_comment(task_id, LOGIN, report)

                # Persist QA result
                _memory_store.save_qa_result(
                    task_id=task_id,
                    issues=[] if is_approved else [review],
                    passed=is_approved,
                )

                if is_approved:
                    print(f"[QA] Approving {task_id} -> ReadyToMerge", flush=True)
                    result = _state_manager.transition(
                        task_id=task_id,
                        target_state="ReadyToMerge",
                        agent_id="qa",
                        reason="QA review passed - ready for merge",
                        max_retries=3,
                    )
                    if not result["ok"]:
                        print(
                            f"[QA] [WARN] Failed to mark {task_id} as ReadyToMerge:"
                            f" {result['error']}",
                            flush=True,
                        )
                else:
                    print(f"[QA] Rejecting {task_id} -> Fixing + creating Fix tasks", flush=True)
                    result = _state_manager.transition(
                        task_id=task_id,
                        target_state="Fixing",
                        agent_id="qa",
                        reason="QA review failed - issues found",
                        max_retries=3,
                    )
                    if not result["ok"]:
                        print(
                            f"[QA] [WARN] Failed to mark {task_id} as Fixing:"
                            f" {result['error']}",
                            flush=True,
                        )

                    # Create Fix tasks in local board
                    qa_issues = parse_qa_review_for_issues(review)
                    fix_count = 0
                    for qa_issue in qa_issues:
                        fix_desc = (
                            f"Fix required for {task_id}\n\n"
                            f"Issue: {qa_issue['title']}\n\n"
                            f"Full QA Review:\n{review}"
                        )
                        fix_id = create_fix_task(
                            fixing_task_id=task_id,
                            issue_title=qa_issue["title"],
                            issue_description=fix_desc,
                            priority=qa_issue["priority"],
                        )
                        if fix_id:
                            fix_count += 1
                        else:
                            print(f"[QA] [WARN] Failed to create Fix task for {task_id}", flush=True)

                    print(f"[QA] [OK] Created {fix_count} Fix tasks for {task_id}", flush=True)

            # Check if any Fixing tasks are fully resolved
            check_fixing_tasks_completion()

        except Exception as e:
            print(f"[QA] Loop error: {e}", flush=True)

        time.sleep(45)


if __name__ == "__main__":
    qa_loop()
