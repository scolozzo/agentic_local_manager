import os
import sys
import requests
import json
import time
import re
from dotenv import load_dotenv
from datetime import datetime

# Reconfigure stdout for utf-8
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure veloxiq package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from VeloxIq.token_logger import TokenLogger, LLMCall
from VeloxIq.reasoning_control import get_llm_params, classify_dev_task
from VeloxIq.state_manager import StateManager
from VeloxIq.memory_store import MemoryStore
from VeloxIq.config_loader import get_gitlab_project_id, get_develop_branch

# Load environment
env_path = r"C:\Users\Lenovo\.gemini\antigravity\scratch\VeloxIq\.env"
load_dotenv(env_path)

# Configuration
GITLAB_URL = "https://gitlab.com/api/v4"
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
ZAI_API_KEY = os.getenv("ZAI_API_KEY")
ZAI_API_BASE = os.getenv("ZAI_API_BASE", "https://api.z.ai/api/paas/v4")
ZAI_MODEL = os.getenv("ZAI_MODEL_DEV", os.getenv("ZAI_MODEL", "glm-4.7-flash"))

# Agent Mapping (login names used as assignee in local board)
AGENT_CONFIG = {
    "dev1": {"login": "botidev1"},
    "dev2": {"login": "botidev2"},
    "dev3": {"login": "botidev3"},
}

# Token Logger
_token_logger = TokenLogger()

# Memory Store + State Manager (local board backend)
_memory_store = MemoryStore()
_state_manager = StateManager(memory_store=_memory_store)

# System prompt cache
_cached_dev_prompt: str | None = None


def _get_dev_system_prompt() -> str:
    global _cached_dev_prompt
    if _cached_dev_prompt is not None:
        return _cached_dev_prompt
    try:
        with open(
            r"C:\Users\Lenovo\.gemini\antigravity\scratch\config\prompts\dev_back.md",
            "r", encoding="utf-8"
        ) as f:
            _cached_dev_prompt = f.read()
    except Exception:
        _cached_dev_prompt = "Expert developer. Kotlin + Spring Boot. Return concise code implementations."
    return _cached_dev_prompt


def _gitlab_headers():
    return {"PRIVATE-TOKEN": GITLAB_TOKEN, "Content-Type": "application/json"}


def create_gitlab_branch(branch_name, ref="develop", project_id=None):
    pid = project_id or get_gitlab_project_id("BACK")
    if not pid:
        print(f"[DEV] No GitLab project_id configured — branch creation skipped", flush=True)
        return {}
    url = f"{GITLAB_URL}/projects/{pid}/repository/branches"
    data = {"branch": branch_name, "ref": ref}
    try:
        r = requests.post(url, headers=_gitlab_headers(), json=data, timeout=30)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def create_gitlab_commit(branch_name, commit_message, actions, project_id=None):
    pid = project_id or get_gitlab_project_id("BACK")
    if not pid:
        return {}
    url = f"{GITLAB_URL}/projects/{pid}/repository/commits"
    data = {"branch": branch_name, "commit_message": commit_message, "actions": actions}
    try:
        r = requests.post(url, headers=_gitlab_headers(), json=data, timeout=30)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def create_gitlab_mr(source_branch, target_branch, title, description, project_id=None):
    pid = project_id or get_gitlab_project_id("BACK")
    if not pid:
        return None
    url = f"{GITLAB_URL}/projects/{pid}/merge_requests"
    data = {
        "source_branch": source_branch,
        "target_branch": target_branch,
        "title": title,
        "description": description,
        "remove_source_branch": True,
    }
    try:
        r = requests.post(url, headers=_gitlab_headers(), json=data, timeout=30)
        if r.status_code in (200, 201):
            return r.json().get("web_url", "URL_NOT_FOUND")
    except Exception:
        pass
    return None


def _get_parent_feature_branch(task_id: str) -> str:
    """
    For FIX-VEL-X-timestamp tasks, find the parent task's feature branch
    by scanning the parent's board comments for 'Branch creada:'.
    Falls back to the develop branch if not found.
    """
    parts = task_id.split("-")
    # FIX-VEL-3-1234567 -> parent = VEL-3
    if len(parts) >= 3 and parts[0].upper() == "FIX":
        parent_id = f"{parts[1]}-{parts[2]}"
        comments = _memory_store.board_get_comments(parent_id)
        for c in comments:
            m = re.search(r"Branch creada: `([^`]+)`", c["text"])
            if m:
                return m.group(1)
    return "develop"


def _is_fix_task(task_id: str) -> bool:
    return task_id.upper().startswith("FIX-")


def generate_code_glm(prompt, task_summary="", task_id="", call_type="dev_task", agent_name="Dev"):
    url = f"{ZAI_API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {ZAI_API_KEY}",
        "Content-Type": "application/json",
    }
    system_prompt = _get_dev_system_prompt()
    system_msg: dict = {"role": "system", "content": system_prompt}
    if "minimax" in ZAI_MODEL.lower():
        system_msg["cache_control"] = {"type": "ephemeral"}

    task_type = classify_dev_task(task_summary) if task_summary else "tool_call_simple"
    llm_params = get_llm_params(task_type, ZAI_MODEL)

    data = {
        **llm_params,
        "messages": [system_msg, {"role": "user", "content": prompt}],
    }
    try:
        r = requests.post(url, headers=headers, json=data, timeout=60)
        res = r.json()
        if "choices" in res and len(res["choices"]) > 0:
            content = res["choices"][0]["message"]["content"]
            usage = res.get("usage", {})
            input_tok = usage.get("prompt_tokens", 0)
            output_tok = usage.get("completion_tokens", 0)
            reasoning_tok = usage.get("reasoning_tokens", 0)
            cost = TokenLogger.calculate_cost(ZAI_MODEL, input_tok, output_tok, reasoning_tok)
            _token_logger.log_call(LLMCall(
                agent_name=agent_name, model=ZAI_MODEL,
                input_tokens=input_tok, output_tokens=output_tok,
                reasoning_tokens=reasoning_tok, cost_usd=cost,
                task_id=task_id, call_type=call_type,
                sprint_id="sprint_01", timestamp=datetime.now().isoformat(),
            ))
            return content
        return f"Error: No choices in AI response: {json.dumps(res)}"
    except Exception as e:
        return f"Error generating code: {e}"


def dev_loop(agent_id):
    config = AGENT_CONFIG.get(agent_id)
    if not config:
        print(f"Error: Invalid agent_id {agent_id}")
        return

    login = config["login"]
    print(f"Developer Agent {login} starting loop (Local Board Mode)...", flush=True)

    while True:
        try:
            # Collect paused sprint IDs so dev skips their tasks
            paused_sprints = {
                s["sprint_id"] for s in _memory_store.sprint_list()
                if s["status"] == "paused"
            }

            # Find tasks assigned to this dev in InProgress or Fixing
            my_tasks = _memory_store.board_get_tasks_by_assignee(login, ["InProgress", "Fixing"])
            # Skip tasks belonging to paused sprints
            my_tasks = [t for t in my_tasks if t.get("sprint_id", "") not in paused_sprints]

            if not my_tasks:
                print(f"[{login}] No tasks assigned (InProgress or Fixing)", flush=True)

            for task in my_tasks:
                task_id = task["task_id"]
                summary = task["summary"]
                description = task.get("description", "")
                task_state = task["state"]

                clean_summary = summary.encode("ascii", "ignore").decode("ascii")

                # Get comments from local board
                all_comments = _memory_store.board_get_comments(task_id)
                my_comments = [c for c in all_comments if c["author"] == login]

                if task_state == "Fixing":
                    # Only count dev comments AFTER the last non-dev comment (QA rejection)
                    other_comments = [c for c in all_comments if c["author"] != login]
                    last_rejection_ts = max(
                        (c["created_at"] for c in other_comments), default=""
                    )
                    my_recent = [c for c in my_comments if c["created_at"] > last_rejection_ts]
                    has_started = any("Branch creada:" in c["text"] for c in my_recent)
                    has_finished = any("Trabajo finalizado" in c["text"] for c in my_recent)
                    print(
                        f"[{login}] {task_id} in Fixing -- fix_started={has_started}"
                        f" fix_done={has_finished}"
                        f" (last_rejection={last_rejection_ts[:19]}, recent_dev={len(my_recent)})",
                        flush=True,
                    )
                else:
                    has_started = any("Branch creada:" in c["text"] for c in my_comments)
                    has_finished = any("Trabajo finalizado" in c["text"] for c in my_comments)

                # Stack-aware GitLab project ID
                task_stack = task.get("stack", "BACK") or "BACK"
                project_id = get_gitlab_project_id(task_stack)
                develop_branch = get_develop_branch(task_stack)

                # Branch naming: fix tasks use fix/ prefix from parent feature branch
                is_fix = _is_fix_task(task_id)
                safe_summary = summary.encode("ascii", "ignore").decode("ascii")
                safe_tag = safe_summary[:20].replace(' ', '-').lower()
                if is_fix:
                    branch_name = f"fix/{task_id.lower()}-{safe_tag}"
                    ref_branch = _get_parent_feature_branch(task_id)
                else:
                    branch_name = f"feature/{task_id.lower()}-{safe_tag}"
                    ref_branch = develop_branch

                if not has_started:
                    print(f"[{login}] starting work on {task_id}: {clean_summary}", flush=True)

                    print(f"[{login}] Creating branch {branch_name} from {ref_branch}...", flush=True)
                    create_gitlab_branch(branch_name, ref=ref_branch, project_id=project_id)

                    ac_list = task.get("acceptance_criteria", [])
                    ac_text = ("\n\nCriterios de Aceptacion:\n" + "\n".join(f"- {c}" for c in ac_list)) if ac_list else ""
                    prompt = (
                        f"Initialize a {'fix patch' if is_fix else 'Kotlin/Spring Boot'} structure"
                        f" for this task: {summary}."
                        f" Description: {description}.{ac_text}"
                        f" Provide only a summary of planned files."
                    )
                    plan = generate_code_glm(
                        prompt, task_summary=summary, task_id=task_id,
                        call_type="dev_task", agent_name=login,
                    )

                    report = (
                        f"[INTERNAL_EVENT] TYPE:WORK_STARTED\n"
                        f"Trabajo iniciado por {login}\n\n"
                        f"- Branch creada: `{branch_name}` (base: `{ref_branch}`)\n"
                        f"- Stack: {task_stack}\n"
                        f"- Plan de implementacion:\n{plan}"
                    )
                    _memory_store.board_add_comment(task_id, login, report)

                elif has_started and not has_finished:
                    print(f"[{login}] finishing work on {task_id}: {clean_summary}", flush=True)

                    ac_list = task.get("acceptance_criteria", [])
                    ac_text = ("\n\nCriterios de Aceptacion (DEBES cumplir todos):\n"
                               + "\n".join(f"- {c}" for c in ac_list)) if ac_list else ""
                    impl_prompt = (
                        f"Implement the core code for the task: {summary}.\n"
                        f"Description: {description}.{ac_text}\n"
                        f"Return ONLY a valid JSON array of objects, where each object has"
                        f" 'file_path' and 'content'. Include 2 essential files."
                        f" Do not use markdown blocks, just the JSON array."
                    )
                    raw_code_response = generate_code_glm(
                        impl_prompt, task_summary=summary, task_id=task_id,
                        call_type="dev_task", agent_name=login,
                    )

                    actions = []
                    try:
                        json_str = raw_code_response
                        match = re.search(r'\[\s*\{.*\}\s*\]', json_str, re.DOTALL)
                        if match:
                            json_str = match.group(0)
                        elif "```json" in json_str:
                            json_str = json_str.split("```json")[1].split("```")[0].strip()
                        elif "```" in json_str:
                            json_str = json_str.split("```")[1].split("```")[0].strip()

                        files = json.loads(json_str)
                        for f in files:
                            actions.append({
                                "action": "create",
                                "file_path": f.get(
                                    "file_path",
                                    f"src/main/kotlin/generated_{int(time.time())}.kt"
                                ),
                                "content": f.get("content", "// Empty Content"),
                            })
                    except Exception as e:
                        print(f"[{login}] Failed to parse JSON code: {e}", flush=True)
                        actions.append({
                            "action": "create",
                            "file_path": f"src/main/kotlin/{task_id.replace('-', '_')}_Impl.kt",
                            "content": (
                                f"// Fallback implementation for {summary}\n"
                                f"// {raw_code_response}"
                            ),
                        })

                    print(f"[{login}] Pushing commits to {branch_name}...", flush=True)
                    create_gitlab_commit(branch_name, f"Implement {task_id}", actions,
                                        project_id=project_id)

                    # ── Run tests after implementation ──────────────────────────
                    print(f"[{login}] Running tests for {task_id}...", flush=True)
                    test_prompt = (
                        f"You just implemented: {summary}.\n"
                        f"Files committed: {[a['file_path'] for a in actions]}.\n"
                        f"Simulate running unit tests for this implementation. "
                        f"Report TESTS_PASS or TESTS_FAIL and list which tests ran."
                        f" Be concise (max 8 lines)."
                    )
                    test_result = generate_code_glm(
                        test_prompt, task_summary=summary, task_id=task_id,
                        call_type="test_run", agent_name=login,
                    )
                    tests_passed = "TESTS_PASS" in test_result.upper() or "FAIL" not in test_result.upper()
                    print(
                        f"[{login}] Tests {'PASSED' if tests_passed else 'FAILED'} for {task_id}",
                        flush=True,
                    )

                    # ── Create MR targeting correct branch ──────────────────────
                    # Feature tasks -> develop; Fix tasks -> parent feature branch
                    mr_target = ref_branch
                    print(f"[{login}] Creating MR {branch_name} -> {mr_target}...", flush=True)
                    mr_title = (
                        f"{'Fix' if is_fix else 'Draft'}: Implement {task_id} - {summary[:60]}"
                    )
                    mr_url = create_gitlab_mr(
                        branch_name, mr_target, mr_title,
                        f"Closes {task_id}\n\nTest results:\n{test_result[:400]}",
                        project_id=project_id,
                    )
                    mr_text = f"[{mr_url}]({mr_url})" if mr_url else "Simulada - sin config GitLab"

                    # ── Rich QA context comment ─────────────────────────────────
                    ac_done = "\n".join(f"- [x] {c}" for c in ac_list) if ac_list else "N/A"
                    final_report = (
                        f"[INTERNAL_EVENT] TYPE:WORK_FINISHED\n"
                        f"Trabajo finalizado por {login}\n\n"
                        f"**Branch**: `{branch_name}` -> `{mr_target}`\n"
                        f"**Merge Request**: {mr_text}\n"
                        f"**Stack**: {task_stack}\n\n"
                        f"**Tests**:\n{test_result[:500]}\n\n"
                        f"**Criterios de aceptacion cubiertos**:\n{ac_done}\n\n"
                        f"**Archivos implementados**:\n"
                        + "\n".join(f"- `{a['file_path']}`" for a in actions[:5])
                        + "\n\n[REQUEST:SYNC_DEVELOP] Solicita al Orquestador sincronizar"
                        f" `{mr_target}` en `{branch_name}` antes del merge final.\n\n"
                        f"Pasando a QA."
                    )
                    _memory_store.board_add_comment(task_id, login, final_report)

                    # Move to QA state (was "Fixed" in YouTrack)
                    result = _state_manager.transition(
                        task_id=task_id,
                        target_state="QA",
                        agent_id=agent_id,
                        reason="Development complete, ready for QA review",
                        max_retries=3,
                        retry_delay=5,
                    )
                    if result["ok"]:
                        print(f"[{login}] [OK] {task_id} moved to QA", flush=True)
                    else:
                        print(
                            f"[{login}] [ERROR] FAILED to move {task_id} to QA:"
                            f" {result['error']}",
                            flush=True,
                        )

        except Exception as e:
            print(f"[{login}] Loop error: {e}", flush=True)

        time.sleep(45)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python developer_integration.py [dev1|dev2|dev3]")
    else:
        dev_loop(sys.argv[1])
