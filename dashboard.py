#!/usr/bin/env python3
"""
dashboard.py — Panel de control VeloxIq
python dashboard.py → http://localhost:8888
"""

import os, sys, json, sqlite3, threading, webbrowser, subprocess, cgi
import re
import unicodedata
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from urllib.parse import urlparse, parse_qs

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from app_core.agent_manager import (
    load_agents, load_specializations, get_log, get_current_task,
    get_agent, start_agent, stop_agent, start_all, stop_all, is_running,
    add_agent, remove_agent, system_running, get_team_status_for,
    create_team_preset, get_agents_with_eligibility, get_team_preset, list_team_presets, set_agents_enabled_for_stack,
    suggest_team_for_scope, update_agent, validate_agent_for_team,
    set_agent_enabled,
    get_schedule, save_schedule, start_scheduler,
)
from app_core.alert_manager import get_active_alerts, clear_alert
from app_core.memory_store import MemoryStore
from app_core.project_context import require_project_context, resolve_project_context, set_active_project_id
from app_core.platform_settings import load_platform_settings, save_platform_settings
from app_core.project_subprojects import (
    default_skills_for_scope,
    get_subproject_definition,
    list_substack_options,
    normalize_project_subprojects,
    upsert_subproject_config,
)
from app_core.project_templates import get_workflow_definition, get_project_template, list_project_templates
from app_core.project_validation import validate_project_configuration, resolve_stack_for_project
from app_core.system_settings import list_available_model_profiles, load_system_settings

BASE_DIR = Path(__file__).parent
PORT     = 8888


def _preview_project_context(
    *,
    project_id: str,
    name: str,
    description: str,
    template_id: str,
    git_dirs: dict,
    directives: dict,
) -> dict:
    template = get_project_template(template_id)
    context = {
        "project_id": project_id,
        "name": name,
        "description": description,
        "template_id": template_id,
        "template": template,
        "workflow": get_workflow_definition(template_id),
        "git_dirs": git_dirs,
        "directives": directives,
    }
    context["validation_errors"] = validate_project_configuration(context)
    return context


def _generate_project_id(name: str) -> str:
    normalized = unicodedata.normalize("NFD", (name or "").strip())
    ascii_name = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    project_id = re.sub(r"[^A-Z0-9]+", "_", ascii_name.upper()).strip("_")
    return project_id[:32]


def _save_dashboard_index_state(store: MemoryStore, project_id: str, sprint_id: str = "", team_id: str = "", subproject_id: str = "") -> None:
    store.save_platform_runtime_state(
        "dashboard",
        {
            "last_project_id": project_id,
            "last_sprint_id": sprint_id,
            "last_team_id": team_id,
            "last_subproject_id": subproject_id,
        },
    )

# ── Cargar .env ────────────────────────────────────────────────────────────────
env_path = BASE_DIR / "VeloxIq" / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

STATE_COLOR = {
    "Todo":         "#6b7280",
    "InProgress":   "#3b82f6",
    "QA":           "#f59e0b",
    "Fixing":       "#ef4444",
    "ReadyToMerge": "#8b5cf6",
    "Merged":       "#6366f1",
    "Blocked":      "#dc2626",
}
STACK_COLOR = {"BACK":"#6366f1","BO":"#f59e0b","MOB":"#10b981"}
PROV_COLOR  = {"zai":"#6366f1","minimax":"#f59e0b","openai":"#10b981"}
TYPE_ICON   = {"pm":"PM","orchestrator":"ORC","dev":"DEV","qa":"QA"}

# ── Datos locales (sin LLM, sin red cuando es posible) ────────────────────────
def local_token_stats() -> dict:
    db = BASE_DIR / "logs" / "token_usage.db"
    empty = {"cost":0,"calls":0,"tokens":0,"by_agent":{},"monthly_cost":0,"monthly_tokens":0}
    if not db.exists():
        return empty
    try:
        con = sqlite3.connect(db)
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")
        row = con.execute("""SELECT SUM(cost_usd),COUNT(*),SUM(input_tokens+output_tokens)
            FROM llm_calls WHERE date(timestamp)=?""", (today,)).fetchone()
        by_agent = dict(con.execute("""SELECT agent_name,SUM(cost_usd) FROM llm_calls
            WHERE date(timestamp)=? GROUP BY agent_name""", (today,)).fetchall())
        mrow = con.execute("""SELECT SUM(cost_usd),SUM(input_tokens+output_tokens)
            FROM llm_calls WHERE strftime('%Y-%m',timestamp)=?""", (month,)).fetchone()
        con.close()
        return {"cost":round(row[0] or 0,4),"calls":row[1] or 0,"tokens":row[2] or 0,
                "by_agent":by_agent,
                "monthly_cost":round(mrow[0] or 0,4),"monthly_tokens":int(mrow[1] or 0)}
    except Exception:
        return empty

def local_certified_endpoints() -> list:
    db = BASE_DIR / "memory" / "veloxiq_memory.db"
    if not db.exists():
        return []
    try:
        con = sqlite3.connect(db)
        rows = con.execute(
            "SELECT path,method,COALESCE(stack,'BACK'),certified_at "
            "FROM certified_endpoints ORDER BY certified_at DESC LIMIT 20"
        ).fetchall()
        con.close()
        return [{"endpoint":r[0],"method":r[1],"stack":r[2],"certified_at":r[3]} for r in rows]
    except Exception:
        return []

# ── Tablero local — cacheado 10s ──────────────────────────────────────────────
_board_cache: dict = {}
_board_cache_ts: float = 0

def get_local_board_data(sprint_id: str = "", project_id: str = "") -> dict:
    global _board_cache, _board_cache_ts
    import time
    cache_key = f"{project_id or '__project__'}::{sprint_id or '__all__'}"
    if time.time() - _board_cache_ts < 10 and _board_cache.get("_key") == cache_key:
        return _board_cache

    db = BASE_DIR / "memory" / "veloxiq_memory.db"
    stacks  = {k: {"total": 0, "verified": 0, "by_state": {}} for k in ["BACK", "BO", "MOB"]}
    parsed  = []
    sprints = []
    active_sprint = {"name": "Sprint Local", "sprint_id": "", "stack": "", "team_id": "", "substack": "", "subproject_id": ""}

    if not project_id:
        _board_cache = {
            "active_sprint": {"name": "Sin proyecto", "sprint_id": "", "stack": "", "project_id": "", "team_id": "", "substack": "", "subproject_id": ""},
            "issues":  [],
            "stacks":  stacks,
            "sprints": [],
            "_key":    cache_key,
        }
        _board_cache_ts = time.time()
        return _board_cache

    if db.exists():
        try:
            con = sqlite3.connect(db)

            # Load sprints list
            if project_id:
                sprint_rows = con.execute(
                    "SELECT sprint_id, name, stack, status, project_id, subproject_id, team_id, substack FROM sprints WHERE project_id = ? ORDER BY created_at DESC",
                    (project_id,),
                ).fetchall()
            else:
                sprint_rows = con.execute(
                    "SELECT sprint_id, name, stack, status, project_id, subproject_id, team_id, substack FROM sprints ORDER BY created_at DESC"
                ).fetchall()
            for sr in sprint_rows:
                sprints.append({"sprint_id": sr[0], "name": sr[1], "stack": sr[2], "status": sr[3], "project_id": sr[4], "subproject_id": sr[5], "team_id": sr[6], "substack": sr[7]})
                if sr[3] == "active" and not sprint_id:
                    active_sprint = {"name": sr[1], "sprint_id": sr[0], "stack": sr[2], "project_id": sr[4], "subproject_id": sr[5], "team_id": sr[6], "substack": sr[7]}

            # Load tasks filtered by sprint
            if sprint_id:
                if project_id:
                    rows = con.execute(
                        "SELECT lb.task_id, lb.summary, lb.state, lb.stack, lb.priority, lb.depends_on, lb.parallel, lb.sprint_id "
                        "FROM local_board lb "
                        "JOIN sprints s ON s.sprint_id = lb.sprint_id "
                        "WHERE lb.sprint_id = ? AND s.project_id = ? ORDER BY lb.created_at ASC",
                        (sprint_id, project_id),
                    ).fetchall()
                else:
                    rows = con.execute(
                        "SELECT task_id, summary, state, stack, priority, depends_on, parallel, sprint_id "
                        "FROM local_board WHERE sprint_id=? ORDER BY created_at ASC", (sprint_id,)
                    ).fetchall()
                # Sprint name for selected sprint
                for sr in sprints:
                    if sr["sprint_id"] == sprint_id:
                        active_sprint = {"name": sr["name"], "sprint_id": sprint_id, "stack": sr["stack"], "project_id": sr["project_id"], "subproject_id": sr.get("subproject_id", ""), "team_id": sr.get("team_id", ""), "substack": sr.get("substack", "")}
            else:
                if project_id:
                    rows = con.execute(
                        "SELECT lb.task_id, lb.summary, lb.state, lb.stack, lb.priority, lb.depends_on, lb.parallel, lb.sprint_id "
                        "FROM local_board lb "
                        "JOIN sprints s ON s.sprint_id = lb.sprint_id "
                        "WHERE s.project_id = ? ORDER BY lb.created_at ASC",
                        (project_id,),
                    ).fetchall()
                else:
                    rows = con.execute(
                        "SELECT task_id, summary, state, stack, priority, depends_on, parallel, sprint_id "
                        "FROM local_board ORDER BY created_at ASC"
                    ).fetchall()
            con.close()

            for task_id, summary, state, stack, priority, depends_on_raw, parallel, t_sprint in rows:
                s  = (summary or "").upper()
                sk = stack.upper() if stack and stack.upper() in ("BACK","BO","MOB") else (
                    "MOB" if any(w in s for w in ("MOB","ANDROID","MOBILE")) else
                    "BO"  if any(w in s for w in ("BO","BACKOFFICE","FRONT")) else "BACK"
                )
                stacks[sk]["total"] += 1
                stacks[sk]["by_state"][state] = stacks[sk]["by_state"].get(state, 0) + 1
                if state in ("Merged", "ReadyToMerge"):
                    stacks[sk]["verified"] += 1
                try:
                    deps = json.loads(depends_on_raw or "[]")
                except Exception:
                    deps = []
                parsed.append({
                    "id":       task_id,
                    "summary":  (summary or "")[:55],
                    "state":    state,
                    "stack":    sk,
                    "priority": priority or "Medium",
                    "depends_on": deps,
                    "parallel": bool(parallel),
                    "sprint_id": t_sprint or "",
                })
        except Exception:
            pass

    _board_cache = {
        "active_sprint": active_sprint,
        "issues":  parsed,
        "stacks":  stacks,
        "sprints": sprints,
        "_key":    cache_key,
    }
    _board_cache_ts = time.time()
    return _board_cache

# ── Build data ─────────────────────────────────────────────────────────────────
def build_data(sprint_id: str = "") -> dict:
    memory_store = MemoryStore()
    project_context = resolve_project_context(memory_store)
    platform_state = memory_store.get_platform_runtime_state("dashboard")
    runtime_state = memory_store.get_project_runtime_state(project_context.get("project_id", "")) if project_context.get("project_id") else {"last_sprint_id": "", "context": {}}
    effective_sprint_id = sprint_id or runtime_state.get("last_sprint_id", "") or platform_state.get("state", {}).get("last_sprint_id", "")
    yt         = get_local_board_data(effective_sprint_id, project_context.get("project_id", ""))
    tc         = local_token_stats()
    endpoints  = local_certified_endpoints()
    schedule   = get_schedule()
    providers  = json.loads((BASE_DIR/"config"/"agents.json").read_text())["providers"]
    active_sprint = yt.get("active_sprint") or {}
    active_stack = active_sprint.get("stack", "")
    active_team_id = active_sprint.get("team_id") or runtime_state.get("context", {}).get("team_id", "")
    team_status = get_team_status_for(active_team_id)
    agents_cfg = get_agents_with_eligibility(
        stack_key=active_stack or None,
        preset_name=active_team_id or None,
    )

    agents_out = []
    for a in agents_cfg:
        running = is_running(a["id"])
        agents_out.append({**a,
            "running":      running,
            "current_task": get_current_task(a["id"]) if running else "En espera",
            "cost_today":   round(tc["by_agent"].get(a["id"],0), 4),
        })
    alerts = get_active_alerts(yt_url="", yt_token="",
                               bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)
    subprojects = normalize_project_subprojects(project_context.get("git_dirs", {}))
    platform_settings = load_platform_settings()
    system_settings = load_system_settings()
    return {"agents":agents_out,"yt":yt,"tc":tc,"endpoints":endpoints,
            "schedule":schedule,"sys_running":system_running(),
            "updated_at":datetime.now().strftime("%H:%M:%S"),
            "specs":load_specializations(),"providers":providers,
            "alerts":alerts,"team":team_status,"active_stack":active_stack,
            "project":project_context,"templates":list_project_templates(),
            "runtime_state": runtime_state,
            "available_teams": list_team_presets(),
            "platform_state": platform_state,
            "platform_settings": platform_settings,
            "subprojects": subprojects,
            "system_settings": system_settings,
            "model_profiles": list_available_model_profiles(system_settings)}

# ── Abrir terminal PowerShell con tail del log del agente ─────────────────────
def open_terminal(agent_id: str) -> dict:
    agent = get_agent(agent_id)
    log_name = agent.get("log_file", f"{agent_id}.log") if agent else f"{agent_id}.log"
    log_file = BASE_DIR / log_name
    if not log_file.exists():
        log_file.touch()
    cmd = (
        f"$host.UI.RawUI.WindowTitle = 'VeloxIq - {agent_id}'; "
        f"Get-Content -Path '{log_file}' -Wait -Tail 60"
    )
    try:
        subprocess.Popen(
            ["powershell", "-NoExit", "-Command", cmd],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── Render HTML ────────────────────────────────────────────────────────────────
def render(data: dict) -> str:
    # Note: This uses raw string (r"") to avoid escape sequence issues
    yt      = data["yt"]
    stacks  = yt.get("stacks",{})
    issues  = yt.get("issues",[])
    active  = yt.get("active_sprint") or {}
    tc      = data["tc"]
    sched   = data["schedule"]
    specs   = data["specs"]
    provs   = data["providers"]
    team    = data["team"]
    active_stack = data.get("active_stack") or ""
    project = data["project"]
    templates = data["templates"]
    project_exists = bool(project.get("exists"))
    active_team = get_team_preset(team.get("active_preset")) or {}
    runtime_state = data.get("runtime_state", {})
    available_teams = data.get("available_teams", [])
    platform_settings = data.get("platform_settings", {})
    subprojects = data.get("subprojects", [])
    platform_state = data.get("platform_state", {}).get("state", {})
    system_settings = data.get("system_settings", {})
    model_profiles = data.get("model_profiles", [])
    has_subprojects = bool(subprojects)

    def pct(s): return int(s["verified"]/s["total"]*100) if s["total"] else 0
    def badges(by_state):
        return "".join(f'<span class="badge" style="background:{STATE_COLOR.get(k,"#888")}">{k}: {v}</span>'
                       for k,v in by_state.items())

    # Stack cards
    stack_html = ""
    labels = {"BACK":"FastAPI · PostgreSQL","BO":"Next.js · shadcn/ui","MOB":"Android · Compose"}
    prereqs = {"BO":"Requiere BACK:auth + openapi-spec","MOB":"Requiere BACK:shared-stable"}
    for name, color in STACK_COLOR.items():
        s = stacks.get(name,{"total":0,"verified":0,"by_state":{}})
        p = pct(s)
        pre = f'<div style="color:#475569;font-size:11px;margin-top:5px">{prereqs[name]}</div>' if p==0 and name in prereqs else ""
        stack_html += f"""<div class="card">
  <h2 style="color:{color}">{name} <span style="font-size:11px;color:#475569;font-weight:400">{labels[name]}</span></h2>
  <div class="prog-wrap"><div class="prog-bar" style="width:{p}%;background:{color}"></div></div>
  <div class="pct">{p}% &nbsp;·&nbsp; {s['verified']}/{s['total']} tareas</div>
  <div style="margin-top:6px">{badges(s['by_state'])}</div>{pre}
</div>"""

    # Agent cards
    agent_html = ""
    for a in data["agents"]:
        running  = a["running"]
        cur_task = a["current_task"]
        # Idle = running but no real task found in logs
        idle     = running and cur_task in ("En espera", "", "Idle")
        icon     = TYPE_ICON.get(a["type"],"?")
        sc       = STACK_COLOR.get(a.get("stack",""),"#555")
        pc       = PROV_COLOR.get(a.get("provider","zai"),"#555")
        btn_cls  = "btn-red" if running else "btn-green"
        btn_lbl  = "Detener" if running else "Iniciar"
        rm_btn   = f'<button class="btn btn-outline btn-sm" onclick="event.stopPropagation();removeAgent(\'{a["id"]}\')">&#x2715;</button>' if a.get("removable") else ""
        dot_cls  = ("dot-idle" if idle else "dot-on") if running else "dot-off"
        eligibility = a.get("eligibility", {})
        elig_color = "#10b981" if eligibility.get("eligible") else "#ef4444"
        elig_text = ", ".join(eligibility.get("reasons", []))
        # Status badge
        if not running:
            status_cls, status_lbl = "status-stopped", "Detenido"
        elif idle:
            status_cls, status_lbl = "status-idle", "En pausa"
        else:
            status_cls, status_lbl = "status-active", "Activo"
        agent_html += f"""<div class="agent-card {'running' if running else 'stopped'}" onclick="toggleLog('{a['id']}')">
  <div class="agent-top">
    <span class="agent-badge">{icon}</span>
    <span class="agent-name">{a['name']}</span>
    <div class="dot {dot_cls}"></div>
    <span class="status-badge {status_cls}">{status_lbl}</span>
  </div>
  <div class="agent-meta">
    <span class="tag" style="background:#0f766e">{a.get('role') or a.get('type') or 'agent'}</span>
    <span class="tag" style="background:{sc}">{a.get('stack') or 'ALL'}</span>
    <span class="tag" style="background:#475569">{a.get('specialization') or 'default'}</span>
    <span class="tag" style="background:{pc}">{a.get('provider','?')}</span>
    <span style="font-size:10px;color:#475569">{a.get('model','')}</span>
    <span style="float:right;font-size:10px;color:#64748b">${a['cost_today']} hoy</span>
  </div>
  <div class="agent-task">{cur_task}</div>
  <div style="font-size:10px;color:{elig_color};margin-top:6px">{elig_text}</div>
  <div class="agent-actions">
    <button class="btn {btn_cls} btn-sm" onclick="event.stopPropagation();agentToggle('{a['id']}',{str(running).lower()})">{btn_lbl}</button>
    <button class="btn btn-outline btn-sm" onclick="event.stopPropagation();toggleAgentEnabled('{a['id']}',{str(a.get('enabled', True)).lower()})">{'Desactivar' if a.get('enabled', True) else 'Activar'}</button>
    <button class="btn btn-gray btn-sm" onclick="event.stopPropagation();openTerminal('{a['id']}')" title="Abrir PowerShell con log en vivo" style="background:#4f46e5">PS</button>
    {rm_btn}
  </div>
  <pre class="log-panel" id="log-{a['id']}"></pre>
</div>"""

    # Sprint selector
    sprints      = yt.get("sprints", [])
    cur_sprint   = active.get("sprint_id", "")
    sprint_opts  = '<option value="">Todos los sprints</option>'
    for sp in sprints:
        sel  = ' selected' if sp["sprint_id"] == cur_sprint else ''
        status_mark = " ★" if sp["status"] == "active" else (" ⏸" if sp["status"] == "paused" else " ✓")
        team_suffix = f' · {sp.get("team_id","")}' if sp.get("team_id") else ""
        sprint_opts += f'<option value="{sp["sprint_id"]}"{sel}>{sp["sprint_id"]} — {sp["name"]}{team_suffix}{status_mark}</option>'
    # Active sprint pause/resume controls
    if cur_sprint:
        active_sp_status = next((s["status"] for s in sprints if s["sprint_id"] == cur_sprint), "")
        if active_sp_status == "active":
            sprint_ctrl_btn = f'<button class="btn btn-sm" style="background:#b45309;color:#fff" onclick="controlSprint(\'{cur_sprint}\',\'pause\')">⏸ Pausar sprint</button>'
        elif active_sp_status == "paused":
            sprint_ctrl_btn = f'<button class="btn btn-sm" style="background:#0e7490;color:#fff" onclick="controlSprint(\'{cur_sprint}\',\'resume\')">▶ Reanudar sprint</button>'
        else:
            sprint_ctrl_btn = ""
    else:
        sprint_ctrl_btn = ""

    # Kanban — 7 columnas del tablero local
    KANBAN_LABELS = {
        "Todo": "Todo", "InProgress": "In Progress", "QA": "QA",
        "Fixing": "Fixing", "ReadyToMerge": "Ready to Merge",
        "Merged": "Merged", "Blocked": "Blocked",
    }
    _PRIO_DOT = {"High":"🔴","Critical":"🔴","Medium":"🟡","Grave":"🟡","Low":"⚪","Mejora":"⚪"}
    kanban_html = ""
    for col, col_label in KANBAN_LABELS.items():
        items = [i for i in issues if i["state"] == col]
        color = STATE_COLOR.get(col, "#888")
        kanban_html += f'<div class="col"><div class="col-h" style="border-color:{color};color:{color}">{col_label} ({len(items)})</div>'
        for i in items:
            sc2      = STACK_COLOR.get(i["stack"], "#888")
            prio_dot = _PRIO_DOT.get(i.get("priority","Medium"), "⚪")
            deps     = i.get("depends_on", [])
            dep_tag  = f'<span title="Deps: {", ".join(deps)}" style="font-size:10px;color:#f59e0b">⛓ {len(deps)}</span> ' if deps else ""
            par_tag  = "" if i.get("parallel", True) else '<span title="Secuencial" style="font-size:10px;color:#a78bfa">⟳ </span>'
            kanban_html += (
                f'<div class="issue" onclick="showTaskDetail(\'{i["id"]}\')">'
                f'<span class="tag" style="background:{sc2}">{i["stack"]}</span>'
                f'{dep_tag}{par_tag}{prio_dot} <b>{i["id"]}</b> {i["summary"]}'
                f'</div>'
            )
        kanban_html += "</div>"

    # Endpoints
    eps = data["endpoints"]
    ep_html = "".join(f'<tr><td><code>{e["method"]}</code></td><td><code>{e["endpoint"]}</code></td>'
                      f'<td><span class="tag" style="background:{STACK_COLOR.get(e["stack"],"#888")}">{e["stack"]}</span></td>'
                      f'<td style="color:#475569;font-size:11px">{e["certified_at"][:16]}</td></tr>'
                      for e in eps) if eps else '<tr><td colspan="4" style="color:#475569">Sin endpoints certificados aún</td></tr>'

    # Modal spec options
    spec_opts = "".join(f'<option value="{k}">{v["label"]} ({v.get("stack","ALL")})</option>'
                        for k,v in specs.items() if k not in ("project_manager","orchestrator"))
    prov_opts = "".join(f'<option value="{k}">{v["label"]}</option>' for k,v in provs.items())
    sched_st  = f"Programado {sched.get('start_time','?')} → {sched.get('stop_time','?')}" if sched.get("enabled") else "Sin programar"
    template_opts = "".join(
        f'<option value="{template["id"]}"{" selected" if template["id"] == project.get("template_id") else ""}>{template["label"]}</option>'
        for template in templates
    )
    workflow_states = " → ".join(project.get("workflow", {}).get("states", []))
    provider_keys = ", ".join(sorted({provider.get("env_key", "") for provider in provs.values() if provider.get("env_key")}))
    validation_html = "".join(
        f'<div style="font-size:11px;color:#fca5a5">{error}</div>' for error in project.get("validation_errors", [])
    )
    active_git_dirs = project.get("git_dirs", {}) if project_exists else {}
    back_value = (active_git_dirs.get("BACK", "") or "").replace('"', "&quot;")
    web_bo_value = (active_git_dirs.get("WEB_BACKOFFICE", active_git_dirs.get("BO", "")) or "").replace('"', "&quot;")
    web_landing_value = (active_git_dirs.get("WEB_LANDING", "") or "").replace('"', "&quot;")
    android_value = (active_git_dirs.get("ANDROID", active_git_dirs.get("MOB", "")) or "").replace('"', "&quot;")
    ios_value = (active_git_dirs.get("IOS", "") or "").replace('"', "&quot;")
    flutter_value = (active_git_dirs.get("FLUTTER", "") or "").replace('"', "&quot;")
    team_badge = active_team.get("label", "Sin equipo asignado")
    team_scope = " / ".join(item for item in [active_team.get("stack_key", active_stack), active.get("substack", "")] if item)
    def textarea_escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    coding_rules_value = textarea_escape("\n".join(platform_settings.get("coding_rules", [])))
    git_rules_value = textarea_escape("\n".join(platform_settings.get("git_rules", [])))
    token_rules_value = textarea_escape("\n".join(platform_settings.get("token_optimization_rules", [])))
    subproject_options = "".join(
        f'<option value="{subproject["id"]}" data-stack="{subproject.get("stack_key","")}" data-substack="{subproject.get("substack","")}">{subproject.get("label", subproject["id"])} · {subproject.get("repo_dir","")}</option>'
        for subproject in subprojects
    ) or '<option value="">No hay subproyectos configurados</option>'
    model_profile_options = "".join(
        f'<option value="{profile["id"]}">{profile["service_label"]} · {profile["model"]}</option>'
        for profile in model_profiles
    ) or '<option value="">Sin perfiles LLM validados</option>'
    subproject_cards = "".join(
        f'<div class="card" style="padding:12px">'
        f'<div style="font-size:13px;font-weight:700;color:#e2e8f0">{textarea_escape(subproject.get("label", subproject["id"]))}</div>'
        f'<div style="font-size:11px;color:#94a3b8;margin-top:4px">{subproject.get("stack_key","")} / {subproject.get("substack","")}</div>'
        f'<div style="font-size:11px;color:#64748b;margin-top:4px">{textarea_escape(subproject.get("repo_dir",""))}</div>'
        f'</div>'
        for subproject in subprojects
    )
    restored_sprint_id = active.get("sprint_id") or runtime_state.get("last_sprint_id", "") or platform_state.get("last_sprint_id", "")
    restored_team_id = active_team.get("id") or runtime_state.get("context", {}).get("team_id", "") or platform_state.get("last_team_id", "")
    restored_subproject_id = active.get("subproject_id") or runtime_state.get("context", {}).get("subproject_id", "") or platform_state.get("last_subproject_id", "")
    restored_subproject = next((item for item in subprojects if item.get("id") == restored_subproject_id), None)
    restored_repo_suffix = f" ({restored_subproject.get('repo_dir', '')})" if restored_subproject else ""
    logic_rows = [
        ("Arranque del dashboard", "Se restaura automaticamente el ultimo proyecto, sprint, equipo y subproyecto persistidos para continuar donde quedo el trabajo."),
        ("Persistencia de contexto", f"Proyecto: {project.get('project_id') or platform_state.get('last_project_id') or 'sin proyecto'} · Sprint: {restored_sprint_id or 'sin sprint'} · Equipo: {restored_team_id or 'sin equipo'} · Subproyecto: {restored_subproject.get('label') if restored_subproject else (restored_subproject_id or 'sin subproyecto')}"),
        ("Vinculo sprint-equipo", "Cada sprint queda asociado a un equipo reusable. Ese equipo define los skills permitidos y el equipo activo se deriva del sprint seleccionado."),
        ("Vinculo sprint-subproyecto", f"Cada sprint pertenece a un subproyecto del proyecto activo. El stack operativo y el repositorio se derivan del subproyecto seleccionado{restored_repo_suffix}."),
        ("Reglas globales", "Las politicas de codificacion, git/ramas y optimizacion de tokens persisten a nivel plataforma y aplican a todos los agentes y proyectos."),
    ]
    logic_html = "".join(
        f'<div style="padding:10px 0;border-top:1px solid #1e293b"><div style="font-size:11px;color:#94a3b8;font-weight:700">{title}</div><div style="font-size:11px;color:#cbd5e1;margin-top:4px">{text}</div></div>'
        for title, text in logic_rows
    )

    def render_rule_list(items: list[str], empty_text: str) -> str:
        if not items:
            return f'<div style="font-size:11px;color:#64748b">{empty_text}</div>'
        return "".join(f'<li>{textarea_escape(item)}</li>' for item in items)

    onboarding_html = ""
    if not project_exists:
        onboarding_html = f"""
<div class="section">
  <div class="section-title">Crear proyecto</div>
  <div style="max-width:560px">
    <div style="font-size:12px;color:#94a3b8;margin-bottom:12px">El sistema necesita primero un proyecto. Hasta que no exista uno, no se muestran tablero ni agentes.</div>
    <div class="fg">
      <label>Nombre del proyecto</label>
      <input type="text" id="onboard-proj-name" placeholder="Nombre completo">
    </div>
    <div class="fg">
      <label>Descripcion</label>
      <input type="text" id="onboard-proj-desc" placeholder="Descripcion breve">
    </div>
    <button class="btn btn-green" onclick="createProject()" style="width:100%">Crear proyecto</button>
  </div>
</div>"""
    elif not has_subprojects:
        onboarding_html = f"""
<div class="section">
  <div class="section-title">Crear primer subproyecto</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start">
    <div>
      <div style="font-size:12px;color:#94a3b8;margin-bottom:12px">Cada proyecto necesita al menos un subproyecto con stack, substack, repositorio y perfiles LLM por defecto para developers y QA.</div>
      <div class="fg">
        <label>Nombre del subproyecto</label>
        <input type="text" id="subproject-name" placeholder="Ej: API Core">
      </div>
      <div class="fg">
        <label>Stack</label>
        <select id="subproject-stack" onchange="refreshSubprojectForm()">
          <option value="BACK">Backend</option>
          <option value="BO">Front Web</option>
          <option value="MOB">Front Mobile</option>
        </select>
      </div>
      <div class="fg">
        <label>Substack existente</label>
        <select id="subproject-substack" onchange="refreshSubprojectForm()"></select>
      </div>
      <div class="fg">
        <label>O crear nuevo substack</label>
        <input type="text" id="subproject-substack-custom" placeholder="Opcional">
      </div>
      <div class="fg">
        <label>Repositorio</label>
        <input type="text" id="subproject-repo" placeholder="C:\\Users\\...\\repos\\mi-subproyecto">
      </div>
      <div class="fg">
        <label>Skills del substack</label>
        <select id="subproject-skills" multiple style="height:120px"></select>
      </div>
      <div class="fg">
        <label>Modelo por defecto para los 3 developers</label>
        <select id="subproject-dev-model">{model_profile_options}</select>
      </div>
      <div class="fg">
        <label>Modelo por defecto para QA</label>
        <select id="subproject-qa-model">{model_profile_options}</select>
      </div>
      <button class="btn btn-green" onclick="createSubproject()" style="width:100%">Crear subproyecto</button>
    </div>
    <div>
      <div style="font-size:12px;color:#e2e8f0;font-weight:700;margin-bottom:8px">Configuracion global actual</div>
      <div style="font-size:11px;color:#94a3b8;margin-bottom:8px">PM y Orchestrator usan el perfil global definido en la instalacion. Developers y QA se fijan por subproyecto.</div>
      <div style="font-size:11px;color:#cbd5e1;line-height:1.6">
        <div>PM: {textarea_escape(system_settings.get("role_defaults", {}).get("pm", "") or "sin perfil")}</div>
        <div>Orchestrator: {textarea_escape(system_settings.get("role_defaults", {}).get("orchestrator", "") or "sin perfil")}</div>
      </div>
    </div>
  </div>
</div>"""

    sys_run = data["sys_running"]
    raw_alerts = data.get("alerts", [])

    # Alert panel HTML
    if raw_alerts:
        alert_items = ""
        for al in raw_alerts:
            tid      = al["task_id"]
            attempts = al["attempts"]
            state    = al.get("yt_state", "?")
            ts       = al.get("detected_at", "")
            yt_link  = f"#task-{tid}"
            alert_items += f"""<div class="alert-card">
  <span class="alert-icon">🚨</span>
  <div class="alert-body">
    <div class="alert-tid"><a href="{yt_link}" target="_blank" style="color:#fca5a5;text-decoration:none">{tid}</a></div>
    <div class="alert-detail">{attempts} intentos de implementación sin verificar &nbsp;·&nbsp; Estado: <b>{state}</b> &nbsp;·&nbsp; {ts}</div>
  </div>
  <button class="alert-dismiss" onclick="dismissAlert('{tid}')">Ignorar</button>
</div>"""
        alert_html = f'<div class="alert-panel">{alert_items}</div>'
    else:
        alert_html = ""

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><title>VeloxIq</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;padding:20px}}
h1{{font-size:20px;font-weight:700}}
.topbar{{display:flex;align-items:center;gap:12px;margin-bottom:18px;flex-wrap:wrap;padding:10px 0}}
.topbar h1{{margin:0;font-size:20px}}
.topbar .subtitle{{margin:0;color:#64748b;font-size:12px;flex:1}}
.topbar .btn{{margin:0}}
.topbar-divider{{width:1px;height:24px;background:#334155;margin:0 6px}}
.btn{{border:none;border-radius:7px;padding:7px 14px;font-size:12px;cursor:pointer;font-weight:600}}
.btn-green{{background:#10b981;color:#fff}}.btn-red{{background:#ef4444;color:#fff}}
.btn-gray{{background:#334155;color:#e2e8f0}}.btn-blue{{background:#3b82f6;color:#fff}}
.btn-outline{{background:transparent;border:1px solid #475569;color:#94a3b8}}
.btn-sm{{padding:3px 9px;font-size:11px;border-radius:5px}}
.grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}}
.card{{background:#1e293b;border-radius:10px;padding:15px;border:1px solid #334155}}
.card h2{{font-size:14px;font-weight:600;margin-bottom:10px}}
.prog-wrap{{background:#334155;border-radius:4px;height:7px;margin:6px 0 4px}}
.prog-bar{{height:7px;border-radius:4px}}
.pct{{font-size:11px;color:#94a3b8}}
.badge{{display:inline-block;font-size:10px;padding:2px 6px;border-radius:3px;color:#fff;margin:2px}}
.tag{{display:inline-block;font-size:10px;padding:1px 5px;border-radius:3px;color:#fff;margin-right:3px}}
.agents-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px;margin-bottom:16px;align-items:start}}
.agent-card{{background:#1e293b;border-radius:10px;padding:13px;border:1px solid #334155;cursor:pointer}}
.agent-card.running{{border-color:#10b98155}}
.agent-card.stopped{{border-color:#ef444433}}
.agent-top{{display:flex;align-items:center;gap:7px;margin-bottom:7px}}
.agent-badge{{background:#334155;border-radius:5px;padding:2px 7px;font-size:11px;font-weight:700;color:#94a3b8}}
.agent-name{{font-weight:600;font-size:13px;flex:1}}
.dot{{width:7px;height:7px;border-radius:50%}}
.dot-on{{background:#10b981;box-shadow:0 0 5px #10b981}}
.dot-off{{background:#ef4444}}
.dot-idle{{background:#f59e0b;box-shadow:0 0 5px #f59e0b}}
.status-badge{{display:inline-block;font-size:9px;padding:1px 5px;border-radius:3px;font-weight:700;margin-left:4px;vertical-align:middle}}
.status-active{{background:#10b98122;color:#10b981;border:1px solid #10b98155}}
.status-idle{{background:#f59e0b22;color:#f59e0b;border:1px solid #f59e0b55}}
.status-stopped{{background:#ef444422;color:#ef4444;border:1px solid #ef444455}}
.agent-meta{{font-size:11px;color:#64748b;margin-bottom:7px}}
.agent-task{{font-size:11px;color:#94a3b8;background:#0f172a;border-radius:5px;padding:5px 7px;min-height:26px}}
.agent-actions{{display:flex;gap:5px;margin-top:8px}}
.log-panel{{background:#0a0f1a;border:1px solid #1e293b;border-radius:6px;padding:10px;
  font-size:10px;color:#64748b;max-height:240px;overflow-y:auto;margin-top:7px;display:none;white-space:pre-wrap}}
.section{{background:#1e293b;border-radius:10px;padding:15px;border:1px solid #334155;margin-bottom:12px}}
.section-title{{font-size:13px;font-weight:600;color:#94a3b8;margin-bottom:11px}}
.kanban-wrap{{overflow-x:auto;padding-bottom:4px}}
.kanban{{display:grid;grid-template-columns:repeat(7,minmax(140px,1fr));gap:8px;min-width:980px}}
.col{{background:#0f172a;border-radius:7px;padding:9px}}
.col-h{{font-size:10px;font-weight:700;border-left:3px solid;padding-left:5px;margin-bottom:7px;text-transform:uppercase;letter-spacing:.4px}}
.issue{{background:#1e293b;border-radius:4px;padding:5px 7px;margin-bottom:5px;font-size:11px;border:1px solid #334155}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{text-align:left;color:#64748b;font-weight:500;padding:5px 7px;border-bottom:1px solid #334155}}
td{{padding:5px 7px;border-bottom:1px solid #0f172a}}
code{{background:#0f172a;padding:2px 4px;border-radius:3px;font-size:11px}}
.cost-bar{{background:#1e293b;border-radius:8px;padding:8px 13px;font-size:12px;margin-bottom:14px;color:#94a3b8;border:1px solid #334155}}
.sched{{display:flex;align-items:center;gap:7px;flex-wrap:wrap}}
.sched input[type=time]{{width:100px;background:#0f172a;border:1px solid #334155;border-radius:5px;padding:5px 7px;color:#e2e8f0;font-size:12px}}
.modal-bg{{display:none;position:fixed;inset:0;background:#000b;z-index:100;align-items:center;justify-content:center}}
.modal-bg.open{{display:flex}}
.modal{{background:#1e293b;border-radius:12px;padding:22px;width:420px;max-width:95vw;border:1px solid #334155}}
.modal h3{{font-size:15px;font-weight:700;margin-bottom:14px}}
.fg{{margin-bottom:11px}}
label{{display:block;font-size:11px;color:#94a3b8;margin-bottom:3px}}
select,input[type=text]{{width:100%;background:#0f172a;border:1px solid #334155;border-radius:5px;padding:7px 9px;color:#e2e8f0;font-size:12px}}
.modal-actions{{display:flex;gap:7px;margin-top:14px;justify-content:flex-end}}
.config-group{{margin-bottom:14px;border:1px solid #334155;border-radius:10px;background:#0f172a}}
.config-group summary{{cursor:pointer;list-style:none;padding:12px 14px;font-size:12px;font-weight:700;color:#cbd5e1;display:flex;align-items:center;justify-content:space-between}}
.config-group summary::-webkit-details-marker{{display:none}}
.config-group[open] summary{{border-bottom:1px solid #334155}}
.config-group-body{{padding:14px}}
.alert-panel{{margin-bottom:14px}}
.alert-card{{display:flex;align-items:center;gap:10px;background:#450a0a;border:1px solid #ef444477;border-radius:8px;padding:9px 13px;margin-bottom:7px}}
.alert-icon{{font-size:16px}}
.alert-body{{flex:1;min-width:0}}
.alert-tid{{font-weight:700;font-size:13px;color:#fca5a5}}
.alert-detail{{font-size:11px;color:#f87171;margin-top:2px}}
.alert-dismiss{{background:#7f1d1d;border:none;border-radius:5px;color:#fca5a5;padding:4px 10px;font-size:11px;cursor:pointer;font-weight:600;white-space:nowrap}}
.alert-dismiss:hover{{background:#991b1b}}
</style></head><body>

<div class="topbar">
  <h1>VeloxIq</h1>
  <span class="subtitle">{project.get('name','Proyecto')} &nbsp;·&nbsp; {project.get('template', {}).get('label', project.get('template_id','template'))} &nbsp;·&nbsp; {data['updated_at']} &nbsp;·&nbsp; <span id="cd">30</span>s</span>
  {f'''<button class="btn {'btn-red' if sys_run else 'btn-green'}" onclick="systemToggle()">
    {'Apagar' if sys_run else 'Encender'}
  </button>
  <button class="btn btn-blue" onclick="document.getElementById('mbg').classList.add('open')">+ Agente</button>
  <button class="btn btn-blue" onclick="openSprintModal()" style="background:#d946ef">+ Sprint</button>''' if project_exists and has_subprojects else ''}
  <button class="btn btn-blue" onclick="openConfigModal()" style="background:#8b5cf6">Configuracion</button>
</div>

{onboarding_html}

{'' if not project_exists else f'''
<div class="section" style="margin-bottom:12px">
  <div class="section-title">Equipo activo</div>
  <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
    <span class="tag" style="background:#0f766e;font-size:11px;padding:4px 8px">{team_badge}</span>
    <span style="font-size:11px;color:#64748b">Sprint: {active.get('sprint_id') or 'sin sprint seleccionado'}</span>
    <span style="font-size:11px;color:#64748b">Scope: {team_scope or 'sin scope'}</span>
    <button class="btn btn-sm btn-outline" onclick="toggleStack('BACK', true)">BACK on</button>
    <button class="btn btn-sm btn-outline" onclick="toggleStack('BACK', false)">BACK off</button>
    <button class="btn btn-sm btn-outline" onclick="toggleStack('BO', true)">BO on</button>
    <button class="btn btn-sm btn-outline" onclick="toggleStack('BO', false)">BO off</button>
    <button class="btn btn-sm btn-outline" onclick="toggleStack('MOB', true)">MOB on</button>
    <button class="btn btn-sm btn-outline" onclick="toggleStack('MOB', false)">MOB off</button>
  </div>
</div>

<div class="section" style="margin-bottom:12px">
  <div class="section-title">Proyecto activo</div>
  <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px">
    <span style="font-size:12px;color:#e2e8f0">{project.get('name','Sin proyecto')}</span>
    <select id="project-template-sel" onchange="updateProjectTemplate(this.value)" style="max-width:260px" {'disabled' if not project_exists else ''}>
      {template_opts}
    </select>
  </div>
  <div style="font-size:11px;color:#94a3b8">{project.get('template', {}).get('description', '')}</div>
  <div style="font-size:10px;color:#64748b;margin-top:6px">Workflow: {workflow_states}</div>
  {validation_html}
</div>

<div class="section" style="margin-bottom:12px">
  <div class="section-title">Subproyectos</div>
  <div class="grid3">{subproject_cards or '<div style="font-size:12px;color:#94a3b8">Todavia no hay subproyectos configurados.</div>'}</div>
</div>

<div class="section" style="margin-bottom:12px">
  <div class="section-title">Contexto restaurado y logica activa</div>
  <div style="display:grid;grid-template-columns:1.2fr 1fr;gap:14px;align-items:start">
    <div style="background:#0f172a;border:1px solid #334155;border-radius:10px;padding:12px">
      <div style="font-size:12px;color:#e2e8f0;font-weight:700;margin-bottom:8px">Indice operativo</div>
      <div style="font-size:11px;color:#94a3b8;margin-bottom:8px">El tablero vuelve a abrir con el ultimo contexto persistido y deja visible la logica base ya implementada.</div>
      {logic_html}
    </div>
    <div style="background:#0f172a;border:1px solid #334155;border-radius:10px;padding:12px">
      <div style="font-size:12px;color:#e2e8f0;font-weight:700;margin-bottom:8px">Reglas persistentes</div>
      <div style="font-size:11px;color:#94a3b8;margin-bottom:6px">Codificacion</div>
      <ul style="margin:0 0 10px 18px;font-size:11px;color:#cbd5e1">{render_rule_list(platform_settings.get("coding_rules", []), "Sin reglas configuradas.")}</ul>
      <div style="font-size:11px;color:#94a3b8;margin-bottom:6px">Git y ramas</div>
      <ul style="margin:0 0 10px 18px;font-size:11px;color:#cbd5e1">{render_rule_list(platform_settings.get("git_rules", []), "Sin reglas configuradas.")}</ul>
      <div style="font-size:11px;color:#94a3b8;margin-bottom:6px">Optimizacion de tokens</div>
      <ul style="margin:0 0 0 18px;font-size:11px;color:#cbd5e1">{render_rule_list(platform_settings.get("token_optimization_rules", []), "Sin reglas configuradas.")}</ul>
    </div>
  </div>
</div>
'''}

{'' if not (project_exists and has_subprojects) else f'''
<!-- Quick scheduler controls under topbar -->
<div style="display:flex;gap:10px;margin-bottom:12px;align-items:center;font-size:11px">
  <div class="sched">
    <input type="time" id="st" value="{sched.get('start_time') or ''}" title="Hora inicio">
    <input type="time" id="sp" value="{sched.get('stop_time') or ''}" title="Hora apagado">
    <button class="btn btn-gray btn-sm" onclick="saveSchedule()">Programar</button>
    <span style="font-size:10px;color:#475569" id="ss">{sched_st}</span>
  </div>
</div>

{alert_html}<div class="cost-bar">
  <div style="display:flex;gap:28px;align-items:flex-end;flex-wrap:wrap">
    <div>
      <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.5px">Hoy</div>
      <div style="font-size:26px;font-weight:800;color:#e2e8f0;line-height:1.1">${tc['cost']}<span style="font-size:13px;font-weight:400;color:#64748b"> USD</span></div>
      <div style="font-size:11px;color:#64748b">{tc['calls']} llamadas &nbsp;·&nbsp; {tc['tokens']:,} tokens</div>
    </div>
    <div style="border-left:1px solid #334155;padding-left:28px">
      <div style="font-size:10px;color:#475569;text-transform:uppercase;letter-spacing:.5px">Este mes</div>
      <div style="font-size:26px;font-weight:800;color:#94a3b8;line-height:1.1">${tc.get('monthly_cost',0)}<span style="font-size:13px;font-weight:400;color:#475569"> USD</span></div>
      <div style="font-size:11px;color:#475569">{tc.get('monthly_tokens',0):,} tokens</div>
    </div>
  </div>
</div>

<div class="grid3">{stack_html}</div>

<div style="font-size:12px;color:#64748b;margin-bottom:9px;font-weight:600">AGENTES</div>
<div class="agents-grid">{agent_html}</div>

<div class="section">
  <div class="section-title" style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
    <span>Tablero — {active.get('name','N/D')}</span>
    <select id="sprint-sel" onchange="filterSprint(this.value)"
      style="font-size:12px;padding:3px 8px;border-radius:6px;background:#1e293b;color:#e2e8f0;border:1px solid #334155">
      {sprint_opts}
    </select>
    {sprint_ctrl_btn}
    <label style="font-size:12px;color:#94a3b8;cursor:pointer" title="Importar plan de ejecucion">
      📎 Subir plan
      <input type="file" id="plan-upload" accept=".json,.md" onchange="uploadPlan(this)"
        style="display:none">
    </label>
    <span id="upload-status" style="font-size:11px;color:#22c55e"></span>
  </div>
  <div class="kanban-wrap"><div class="kanban">{kanban_html}</div></div>
</div>

<div class="section">
  <div class="section-title">Endpoints certificados por QA</div>
  <table><tr><th>Método</th><th>Endpoint</th><th>Stack</th><th>Certificado</th></tr>{ep_html}</table>
</div>
'''}

<!-- MODAL -->
<div class="modal-bg" id="mbg">
  <div class="modal">
    <h3>Agregar agente</h3>
    <div class="fg"><label>Tipo</label>
      <select id="nt" onchange="refreshSpecializationOptions()"><option value="dev">Dev</option><option value="qa">QA</option></select></div>
    <div class="fg"><label>Especialización</label>
      <select id="ns">{spec_opts}</select></div>
    <div class="fg"><label>Proveedor</label>
      <select id="np" onchange="updModels()">{prov_opts}</select></div>
    <div class="fg"><label>Modelo</label>
      <select id="nm"></select></div>
    <div class="fg"><label>Nombre (opcional)</label>
      <input type="text" id="nn" placeholder="Ej: Dev DB Postgres"></div>
    <div class="modal-actions">
      <button class="btn btn-gray" onclick="document.getElementById('mbg').classList.remove('open')">Cancelar</button>
      <button class="btn btn-green" onclick="addAgent()">Agregar</button>
    </div>
  </div>
</div>
<!-- UNIFIED CONFIG MODAL -->
<div class="modal-bg" id="config-modal-bg">
  <div class="modal" style="width:600px;max-height:90vh;overflow-y:auto">
    <h3>Configuracion del Sistema</h3>

    <details class="config-group" open>
      <summary>Proyecto Activo Y Alta Rapida <span style="font-size:11px;color:#64748b">obligatorio minimo</span></summary>
      <div class="config-group-body">
        <div id="project-list" style="max-height:150px;overflow-y:auto;margin-bottom:12px"></div>
        <div class="fg">
          <label>Nombre del Proyecto</label>
          <input type="text" id="new-proj-name" placeholder="Nombre completo">
        </div>
        <div class="fg">
          <label>Descripcion</label>
          <input type="text" id="new-proj-desc" placeholder="Detalles del proyecto">
        </div>
        <button class="btn btn-green" onclick="createProject()" style="width:100%">Crear Proyecto</button>
      </div>
    </details>

    <details class="config-group">
      <summary>Alta De Subproyecto <span style="font-size:11px;color:#64748b">habilita tablero y agentes</span></summary>
      <div class="config-group-body">
        <div style="font-size:11px;color:#64748b;margin-bottom:10px">Selecciona o crea un substack, define skills y asigna perfiles LLM por defecto para developers y QA.</div>
        <div class="fg">
          <label>Nombre del subproyecto</label>
          <input type="text" id="subproject-name-config" placeholder="Ej: Backoffice Principal">
        </div>
        <div class="fg">
          <label>Stack</label>
          <select id="subproject-stack-config" onchange="refreshSubprojectForm('config')">
            <option value="BACK">Backend</option>
            <option value="BO">Front Web</option>
            <option value="MOB">Front Mobile</option>
          </select>
        </div>
        <div class="fg">
          <label>Substack existente</label>
          <select id="subproject-substack-config" onchange="refreshSubprojectForm('config')"></select>
        </div>
        <div class="fg">
          <label>O crear nuevo substack</label>
          <input type="text" id="subproject-substack-custom-config" placeholder="Opcional">
        </div>
        <div class="fg">
          <label>Repositorio</label>
          <input type="text" id="subproject-repo-config" placeholder="C:\\Users\\...\\repos\\subproyecto">
        </div>
        <div class="fg">
          <label>Skills del substack</label>
          <select id="subproject-skills-config" multiple style="height:120px"></select>
        </div>
        <div class="fg">
          <label>Modelo por defecto para developers</label>
          <select id="subproject-dev-model-config">{model_profile_options}</select>
        </div>
        <div class="fg">
          <label>Modelo por defecto para QA</label>
          <select id="subproject-qa-model-config">{model_profile_options}</select>
        </div>
        <button class="btn btn-green" onclick="createSubproject('config')" style="width:100%">Guardar Subproyecto</button>
      </div>
    </details>

    <details class="config-group">
      <summary>Repos Adicionales Del Proyecto <span style="font-size:11px;color:#64748b">opcional</span></summary>
      <div class="config-group-body">
        <div style="font-size:11px;color:#64748b;margin-bottom:10px">Agrega o actualiza repos adicionales para el proyecto seleccionado. Solo se requiere al menos uno para crear el proyecto.</div>
        <div class="fg">
          <label>BACK (FastAPI · PostgreSQL)</label>
          <input type="text" id="git-back" value="{back_value}" placeholder="C:\\Users\\...\\repos\\backend">
        </div>
        <div class="fg">
          <label>Front Web - Backoffice</label>
          <input type="text" id="git-web-bo" value="{web_bo_value}" placeholder="C:\\Users\\...\\repos\\backoffice">
        </div>
        <div class="fg">
          <label>Front Web - Landing (opcional)</label>
          <input type="text" id="git-web-landing" value="{web_landing_value}" placeholder="C:\\Users\\...\\repos\\landing">
        </div>
        <div class="fg">
          <label>Mobile - Android</label>
          <input type="text" id="git-android" value="{android_value}" placeholder="C:\\Users\\...\\repos\\android">
        </div>
        <div class="fg">
          <label>Mobile - iOS (opcional)</label>
          <input type="text" id="git-ios" value="{ios_value}" placeholder="C:\\Users\\...\\repos\\ios">
        </div>
        <div class="fg">
          <label>Mobile - Flutter (opcional)</label>
          <input type="text" id="git-flutter" value="{flutter_value}" placeholder="C:\\Users\\...\\repos\\flutter">
        </div>
        <button class="btn btn-green" onclick="saveGitDirs()" style="width:100%">Guardar Directorios</button>
      </div>
    </details>

    <details class="config-group">
      <summary>Modelos Y API Keys <span style="font-size:11px;color:#64748b">informativo</span></summary>
      <div class="config-group-body">
        <div style="font-size:11px;color:#94a3b8">Providers soportados por entorno: {provider_keys}</div>
        <div style="font-size:10px;color:#64748b;margin-top:6px">Las API keys se leen desde variables de entorno. Esta seccion es informativa.</div>
      </div>
    </details>

    <details class="config-group">
      <summary>Reglas Globales De Plataforma <span style="font-size:11px;color:#64748b">persisten para todos los proyectos</span></summary>
      <div class="config-group-body">
        <div class="fg">
          <label>Politicas generales de codificacion</label>
          <textarea id="platform-coding-rules" style="width:100%;height:100px;background:#0f172a;border:1px solid #334155;border-radius:5px;padding:7px;color:#e2e8f0;font-size:12px;resize:vertical">{coding_rules_value}</textarea>
        </div>
        <div class="fg">
          <label>Politicas generales de ramas y git</label>
          <textarea id="platform-git-rules" style="width:100%;height:100px;background:#0f172a;border:1px solid #334155;border-radius:5px;padding:7px;color:#e2e8f0;font-size:12px;resize:vertical">{git_rules_value}</textarea>
        </div>
        <div class="fg">
          <label>Politicas de optimizacion de tokens</label>
          <textarea id="platform-token-rules" style="width:100%;height:100px;background:#0f172a;border:1px solid #334155;border-radius:5px;padding:7px;color:#e2e8f0;font-size:12px;resize:vertical">{token_rules_value}</textarea>
        </div>
        <button class="btn btn-green" onclick="savePlatformSettings()" style="width:100%">Guardar Reglas Globales</button>
      </div>
    </details>

    <div class="modal-actions">
      <button class="btn btn-gray" onclick="closeConfigModal()">Cerrar</button>
    </div>
  </div>
</div>

<!-- CREATE SPRINT MODAL -->
<div class="modal-bg" id="sprint-modal-bg">
  <div class="modal" style="width:520px">
    <h3>Crear Sprint</h3>
    <div class="fg">
      <label>Sprint ID</label>
      <input type="text" id="sprint-id" placeholder="sprint_02">
    </div>
    <div class="fg">
      <label>Nombre</label>
      <input type="text" id="sprint-name" placeholder="Sprint 2 - Autenticación">
    </div>
    <div class="fg">
      <label>Subproyecto</label>
      <select id="sprint-subproject" onchange="refreshSprintScope()">
        {subproject_options}
      </select>
    </div>
    <div class="fg">
      <label>Stack operativo</label>
      <input type="text" id="sprint-stack" readonly>
    </div>
    <div class="fg">
      <label>Substack</label>
      <input type="text" id="sprint-substack" readonly>
    </div>
    <div class="fg">
      <label>Modo de equipo</label>
      <select id="sprint-team-mode" onchange="toggleTeamMode()">
        <option value="reuse">Reutilizar perfil existente</option>
        <option value="create">Crear perfil nuevo</option>
      </select>
    </div>
    <div class="fg" id="reuse-team-group">
      <label>Equipo asignado</label>
      <select id="sprint-team"></select>
    </div>
    <div id="create-team-group" style="display:none">
      <div class="fg">
        <label>Nombre del nuevo equipo</label>
        <input type="text" id="new-team-label" placeholder="Ej: Mobile Android Premium">
      </div>
      <div class="fg">
        <label>Nombre del stack del equipo</label>
        <input type="text" id="new-team-stack-name" placeholder="Ej: Android Kotlin">
      </div>
      <div class="fg">
        <label>Skills del equipo</label>
        <select id="new-team-skills" multiple style="height:110px"></select>
      </div>
    </div>
    <div class="fg">
      <label style="display:flex;align-items:center;gap:7px">
        Tareas (JSON format)
        <span style="font-size:9px;color:#475569">ej: Paste JSON array of tasks</span>
      </label>
      <textarea id="sprint-tasks" style="width:100%;height:120px;background:#0f172a;border:1px solid #334155;border-radius:5px;padding:7px;color:#e2e8f0;font-family:monospace;font-size:11px;resize:vertical"></textarea>
    </div>
    <div class="modal-actions">
      <button class="btn btn-gray" onclick="closeSprintModal()">Cancelar</button>
      <button class="btn btn-green" onclick="createSprint()">Crear Sprint</button>
    </div>
  </div>
</div>

</div>

<script>
const PROVS = {json.dumps(provs)};
const SPECS = {json.dumps(specs)};
const TEAM_PRESETS = {json.dumps(available_teams)};
const ACTIVE_PROJECT_ID = {json.dumps(project.get("project_id", ""))};
const ACTIVE_SPRINT_ID = {json.dumps(active.get("sprint_id", ""))};
const ACTIVE_TEAM_ID = {json.dumps(active_team.get("id", ""))};
const ACTIVE_SUBPROJECT_ID = {json.dumps(active.get("subproject_id") or runtime_state.get("context", {}).get("subproject_id", ""))};
const SUBPROJECTS = {json.dumps(subprojects)};
const SPRINTS = {json.dumps(sprints)};
const MODEL_PROFILES = {json.dumps(model_profiles)};
const SYSTEM_ROLE_DEFAULTS = {json.dumps(system_settings.get("role_defaults", {}))};
const SUBSTACK_OPTIONS = {json.dumps({key: list_substack_options(key) for key in ("BACK", "BO", "MOB")})};
let sprintScopeInitialized = false;

function hasOpenModal(){{
  return ['mbg','config-modal-bg','sprint-modal-bg'].some(id=>document.getElementById(id)?.classList.contains('open'));
}}

setInterval(()=>{{
  let c=document.getElementById('cd');
  if(!c||hasOpenModal())return;
  c.textContent=+c.textContent-1;
  if(+c.textContent<=0)location.reload();
}},1000);

async function systemToggle(){{await fetch('/api/system/{("stop" if sys_run else "start")}',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{team_id:ACTIVE_TEAM_ID}})}});location.reload();}}

function toggleLog(id){{
  const p=document.getElementById('log-'+id);
  if(p.style.display==='block'){{p.style.display='none';return;}}
  p.style.display='block';p.textContent='Cargando...';
  fetch('/api/agents/'+id+'/log').then(r=>r.text()).then(t=>{{p.textContent=t;p.scrollTop=p.scrollHeight;}});
}}

async function agentToggle(id,running){{
  await fetch('/api/agents/'+id+'/'+(running?'stop':'start'),{{method:'POST'}});location.reload();
}}

async function toggleAgentEnabled(id,enabled){{
  await fetch('/api/agents/'+id+'/enabled',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{enabled:!enabled}})}});
  location.reload();
}}

async function toggleStack(stack, enabled){{
  await fetch('/api/team/stack',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{stack_key:stack, enabled}})}});
  location.reload();
}}

async function removeAgent(id){{
  if(!confirm('¿Eliminar agente '+id+'?'))return;
  const r=await fetch('/api/agents/'+id,{{method:'DELETE'}});
  const d=await r.json();
  if(!d.ok){{alert('Error: '+(d.error||''));return;}}
  location.reload();
}}

function updModels(){{
  const p=document.getElementById('np').value;
  const s=document.getElementById('nm');
  s.innerHTML=(PROVS[p]?.models||[]).map(m=>`<option value="${{m}}">${{m}}</option>`).join('');
}}
updModels();

function refreshSubprojectForm(scope='main'){{
  const suffix=scope==='config' ? '-config' : '';
  const stack=document.getElementById('subproject-stack'+suffix)?.value||'BACK';
  const substackSelect=document.getElementById('subproject-substack'+suffix);
  const skillsSelect=document.getElementById('subproject-skills'+suffix);
  if(substackSelect){{
    const options=SUBSTACK_OPTIONS[stack]||[];
    const current=substackSelect.value;
    substackSelect.innerHTML=options.map(value=>`<option value="${{value}}">${{value}}</option>`).join('');
    if(current && options.includes(current))substackSelect.value=current;
  }}
  if(skillsSelect){{
    const selectedSubstack=substackSelect?.value||'';
    const recommended=TEAM_PRESETS.find(team=>((team.stack_key||'')===stack) && (!(team.substacks||[]).length || (team.substacks||[]).includes(selectedSubstack)));
    const allowed=Object.entries(SPECS).filter(([key, spec])=>spec.role!=='pm' && spec.role!=='orchestrator' && (spec.stack_key||'')===stack);
    skillsSelect.innerHTML=allowed.map(([key, spec])=>`<option value="${{key}}">${{spec.label}}</option>`).join('');
    Array.from(skillsSelect.options).forEach(option=>option.selected=(recommended?.skills||[]).includes(option.value));
  }}
  const devModel=document.getElementById('subproject-dev-model'+suffix);
  const qaModel=document.getElementById('subproject-qa-model'+suffix);
  if(devModel && !devModel.value && SYSTEM_ROLE_DEFAULTS.developers)devModel.value=SYSTEM_ROLE_DEFAULTS.developers;
  if(qaModel && !qaModel.value && SYSTEM_ROLE_DEFAULTS.qa)qaModel.value=SYSTEM_ROLE_DEFAULTS.qa;
}}

function refreshSpecializationOptions(){{
  const type=document.getElementById('nt')?.value||'dev';
  const select=document.getElementById('ns');
  const activeTeam=TEAM_PRESETS.find(team=>team.id===ACTIVE_TEAM_ID) || null;
  const allowedSkills=new Set(activeTeam?.skills||[]);
  const options=Object.entries(SPECS).filter(([key, spec])=>{{
    if(type==='qa')return spec.role==='qa';
    if(type!=='dev')return spec.role===type;
    if(!ACTIVE_TEAM_ID)return spec.role==='developer';
    return spec.role==='developer' && allowedSkills.has(key);
  }});
  select.innerHTML=options.map(([key, spec])=>`<option value="${{key}}">${{spec.label}} (${{spec.stack||'ALL'}})</option>`).join('');
}}
refreshSpecializationOptions();

function refreshSprintTeams(){{
  const stack=document.getElementById('sprint-stack')?.value||'';
  const substack=document.getElementById('sprint-substack')?.value||'';
  const sel=document.getElementById('sprint-team');
  if(!sel)return;
  const teams=TEAM_PRESETS.filter(team=>((team.stack_key||'')===stack||!stack) && (!substack || !(team.substacks||[]).length || (team.substacks||[]).includes(substack)));
  sel.innerHTML=teams.map(team=>`<option value="${{team.id}}">${{team.label}}${{team.substacks?.length ? ' · '+team.substacks.join(', ') : ''}}</option>`).join('');
}}

function refreshTeamSkills(){{
  const subprojectId=document.getElementById('sprint-subproject')?.value||'';
  const stack=document.getElementById('sprint-stack')?.value||'';
  const select=document.getElementById('new-team-skills');
  if(!select)return;
  const allowed=Object.entries(SPECS).filter(([key, spec])=>spec.role==='developer' && (spec.stack_key||'')===stack);
  select.innerHTML=allowed.map(([key, spec])=>`<option value="${{key}}">${{spec.label}}</option>`).join('');
  const suggested=TEAM_PRESETS.find(team=>((team.stack_key||'')===stack) && (!(team.substacks||[]).length || (team.substacks||[]).includes(document.getElementById('sprint-substack')?.value||'')));
  if(suggested){{
    Array.from(select.options).forEach(option=>option.selected=(suggested.skills||[]).includes(option.value));
  }}
  const stackName=document.getElementById('new-team-stack-name');
  if(stackName && !stackName.value){{
    const subproject=SUBPROJECTS.find(item=>item.id===subprojectId);
    stackName.value=subproject?.stack_name||stack||'';
  }}
}}

function refreshSprintScope(){{
  const subprojectSelect=document.getElementById('sprint-subproject');
  if(subprojectSelect && !sprintScopeInitialized && ACTIVE_SUBPROJECT_ID && subprojectSelect.value!==ACTIVE_SUBPROJECT_ID){{
    subprojectSelect.value=ACTIVE_SUBPROJECT_ID;
  }}
  sprintScopeInitialized = true;
  const subprojectId=document.getElementById('sprint-subproject')?.value||'';
  const subproject=SUBPROJECTS.find(item=>item.id===subprojectId);
  document.getElementById('sprint-stack').value=subproject?.stack_key||'';
  document.getElementById('sprint-substack').value=subproject?.substack||'';
  refreshSprintTeams();
  refreshTeamSkills();
}}

function toggleTeamMode(){{
  const mode=document.getElementById('sprint-team-mode')?.value||'reuse';
  document.getElementById('reuse-team-group').style.display=mode==='reuse'?'block':'none';
  document.getElementById('create-team-group').style.display=mode==='create'?'block':'none';
}}

refreshSprintScope();
toggleTeamMode();
refreshSubprojectForm();
refreshSubprojectForm('config');

async function addAgent(){{
  const spec=document.getElementById('ns').value;
  const prov=document.getElementById('np').value;
  const model=document.getElementById('nm').value;
  const type=document.getElementById('nt').value;
  const name=document.getElementById('nn').value;
  const role=SPECS[spec]?.role||(type==='dev'?'developer':type);
  const stack=SPECS[spec]?.stack||'backend';
  const stack_key=SPECS[spec]?.stack_key||'BACK';
  if(type==='dev' && (!ACTIVE_PROJECT_ID || !ACTIVE_SPRINT_ID || !ACTIVE_TEAM_ID)){{alert('Los nuevos developers solo pueden crearse dentro de un sprint con equipo asignado.');return;}}
  const id=type+'_'+spec+'_'+Date.now().toString(36);
  const r=await fetch('/api/agents',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{id,name:name||spec,type,role,stack,stack_key,specialization:spec,provider:prov,model,project_id:ACTIVE_PROJECT_ID,sprint_id:ACTIVE_SPRINT_ID,team_id:ACTIVE_TEAM_ID}})}});
  const d=await r.json();
  if(d.ok){{document.getElementById('mbg').classList.remove('open');location.reload();}}
  else alert('Error: '+d.error);
}}

async function openTerminal(id){{
  const r=await fetch('/api/agents/'+id+'/terminal',{{method:'POST'}});
  const d=await r.json();
  if(!d.ok)alert('No se pudo abrir terminal: '+(d.error||''));
}}

async function dismissAlert(tid){{
  await fetch('/api/alerts/'+tid,{{method:'DELETE'}});
  location.reload();
}}

async function saveSchedule(){{
  const st=document.getElementById('st').value;
  const sp=document.getElementById('sp').value;
  await fetch('/api/schedule',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{start_time:st||null,stop_time:sp||null,enabled:true}})}});
  document.getElementById('ss').textContent='Guardado \u2713';
}}

async function savePlatformSettings(){{
  const coding=document.getElementById('platform-coding-rules').value;
  const git=document.getElementById('platform-git-rules').value;
  const token=document.getElementById('platform-token-rules').value;
  const r=await fetch('/api/platform-settings',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{
      coding_rules:coding.split('\\n'),
      git_rules:git.split('\\n'),
      token_optimization_rules:token.split('\\n')
    }})}});
  const d=await r.json();
  if(!d.ok){{alert('Error: '+(d.error||''));return;}}
  alert('Reglas globales guardadas');
}}

function filterSprint(sprintId){{
  const sprint=SPRINTS.find(item=>item.sprint_id===sprintId) || null;
  if(ACTIVE_PROJECT_ID){{
    fetch('/api/projects/runtime',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{
      project_id:ACTIVE_PROJECT_ID,
      last_sprint_id:sprintId,
      team_id:sprint?.team_id||ACTIVE_TEAM_ID,
      subproject_id:sprint?.subproject_id||''
    }})}}).catch(()=>null);
  }}
  const url=new URL(window.location.href);
  if(sprintId)url.searchParams.set('sprint',sprintId);
  else url.searchParams.delete('sprint');
  window.location.href=url.toString();
}}

async function uploadPlan(input){{
  const file=input.files[0];
  if(!file)return;
  const st=document.getElementById('upload-status');
  st.textContent='Subiendo...';
  const fd=new FormData();fd.append('file',file);
  try{{
    const r=await fetch('/api/upload-plan',{{method:'POST',body:fd}});
    const d=await r.json();
    if(d.ok){{
      st.style.color='#22c55e';
      st.textContent='Sprint '+d.sprint_id+' creado ('+d.tasks_created+' tareas)';
      setTimeout(()=>location.reload(),1500);
    }}else{{
      st.style.color='#f87171';
      st.textContent='Error: '+(d.error||'desconocido');
    }}
  }}catch(e){{st.style.color='#f87171';st.textContent='Error de red';}}
  input.value='';
}}

async function controlSprint(sprintId, action){{
  const labels = {{pause:'pausar', resume:'reanudar'}};
  if(!confirm('¿Seguro que deseas '+labels[action]+' el sprint '+sprintId+'?'))return;
  const r=await fetch('/api/sprint/'+sprintId+'/'+action,{{method:'POST'}});
  const d=await r.json();
  if(d.ok){{alert(d.message||'Listo');location.reload();}}
  else alert('Error: '+(d.error||'desconocido'));
}}

function showTaskDetail(taskId){{
  fetch('/api/tasks/'+taskId).then(r=>r.json()).then(d=>{{
    if(!d.ok)return;
    const t=d.task;
    const ac=(t.acceptance_criteria||[]).map(c=>'<li>'+c+'</li>').join('');
    const deps=(t.depends_on||[]).join(', ')||'ninguna';
    alert(t.task_id+' — '+t.summary+
      '\\nPrioridad: '+t.priority+'  |  Sprint: '+(t.sprint_id||'—')+
      '\\nParalelo: '+(t.parallel?'Si':'No')+
      '\\nDepende de: '+deps+
      (ac?'\\n\\nCriterios:\\n'+(t.acceptance_criteria||[]).join('\\n  - '):''));
  }});
}}

// ── UNIFIED CONFIG MANAGEMENT ──────────────────────────────────────────────────────
function openConfigModal(){{
  document.getElementById('config-modal-bg').classList.add('open');
  loadProjectList();
  refreshSubprojectForm('config');
}}
function closeConfigModal(){{
  document.getElementById('config-modal-bg').classList.remove('open');
}}

async function loadProjectList(){{
  const r=await fetch('/api/projects');
  const projects=await r.json();
  let html='<div style="font-size:10px;color:#64748b;margin-bottom:8px">Cambiar proyecto:</div>';
  for(const p of projects){{
    html+=`<button class="btn btn-outline btn-sm" style="width:100%;text-align:left;margin-bottom:4px;padding:6px;font-size:11px" onclick="selectProject('${{p.project_id}}')">✓ ${{p.name}}</button>`;
  }}
  document.getElementById('project-list').innerHTML=html;
}}

async function selectProject(projectId){{
  const r=await fetch('/api/projects/active',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{
      project_id:projectId,
      previous_project_id:ACTIVE_PROJECT_ID,
      previous_sprint_id:(document.getElementById('sprint-sel')?.value||ACTIVE_SPRINT_ID),
      previous_team_id:ACTIVE_TEAM_ID,
      previous_subproject_id:(document.getElementById('sprint-subproject')?.value||'')
    }})}});
  const d=await r.json();
  if(!d.ok){{alert('Error: '+(d.error||''));return;}}
  window.location.href=d.redirect_url||window.location.href.split('?')[0];
}}

async function createProject(){{
  const name=(document.getElementById('onboard-proj-name')?.value||document.getElementById('new-proj-name')?.value||'').trim();
  const desc=(document.getElementById('onboard-proj-desc')?.value||document.getElementById('new-proj-desc')?.value||'').trim();
  const template_id=document.getElementById('project-template-sel')?.value||'software_delivery_default';
  if(!name||!desc){{alert('Nombre y descripcion son requeridos');return;}}
  const r=await fetch('/api/projects/create',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{name,description:desc,git_dirs:{{}},template_id}})}});
  const d=await r.json();
  if(d.ok){{
    alert('Proyecto '+name+' creado correctamente');
    if(document.getElementById('new-proj-name'))document.getElementById('new-proj-name').value='';
    if(document.getElementById('new-proj-desc'))document.getElementById('new-proj-desc').value='';
    if(document.getElementById('onboard-proj-name'))document.getElementById('onboard-proj-name').value='';
    if(document.getElementById('onboard-proj-desc'))document.getElementById('onboard-proj-desc').value='';
    loadProjectList();
    location.reload();
  }}
  else alert('Error: '+(d.error||''));
}}

async function createSubproject(scope='main'){{
  const suffix=scope==='config' ? '-config' : '';
  const projectId=ACTIVE_PROJECT_ID;
  if(!projectId){{alert('Debes seleccionar o crear un proyecto');return;}}
  const label=(document.getElementById('subproject-name'+suffix)?.value||'').trim();
  const stack_key=(document.getElementById('subproject-stack'+suffix)?.value||'').trim();
  const baseSubstack=(document.getElementById('subproject-substack'+suffix)?.value||'').trim();
  const customSubstack=(document.getElementById('subproject-substack-custom'+suffix)?.value||'').trim();
  const substack=(customSubstack||baseSubstack).trim();
  const repo_dir=(document.getElementById('subproject-repo'+suffix)?.value||'').trim();
  const skills=Array.from(document.getElementById('subproject-skills'+suffix)?.selectedOptions||[]).map(option=>option.value);
  const dev_model_profile=(document.getElementById('subproject-dev-model'+suffix)?.value||SYSTEM_ROLE_DEFAULTS.developers||'').trim();
  const qa_model_profile=(document.getElementById('subproject-qa-model'+suffix)?.value||SYSTEM_ROLE_DEFAULTS.qa||'').trim();
  if(!label||!stack_key||!substack||!repo_dir){{alert('Nombre, stack, substack y repositorio son obligatorios');return;}}
  const r=await fetch('/api/projects/'+projectId+'/subprojects',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{label,stack_key,substack,repo_dir,skills,dev_model_profile,qa_model_profile}})}});  
  const d=await r.json();
  if(!d.ok){{alert('Error: '+(d.error||''));return;}}
  alert('Subproyecto guardado');
  location.reload();
}}

async function saveGitDirs(){{
  const back=document.getElementById('git-back').value.trim();
  const webBo=document.getElementById('git-web-bo').value.trim();
  const webLanding=document.getElementById('git-web-landing').value.trim();
  const android=document.getElementById('git-android').value.trim();
  const ios=document.getElementById('git-ios').value.trim();
  const flutter=document.getElementById('git-flutter').value.trim();
  const git_dirs={{}};
  if(back) git_dirs.BACK=back;
  if(webBo) git_dirs.WEB_BACKOFFICE=webBo;
  if(webLanding) git_dirs.WEB_LANDING=webLanding;
  if(android) git_dirs.ANDROID=android;
  if(ios) git_dirs.IOS=ios;
  if(flutter) git_dirs.FLUTTER=flutter;
  if(!ACTIVE_PROJECT_ID){{alert('Debes seleccionar un proyecto');return;}}
  if(!Object.keys(git_dirs).length){{alert('Debes configurar al menos un repositorio');return;}}

  const r=await fetch('/api/projects/'+ACTIVE_PROJECT_ID+'/config',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{git_dirs}})}});
  const d=await r.json();
  if(d.ok){{
    alert('Directorios Git guardados');
    location.reload();
  }}
  else alert('Error: '+(d.error||''));
}}

async function updateProjectTemplate(template_id){{
  if(!ACTIVE_PROJECT_ID){{alert('Debes seleccionar un proyecto');return;}}
  const r=await fetch('/api/projects/'+ACTIVE_PROJECT_ID+'/template',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{template_id}})}});
  const d=await r.json();
  if(!d.ok){{alert('Error: '+(d.error||''));return;}}
  location.reload();
}}

function openSprintModal(){{
  if(!ACTIVE_PROJECT_ID){{alert('Debes crear o seleccionar un proyecto antes de crear un sprint');return;}}
  document.getElementById('sprint-modal-bg').classList.add('open');
}}
function closeSprintModal(){{
  document.getElementById('sprint-modal-bg').classList.remove('open');
}}
async function createSprint(){{
  if(!ACTIVE_PROJECT_ID){{alert('Debes seleccionar o crear un proyecto antes de crear un sprint');return;}}
  const id=document.getElementById('sprint-id').value.trim();
  const name=document.getElementById('sprint-name').value.trim();
  const stack=document.getElementById('sprint-stack').value;
  const substack=document.getElementById('sprint-substack').value;
  const subproject_id=document.getElementById('sprint-subproject').value;
  const team_mode=document.getElementById('sprint-team-mode').value;
  const team_id=team_mode==='reuse' ? document.getElementById('sprint-team').value : '';
  const tasksJson=document.getElementById('sprint-tasks').value.trim();
  if(!id||!name){{alert('Sprint ID y Nombre requeridos');return;}}
  if(!subproject_id){{alert('Debes seleccionar un subproyecto');return;}}
  if(team_mode==='reuse' && !team_id){{alert('Debes asignar un equipo al sprint');return;}}
  let tasks=[];
  try{{
    tasks=tasksJson?JSON.parse(tasksJson):[];
  }}catch(e){{
    alert('Error en JSON de tareas: '+e.message);
    return;
  }}
  const create_team=team_mode==='create' ? {{
    label:document.getElementById('new-team-label').value.trim(),
    stack_key:stack,
    stack_name:document.getElementById('new-team-stack-name').value.trim()||stack,
    substacks:[substack].filter(Boolean),
    subproject_id,
    skills:Array.from(document.getElementById('new-team-skills').selectedOptions).map(option=>option.value)
  }} : null;
  if(team_mode==='create' && (!create_team.label || !create_team.skills.length)){{alert('Debes definir nombre y skills para el nuevo equipo');return;}}
  const r=await fetch('/api/sprints/create',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{project_id:ACTIVE_PROJECT_ID,sprint_id:id,name,stack,substack,subproject_id,team_id,tasks,create_team}})}});
  const d=await r.json();
  if(d.ok){{alert('Sprint '+id+' creado con '+d.result.tasks_created+' tareas');closeSprintModal();location.reload();}}
  else alert('Error: '+(d.error||''));
}}
</script></body></html>"""

# ── HTTP Handler ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def _json(self, data, status=200):
        body=json.dumps(data).encode()
        self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",len(body));self.end_headers();self.wfile.write(body)
    def _text(self, text, status=200):
        body=text.encode("utf-8","replace")
        self.send_response(status);self.send_header("Content-Type","text/plain; charset=utf-8");self.send_header("Content-Length",len(body));self.end_headers();self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        p = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)
        if p in ("","/"):
            sprint_id = qs.get("sprint",[""])[0]
            data=build_data(sprint_id);html=render(data).encode("utf-8")
            self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",len(html));self.end_headers();self.wfile.write(html)
        elif p.startswith("/api/agents/") and p.endswith("/log"):
            self._text(get_log(p.split("/")[3], lines=80))
        elif p.startswith("/api/tasks/"):
            task_id = p[len("/api/tasks/"):]
            try:
                from app_core.memory_store import MemoryStore
                task = MemoryStore().board_get_task(task_id)
                if task:
                    self._json({"ok": True, "task": task})
                else:
                    self._json({"ok": False, "error": "not found"}, 404)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
        else:
            self._json({"error":"not found"},404)

    def do_POST(self):
        p=urlparse(self.path).path.rstrip("/")
        # Multipart upload must be handled before the generic JSON body read
        if p == "/api/upload-plan":
            self._handle_upload_plan()
            return
        n=int(self.headers.get("Content-Length",0))
        body=json.loads(self.rfile.read(n)) if n else {}
        if p=="/api/system/start":     self._json(start_all(body.get("team_id") or None))
        elif p=="/api/system/stop":    self._json(stop_all())
        elif p.endswith("/start"):      self._json(start_agent(p.split("/")[3]))
        elif p.endswith("/stop"):       self._json(stop_agent(p.split("/")[3]))
        elif p.endswith("/terminal"):   self._json(open_terminal(p.split("/")[3]))
        elif p.endswith("/enabled"):    self._json(set_agent_enabled(p.split("/")[3], bool(body.get("enabled", True))))
        elif p=="/api/agents":
            try:
                if body.get("role") == "developer":
                    sprint = MemoryStore().sprint_get(body.get("sprint_id", ""))
                    if not sprint:
                        self._json({"ok": False, "error": "Debes seleccionar un sprint valido para agregar developers."}, 400)
                        return
                    if sprint.get("project_id") != body.get("project_id"):
                        self._json({"ok": False, "error": "El sprint no pertenece al proyecto activo."}, 400)
                        return
                    if sprint.get("team_id") != body.get("team_id"):
                        self._json({"ok": False, "error": "El team del sprint no coincide con el agent solicitado."}, 400)
                        return
                    ok, error = validate_agent_for_team(body, body.get("team_id"))
                    if not ok:
                        self._json({"ok": False, "error": error}, 400)
                        return
                    body["removable"] = False
                    body["locked_to_team"] = True
                self._json(add_agent(body))
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
        elif p=="/api/team/stack":     self._json(set_agents_enabled_for_stack(body.get("stack_key", ""), bool(body.get("enabled", True))))
        elif p=="/api/schedule":       save_schedule(body);self._json({"ok":True})
        elif p.startswith("/api/sprint/") and p.endswith("/pause"):
            sid = p.split("/")[3]
            msg = MemoryStore().sprint_pause(sid)
            self._json({"ok": True, "message": msg})
        elif p.startswith("/api/sprint/") and p.endswith("/resume"):
            sid = p.split("/")[3]
            msg = MemoryStore().sprint_resume(sid)
            self._json({"ok": True, "message": msg})
        elif p == "/api/projects":
            self._json(MemoryStore().project_list())
        elif p == "/api/projects/create":
            try:
                project_id = body.get("project_id", "") or _generate_project_id(body.get("name", ""))
                body["project_id"] = project_id
                store = MemoryStore()
                if not project_id:
                    self._json({"ok": False, "error": "No se pudo generar un ID valido para el proyecto."}, 400)
                    return
                if store.get_project(project_id):
                    self._json({"ok": False, "error": "El proyecto ya existe."}, 400)
                    return
                store.project_create(
                    project_id,
                    body.get("name", ""),
                    body.get("description", ""),
                    body.get("git_dirs", {}),
                    body.get("template_id", "software_delivery_default"),
                )
                set_active_project_id(project_id, store)
                _save_dashboard_index_state(store, project_id)
                self._json({"ok": True, "project_id": project_id})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
        elif p.startswith("/api/projects/") and p.endswith("/subprojects"):
            project_id = p.split("/")[3]
            try:
                store = MemoryStore()
                current = require_project_context(store, project_id)
                subproject_id = body.get("id") or body.get("label", "")
                normalized_git_dirs = upsert_subproject_config(
                    current.get("git_dirs", {}),
                    {
                        "id": _generate_project_id(subproject_id),
                        "label": body.get("label", ""),
                        "repo_dir": body.get("repo_dir", ""),
                        "stack_key": body.get("stack_key", ""),
                        "substack": body.get("substack", ""),
                        "skills": body.get("skills") or default_skills_for_scope(body.get("stack_key", ""), body.get("substack", "")),
                        "dev_model_profile": body.get("dev_model_profile", ""),
                        "qa_model_profile": body.get("qa_model_profile", ""),
                    },
                )
                preview = _preview_project_context(
                    project_id=project_id,
                    name=current.get("name", project_id),
                    description=current.get("description", ""),
                    template_id=current.get("template_id", "software_delivery_default"),
                    git_dirs=normalized_git_dirs,
                    directives=current.get("directives", {}),
                )
                if preview["validation_errors"] and "project requires at least one repository" not in preview["validation_errors"]:
                    self._json({"ok": False, "error": "; ".join(preview["validation_errors"])}, 400)
                    return
                store.project_update_git_dirs(project_id, normalized_git_dirs)
                self._json({"ok": True, "subprojects": normalize_project_subprojects(normalized_git_dirs)})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
        elif p == "/api/projects/active":
            try:
                store = MemoryStore()
                project_id = body.get("project_id", "")
                if not store.get_project(project_id):
                    self._json({"ok": False, "error": "El proyecto no existe."}, 400)
                    return
                previous_project_id = body.get("previous_project_id", "")
                previous_sprint_id = body.get("previous_sprint_id", "")
                if previous_project_id:
                    store.save_project_runtime_state(
                        previous_project_id,
                        last_sprint_id=previous_sprint_id,
                        context={
                            "team_id": body.get("previous_team_id", ""),
                            "subproject_id": body.get("previous_subproject_id", ""),
                        },
                    )
                set_active_project_id(project_id, store)
                runtime_state = store.get_project_runtime_state(project_id)
                _save_dashboard_index_state(
                    store,
                    project_id,
                    runtime_state.get("last_sprint_id", ""),
                    runtime_state.get("context", {}).get("team_id", ""),
                    runtime_state.get("context", {}).get("subproject_id", ""),
                )
                redirect_url = f"/?sprint={runtime_state.get('last_sprint_id')}" if runtime_state.get("last_sprint_id") else "/"
                self._json({"ok": True, "redirect_url": redirect_url})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
        elif p == "/api/projects/runtime":
            try:
                store = MemoryStore()
                project_id = body.get("project_id", "")
                store.save_project_runtime_state(
                    project_id,
                    last_sprint_id=body.get("last_sprint_id", ""),
                    context={
                        "team_id": body.get("team_id", ""),
                        "subproject_id": body.get("subproject_id", ""),
                    },
                )
                _save_dashboard_index_state(
                    store,
                    project_id,
                    body.get("last_sprint_id", ""),
                    body.get("team_id", ""),
                    body.get("subproject_id", ""),
                )
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
        elif p == "/api/platform-settings":
            try:
                settings = save_platform_settings(body)
                self._json({"ok": True, "settings": settings})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
        elif p.startswith("/api/projects/") and p.endswith("/config"):
            project_id = p.split("/")[3]
            try:
                store = MemoryStore()
                current = require_project_context(store, project_id)
                merged_git_dirs = dict(current.get("git_dirs", {}))
                for key, value in (body.get("git_dirs", {}) or {}).items():
                    existing = merged_git_dirs.get(key)
                    if isinstance(existing, dict):
                        merged_git_dirs[key] = {**existing, "repo_dir": value}
                    else:
                        merged_git_dirs[key] = value
                preview = _preview_project_context(
                    project_id=project_id,
                    name=current.get("name", project_id),
                    description=current.get("description", ""),
                    template_id=current.get("template_id", "software_delivery_default"),
                    git_dirs=merged_git_dirs,
                    directives=current.get("directives", {}),
                )
                if preview["validation_errors"]:
                    self._json({"ok": False, "error": "; ".join(preview["validation_errors"])}, 400)
                    return
                store.project_update_git_dirs(project_id, merged_git_dirs)
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
        elif p.startswith("/api/projects/") and p.endswith("/template"):
            project_id = p.split("/")[3]
            try:
                store = MemoryStore()
                current = require_project_context(store, project_id)
                preview = _preview_project_context(
                    project_id=project_id,
                    name=current.get("name", project_id),
                    description=current.get("description", ""),
                    template_id=body.get("template_id", "software_delivery_default"),
                    git_dirs=current.get("git_dirs", {}),
                    directives=current.get("directives", {}),
                )
                if preview["validation_errors"]:
                    self._json({"ok": False, "error": "; ".join(preview["validation_errors"])}, 400)
                    return
                store.project_set_template(project_id, body.get("template_id", "software_delivery_default"))
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
        elif p == "/api/sprints/create":
            from app_core.sprint_manager import create_sprint_from_plan
            try:
                store = MemoryStore()
                project_context = require_project_context(store, body.get("project_id"))
                subproject = get_subproject_definition(body.get("subproject_id", ""))
                stack = resolve_stack_for_project(project_context, body.get("stack", subproject.get("stack_key", "BACK")))
                team = None
                if body.get("create_team"):
                    create_result = create_team_preset({
                        **body.get("create_team", {}),
                        "stack_key": stack,
                        "substacks": [body.get("substack", subproject.get("substack", ""))],
                        "subproject_id": body.get("subproject_id", ""),
                    })
                    if not create_result.get("ok"):
                        self._json({"ok": False, "error": create_result.get("error", "No se pudo crear el equipo.")}, 400)
                        return
                    body["team_id"] = create_result["team_id"]
                    team = create_result["team"]
                else:
                    team = get_team_preset(body.get("team_id"))
                if not team:
                    self._json({"ok": False, "error": "Debes asignar un equipo valido al sprint."}, 400)
                    return
                # Expect: {sprint_id, name, stack, tasks: [{id, summary, depends_on, parallel}]}
                plan = {
                    "sprint_id": body.get("sprint_id", ""),
                    "name": body.get("name", ""),
                    "project_id": project_context["project_id"],
                    "stack": stack,
                    "substack": body.get("substack", subproject.get("substack", "")),
                    "subproject_id": body.get("subproject_id", ""),
                    "team_id": body.get("team_id", ""),
                    "team_snapshot": team,
                    "tasks": body.get("tasks", [])
                }
                result = create_sprint_from_plan(plan, store)
                for agent in get_agents_with_eligibility(stack_key=stack, preset_name=team["id"]):
                    if agent.get("role") == "developer":
                        update_agent(agent["id"], {"removable": False, "team_id": team["id"]})
                set_active_project_id(project_context["project_id"], store)
                _save_dashboard_index_state(
                    store,
                    project_context["project_id"],
                    plan["sprint_id"],
                    team["id"],
                    plan["subproject_id"],
                )
                global _board_cache_ts
                _board_cache_ts = 0
                self._json({"ok": True, "sprint_id": plan["sprint_id"], "team_id": body.get("team_id", ""), "result": result})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
        else:                          self._json({"error":"not found"},404)

    def _handle_upload_plan(self):
        try:
            ctype = self.headers.get("Content-Type", "")
            environ = {
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": ctype,
                "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
            }
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ=environ)
            if "file" not in form:
                self._json({"ok": False, "error": "No file in request"}); return
            item = form["file"]
            try:
                content = item.file.read().decode("utf-8", "replace")
            except Exception as e:
                self._json({"ok": False, "error": f"Read error: {e}"}); return
            from app_core.sprint_manager import parse_plan, create_sprint_from_plan
            from app_core.memory_store import MemoryStore
            plan = parse_plan(content)
            if not plan:
                self._json({"ok": False, "error": "Could not parse plan (use JSON or Markdown format)"}); return
            result = create_sprint_from_plan(plan, MemoryStore())
            # Invalidate board cache so new tasks appear immediately
            global _board_cache_ts
            _board_cache_ts = 0
            self._json({"ok": True, "sprint_id": plan["sprint_id"],
                        "tasks_created": result["tasks_created"],
                        "tasks_skipped": result["tasks_skipped"]})
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)

    def do_DELETE(self):
        p=urlparse(self.path).path.rstrip("/")
        parts=p.split("/")
        if len(parts)==4 and parts[2]=="agents":   self._json(remove_agent(parts[3]))
        elif len(parts)==4 and parts[2]=="alerts":  clear_alert(parts[3]);self._json({"ok":True})
        else:                                        self._json({"error":"not found"},404)

    def log_message(self, *args): pass

# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    start_scheduler()
    url = f"http://localhost:{PORT}"
    print(f"\n  VeloxIq Dashboard → {url}")
    print("  Ctrl+C para detener\n")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    HTTPServer(("", PORT), Handler).serve_forever()
