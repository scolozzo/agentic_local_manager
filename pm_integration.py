import os
import sys
import requests
import json
from datetime import datetime

# Ensure veloxiq package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_core.token_logger import TokenLogger, LLMCall
from app_core.status_router import handle_pm_query, LocalBoardStatusClient
from app_core.memory_store import MemoryStore
from app_core.sprint_manager import parse_plan, create_sprint_from_plan, describe_execution_plan
from app_core.agent_config import compose_agent_prompt, get_agent_model, load_repo_env

# Load environment
load_repo_env()

# Configuration
ZAI_API_BASE       = os.getenv("ZAI_API_BASE", "https://api.z.ai/api/paas/v4")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
ZAI_MODEL_PM       = get_agent_model("pm", env_var="ZAI_MODEL_PM", default=os.getenv("ZAI_MODEL", "glm-4.7-flash"))

# Token Logger + Memory Store
_token_logger = TokenLogger()
_memory_store = MemoryStore()

# Status Router backed by local board (no HTTP)
_status_client = LocalBoardStatusClient()

def _get_system_prompt() -> str:
    return compose_agent_prompt("pm")


def block_task(task_id: str, reason: str):
    """Block a task in local board and notify via Telegram."""
    _memory_store.board_update_state(task_id, "Blocked")
    _memory_store.board_add_comment(
        task_id, "pm",
        f"[BLOCKED] {reason}"
    )
    send_telegram_alert(
        f"Tarea Bloqueada\nIssue: {task_id}\nRazon: {reason}"
    )


def send_telegram_alert(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram config missing, skipping alert.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def send_telegram_direct(chat_id: str, message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass


def import_plan_from_text(text: str, chat_id: str):
    """Parse a plan (JSON or Markdown) and create sprint + tasks in local board."""
    plan = parse_plan(text)
    if not plan:
        send_telegram_direct(chat_id, "No pude parsear el plan. Usa formato JSON o Markdown.")
        return
    result = create_sprint_from_plan(plan, _memory_store)
    summary = describe_execution_plan(plan)
    reply = (
        f"Sprint importado: *{plan['sprint_id']}* — {plan['name']}\n"
        f"Tareas creadas: {result['tasks_created']} | Ya existian: {result['tasks_skipped']}\n\n"
        f"{summary}"
    )
    send_telegram_direct(chat_id, reply[:4096])  # Telegram message limit


def listen_telegram_commands(last_id: int) -> int:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        r = requests.get(url, params={"offset": last_id + 1, "timeout": 30})
        if r.status_code != 200:
            return last_id
        updates = r.json().get("result", [])
        for update in updates:
            last_id = update["update_id"]
            msg = update.get("message", {})
            chat_id = str(msg["chat"]["id"]) if "chat" in msg else TELEGRAM_CHAT_ID

            if "text" in msg:
                process_text_command(msg["text"], chat_id)

            elif "document" in msg:
                # Plan file attachment (.json or .md)
                doc = msg["document"]
                fname = doc.get("file_name", "")
                if fname.endswith(".json") or fname.endswith(".md"):
                    file_path = get_telegram_file(doc["file_id"])
                    if file_path:
                        try:
                            content = open(file_path, encoding="utf-8").read()
                        except Exception:
                            content = open(file_path, encoding="latin-1").read()
                        finally:
                            import os as _os
                            if _os.path.exists(file_path):
                                _os.remove(file_path)
                        import_plan_from_text(content, chat_id)
                else:
                    send_telegram_direct(chat_id, f"Adjunto no reconocido: {fname}. Envia .json o .md")

            elif "voice" in msg or "audio" in msg:
                file_id = msg.get("voice", msg.get("audio")).get("file_id")
                audio_path = get_telegram_file(file_id)
                if audio_path:
                    text = transcribe_audio(audio_path)
                    if text:
                        process_text_command(text, chat_id)
        return last_id
    except Exception as e:
        print(f"Update Error: {e}")
        return last_id


def get_telegram_file(file_id: str):
    url_info = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
    try:
        r_info = requests.get(url_info, timeout=10).json()
        if r_info.get("ok"):
            file_path = r_info["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            local_path = f"tmp_audio_{file_id}.ogg"
            r_down = requests.get(download_url, timeout=30)
            with open(local_path, "wb") as f:
                f.write(r_down.content)
            return local_path
    except Exception:
        pass
    return None


def transcribe_audio(file_path: str):
    url = f"{ZAI_API_BASE}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {os.getenv('ZAI_API_KEY')}"}
    try:
        with open(file_path, "rb") as f:
            r = requests.post(url, headers=headers,
                              files={"file": f}, data={"model": "glm-asr-2512"}, timeout=60)
        if r.status_code == 200:
            return r.json().get("text")
    except Exception:
        pass
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
    return None


def call_pm_ai(user_message: str, task_id: str = "pm-general") -> str:
    url = f"{ZAI_API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('ZAI_API_KEY')}",
        "Content-Type": "application/json",
    }
    status_context = get_full_status_report()
    system_prompt = _get_system_prompt()
    system_msg: dict = {"role": "system", "content": system_prompt}
    if "minimax" in ZAI_MODEL_PM.lower():
        system_msg["cache_control"] = {"type": "ephemeral"}

    payload = {
        "model": ZAI_MODEL_PM,
        "messages": [
            system_msg,
            {
                "role": "user",
                "content": f"Contexto de Estado Actual:\n{status_context}\n\nMensaje del Usuario: {user_message}",
            },
        ],
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=120)
        if r.status_code == 200:
            res = r.json()
            content = res["choices"][0]["message"]["content"]
            usage = res.get("usage", {})
            input_tok = usage.get("prompt_tokens", 0)
            output_tok = usage.get("completion_tokens", 0)
            reasoning_tok = usage.get("reasoning_tokens", 0)
            cost = TokenLogger.calculate_cost(ZAI_MODEL_PM, input_tok, output_tok, reasoning_tok)
            _token_logger.log_call(LLMCall(
                agent_name="PM", model=ZAI_MODEL_PM,
                input_tokens=input_tok, output_tokens=output_tok,
                reasoning_tokens=reasoning_tok, cost_usd=cost,
                task_id=task_id, call_type="pm_query",
                sprint_id="sprint_01", timestamp=datetime.now().isoformat(),
            ))
            return content
        print(f"AI API Error ({r.status_code}): {r.text}")
    except requests.exceptions.Timeout:
        return "Timeout esperando respuesta de la IA. Intenta de nuevo."
    except Exception as e:
        return f"Error al conectar con la IA: {e}"
    return "Lo siento, tuve un problema procesando tu mensaje."


def handle_sprint_command(text: str, chat_id: str) -> bool:
    """
    Handle /sprint command to create sprint via dashboard API.
    Format:
      /sprint sprint_02 "Auth Flow"
      - VEL-1: Login endpoint
      - VEL-2: JWT validation (depends VEL-1)
      - VEL-3: Logout (parallel)
    """
    lines = text.strip().split('\n')
    first_line = lines[0].strip()

    if not first_line.startswith('/sprint'):
        return False

    # Parse first line: /sprint <sprint_id> "<name>"
    parts = first_line.split(None, 2)  # split on whitespace, max 3 parts
    if len(parts) < 3:
        send_telegram_direct(chat_id, "Formato: /sprint <id> \"<nombre>\"")
        return True

    sprint_id = parts[1]
    name = parts[2].strip('"').strip("'")

    # Parse tasks from remaining lines
    tasks = []
    for line in lines[1:]:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Format: "- VEL-1: summary" or "- VEL-1: summary (depends VEL-0, parallel: false)"
        if line.startswith('-'):
            line = line[1:].strip()
            task_id = ""
            summary = ""
            depends_on = []
            parallel = True

            # Extract task_id and summary
            if ':' in line:
                task_id, rest = line.split(':', 1)
                task_id = task_id.strip()

                # Check for metadata in parentheses
                if '(' in rest and ')' in rest:
                    summary = rest[:rest.index('(')].strip()
                    metadata = rest[rest.index('(')+1:rest.index(')')].strip().lower()

                    # Parse depends VEL-X format
                    if 'depend' in metadata:
                        deps_part = metadata.split('depend')[-1]
                        for dep_match in deps_part.split():
                            if dep_match.startswith('vel-') or dep_match.startswith('vel_'):
                                depends_on.append(dep_match.upper())

                    # Parse parallel: false
                    if 'parallel' in metadata and 'false' in metadata:
                        parallel = False
                else:
                    summary = rest.strip()
            else:
                task_id = line.strip()

            if task_id:
                tasks.append({
                    "id": task_id.upper(),
                    "summary": summary or task_id,
                    "depends_on": depends_on,
                    "parallel": parallel
                })

    if not tasks:
        send_telegram_direct(chat_id, "No se encontraron tareas. Formato:\n- VEL-1: descripcion")
        return True

    # Call dashboard API to create sprint
    try:
        import requests
        url = "http://localhost:8888/api/sprints/create"
        payload = {
            "sprint_id": sprint_id,
            "name": name,
            "stack": "BACK",  # Default to BACK, can be enhanced later
            "tasks": tasks
        }
        r = requests.post(url, json=payload, timeout=10)
        result = r.json()

        if result.get("ok"):
            task_list = "\n".join([f"  • {t['id']}: {t['summary']}" for t in tasks])
            reply = (
                f"Sprint creado: *{sprint_id}* — {name}\n"
                f"Tareas: {len(tasks)}\n\n"
                f"{task_list}"
            )
            send_telegram_direct(chat_id, reply)
            print(f"[PM] Sprint {sprint_id} creado con {len(tasks)} tareas")
        else:
            error = result.get("error", "Error desconocido")
            send_telegram_direct(chat_id, f"Error al crear sprint: {error}")
    except Exception as e:
        send_telegram_direct(chat_id, f"Error de API: {str(e)}")
        print(f"[PM] Error al crear sprint: {e}")

    return True


def process_text_command(text: str, chat_id: str):
    print(f"PM processing command: {text}")

    # NEW: Handle /sprint command (create sprint via dashboard)
    if text.strip().startswith('/sprint'):
        handle_sprint_command(text, chat_id)
        return

    # Tarea 4: Status Router — resolver sin LLM si es query de estado
    direct_response = handle_pm_query(text, _status_client, _token_logger)
    if direct_response is not None:
        send_telegram_direct(chat_id, direct_response)
        return

    # Escalar al LLM solo si el router no resolvió
    ai_response = call_pm_ai(text)

    if "[ACTION:REQUEST_DEEP_STATUS]" in ai_response:
        # Escribir evento en board comments del issue más reciente en InProgress
        in_progress = _memory_store.board_get_tasks_by_state("InProgress")
        if in_progress:
            tid = in_progress[0]["task_id"]
            _memory_store.board_add_comment(tid, "pm", "[REQUEST:DEEP_STATUS] Synthesis requested by user.")
        ai_response = ai_response.replace("[ACTION:REQUEST_DEEP_STATUS]", "").strip()

    send_telegram_direct(chat_id, ai_response)


def check_for_events():
    """Check board comments for internal events and notify PM via Telegram."""
    if not _MEMORY_DB_EXISTS():
        return
    import sqlite3
    from pathlib import Path
    db = Path(__file__).parent / "memory" / "veloxiq_memory.db"
    if not db.exists():
        return
    try:
        con = sqlite3.connect(db)
        # Get recent comments (last 50) with INTERNAL_EVENT
        rows = con.execute(
            "SELECT task_id, author, text, created_at FROM board_comments"
            " WHERE text LIKE '%[INTERNAL_EVENT]%'"
            " ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        con.close()
    except Exception:
        return

    sent = _load_event_sent()
    for task_id, author, text, created_at in rows:
        event_key = f"{task_id}:{created_at}"
        if event_key in sent:
            continue
        if "TYPE:WORK_STARTED" in text:
            details = text.split("DETAILS:")[-1].strip() if "DETAILS:" in text else text
            send_telegram_alert(f"PM Update: {details}")
            sent[event_key] = True
        elif "TYPE:DEADLOCK_ALERT" in text:
            send_telegram_alert(f"DEADLOCK en {task_id}: {text.split('DETAILS:')[-1][:200]}")
            sent[event_key] = True

    _save_event_sent(sent)


def _MEMORY_DB_EXISTS() -> bool:
    from pathlib import Path
    return (Path(__file__).parent / "memory" / "veloxiq_memory.db").exists()


_EVENT_SENT_FILE = None

def _load_event_sent() -> dict:
    from pathlib import Path
    f = Path(__file__).parent / "logs" / "pm_events_sent.json"
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    return {}

def _save_event_sent(sent: dict):
    from pathlib import Path
    f = Path(__file__).parent / "logs" / "pm_events_sent.json"
    f.parent.mkdir(exist_ok=True)
    f.write_text(json.dumps(sent))


def get_full_status_report() -> str:
    """Build a status report from the local board (no HTTP)."""
    summary = _status_client.get_sprint_summary()
    in_progress = _status_client.get_sprint_status()
    blocked = _status_client.get_blocked_tasks()
    return f"{summary}\n\n{in_progress}\n\n{blocked}"


if __name__ == "__main__":
    print("PM Agent active and listening (Local Board Mode)...", flush=True)
    send_telegram_alert("PM Online: Estoy listo y escuchando tus mensajes.")

    last_id = 0
    import time
    while True:
        last_id = listen_telegram_commands(last_id)
        check_for_events()
        time.sleep(10)
