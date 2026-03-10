#!/usr/bin/env python3
"""
dashboard.py — Panel de control VeloxIq
python dashboard.py → http://localhost:8888
"""

import os, sys, json, sqlite3, threading, webbrowser, subprocess, cgi
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from urllib.parse import urlparse, parse_qs

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from app_core.agent_manager import (
    load_agents, load_specializations, get_log, get_current_task,
    get_agent, start_agent, stop_agent, start_all, stop_all, is_running,
    add_agent, remove_agent, system_running, get_team_status,
    get_agents_with_eligibility, set_active_preset, set_agents_enabled_for_stack,
    set_agent_enabled,
    get_schedule, save_schedule, start_scheduler,
)
from app_core.alert_manager import get_active_alerts, clear_alert

BASE_DIR = Path(__file__).parent
PORT     = 8888

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

def get_local_board_data(sprint_id: str = "") -> dict:
    global _board_cache, _board_cache_ts
    import time
    cache_key = sprint_id or "__all__"
    if time.time() - _board_cache_ts < 10 and _board_cache.get("_key") == cache_key:
        return _board_cache

    db = BASE_DIR / "memory" / "veloxiq_memory.db"
    stacks  = {k: {"total": 0, "verified": 0, "by_state": {}} for k in ["BACK", "BO", "MOB"]}
    parsed  = []
    sprints = []
    active_sprint = {"name": "Sprint Local", "sprint_id": "", "stack": ""}

    if db.exists():
        try:
            con = sqlite3.connect(db)

            # Load sprints list
            sprint_rows = con.execute(
                "SELECT sprint_id, name, stack, status FROM sprints ORDER BY created_at DESC"
            ).fetchall()
            for sr in sprint_rows:
                sprints.append({"sprint_id": sr[0], "name": sr[1], "stack": sr[2], "status": sr[3]})
                if sr[3] == "active" and not sprint_id:
                    active_sprint = {"name": sr[1], "sprint_id": sr[0], "stack": sr[2]}

            # Load tasks filtered by sprint
            if sprint_id:
                rows = con.execute(
                    "SELECT task_id, summary, state, stack, priority, depends_on, parallel, sprint_id "
                    "FROM local_board WHERE sprint_id=? ORDER BY created_at ASC", (sprint_id,)
                ).fetchall()
                # Sprint name for selected sprint
                for sr in sprints:
                    if sr["sprint_id"] == sprint_id:
                        active_sprint = {"name": sr["name"], "sprint_id": sprint_id, "stack": sr["stack"]}
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
    yt         = get_local_board_data(sprint_id)
    tc         = local_token_stats()
    endpoints  = local_certified_endpoints()
    schedule   = get_schedule()
    providers  = json.loads((BASE_DIR/"config"/"agents.json").read_text())["providers"]
    active_stack = (yt.get("active_sprint") or {}).get("stack", "")
    team_status = get_team_status()
    agents_cfg = get_agents_with_eligibility(
        stack_key=active_stack or None,
        preset_name=team_status["active_preset"],
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
    return {"agents":agents_out,"yt":yt,"tc":tc,"endpoints":endpoints,
            "schedule":schedule,"sys_running":system_running(),
            "updated_at":datetime.now().strftime("%H:%M:%S"),
            "specs":load_specializations(),"providers":providers,
            "alerts":alerts,"team":team_status,"active_stack":active_stack}

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
  <h2 style="color:{color}">SEGURO-{name} <span style="font-size:11px;color:#475569;font-weight:400">{labels[name]}</span></h2>
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
        sprint_opts += f'<option value="{sp["sprint_id"]}"{sel}>{sp["sprint_id"]} — {sp["name"]}{status_mark}</option>'
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
    preset_opts = "".join(
        f'<option value="{preset["id"]}"{" selected" if preset["active"] else ""}>{preset["label"]}</option>'
        for preset in team.get("presets", [])
    )

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
  <span class="subtitle">SeguroAuto &nbsp;·&nbsp; {data['updated_at']} &nbsp;·&nbsp; <span id="cd">30</span>s</span>
  <button class="btn {'btn-red' if sys_run else 'btn-green'}" onclick="systemToggle()">
    {'Apagar' if sys_run else 'Encender'}
  </button>
  <button class="btn btn-blue" onclick="document.getElementById('mbg').classList.add('open')">+ Agente</button>
  <button class="btn btn-blue" onclick="openConfigModal()" style="background:#8b5cf6">Configuracion</button>
  <button class="btn btn-blue" onclick="openSprintModal()" style="background:#d946ef">+ Sprint</button>
</div>

<div class="section" style="margin-bottom:12px">
  <div class="section-title">Equipo activo</div>
  <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
    <select id="preset-sel" onchange="changePreset(this.value)" style="max-width:240px">
      {preset_opts}
    </select>
    <span style="font-size:11px;color:#64748b">Stack actual: {active_stack or 'ALL'}</span>
    <button class="btn btn-sm btn-outline" onclick="toggleStack('BACK', true)">BACK on</button>
    <button class="btn btn-sm btn-outline" onclick="toggleStack('BACK', false)">BACK off</button>
    <button class="btn btn-sm btn-outline" onclick="toggleStack('BO', true)">BO on</button>
    <button class="btn btn-sm btn-outline" onclick="toggleStack('BO', false)">BO off</button>
    <button class="btn btn-sm btn-outline" onclick="toggleStack('MOB', true)">MOB on</button>
    <button class="btn btn-sm btn-outline" onclick="toggleStack('MOB', false)">MOB off</button>
  </div>
</div>

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

<!-- MODAL -->
<div class="modal-bg" id="mbg">
  <div class="modal">
    <h3>Agregar agente</h3>
    <div class="fg"><label>Tipo</label>
      <select id="nt"><option value="dev">Dev</option><option value="qa">QA</option></select></div>
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

    <!-- TAB 1: PROYECTOS -->
    <div style="margin-bottom:20px;border-bottom:1px solid #334155;padding-bottom:15px">
      <h4 style="font-size:13px;color:#94a3b8;margin-bottom:10px">PROYECTOS</h4>
      <div id="project-list" style="max-height:150px;overflow-y:auto;margin-bottom:12px"></div>

      <div class="fg">
        <label>ID del Proyecto</label>
        <input type="text" id="new-proj-id" placeholder="Ej: SEGURO, ACME">
      </div>
      <div class="fg">
        <label>Nombre del Proyecto</label>
        <input type="text" id="new-proj-name" placeholder="Nombre completo">
      </div>
      <div class="fg">
        <label>Descripcion (opcional)</label>
        <input type="text" id="new-proj-desc" placeholder="Detalles del proyecto">
      </div>
      <button class="btn btn-green" onclick="createProject()" style="width:100%">Crear Proyecto</button>
    </div>

    <!-- TAB 2: DIRECTORIOS GIT -->
    <div style="margin-bottom:20px;border-bottom:1px solid #334155;padding-bottom:15px">
      <h4 style="font-size:13px;color:#94a3b8;margin-bottom:10px">DIRECTORIOS GIT (Rutas locales)</h4>
      <div class="fg">
        <label>BACK (FastAPI · PostgreSQL)</label>
        <input type="text" id="git-back" placeholder="C:\\Users\\...\\repos\\backend">
      </div>
      <div class="fg">
        <label>BO (Next.js · shadcn/ui)</label>
        <input type="text" id="git-bo" placeholder="C:\\Users\\...\\repos\\backoffice">
      </div>
      <div class="fg">
        <label>MOB (Android · Compose)</label>
        <input type="text" id="git-mob" placeholder="C:\\Users\\...\\repos\\mobile">
      </div>
      <button class="btn btn-green" onclick="saveGitDirs()" style="width:100%">Guardar Directorios</button>
    </div>

    <!-- TAB 3: DIRECTIVAS DEL PROYECTO -->
    <div style="margin-bottom:20px">
      <h4 style="font-size:13px;color:#94a3b8;margin-bottom:10px">DIRECTIVAS (Reglas del proyecto)</h4>
      <div class="fg">
        <label>Estrategia de Merge</label>
        <select id="directive-merge" style="width:100%">
          <option value="squash">Squash (por defecto)</option>
          <option value="merge-commit">Merge Commit</option>
          <option value="rebase">Rebase</option>
        </select>
      </div>
      <div class="fg">
        <label>Prefijo de Feature</label>
        <input type="text" id="directive-feature-prefix" placeholder="FEAT- o VEL- o custom">
      </div>
      <div class="fg">
        <label>Rama de Desarrollo</label>
        <input type="text" id="directive-dev-branch" placeholder="develop (por defecto)">
      </div>
      <button class="btn btn-green" onclick="saveDirectives()" style="width:100%">Guardar Directivas</button>
    </div>

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
      <label>Stack</label>
      <select id="sprint-stack">
        <option value="BACK">BACK (FastAPI)</option>
        <option value="BO">BO (Next.js)</option>
        <option value="MOB">MOB (Android)</option>
      </select>
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

setInterval(()=>{{let c=document.getElementById('cd');c.textContent=+c.textContent-1;if(+c.textContent<=0)location.reload();}},1000);

async function systemToggle(){{await fetch('/api/system/{("stop" if sys_run else "start")}',{{method:'POST'}});location.reload();}}

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

async function changePreset(preset){{
  await fetch('/api/team/preset',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{preset}})}});
  location.reload();
}}

async function toggleStack(stack, enabled){{
  await fetch('/api/team/stack',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{stack_key:stack, enabled}})}});
  location.reload();
}}

async function removeAgent(id){{
  if(!confirm('¿Eliminar agente '+id+'?'))return;
  await fetch('/api/agents/'+id,{{method:'DELETE'}});location.reload();
}}

function updModels(){{
  const p=document.getElementById('np').value;
  const s=document.getElementById('nm');
  s.innerHTML=(PROVS[p]?.models||[]).map(m=>`<option value="${{m}}">${{m}}</option>`).join('');
}}
updModels();

async function addAgent(){{
  const spec=document.getElementById('ns').value;
  const prov=document.getElementById('np').value;
  const model=document.getElementById('nm').value;
  const type=document.getElementById('nt').value;
  const name=document.getElementById('nn').value;
  const role=SPECS[spec]?.role||(type==='dev'?'developer':type);
  const stack=SPECS[spec]?.stack||'backend';
  const stack_key=SPECS[spec]?.stack_key||'BACK';
  const id=type+'_'+spec+'_'+Date.now().toString(36);
  const r=await fetch('/api/agents',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{id,name:name||spec,type,role,stack,stack_key,specialization:spec,provider:prov,model}})}});
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

function filterSprint(sprintId){{
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
}}
function closeConfigModal(){{
  document.getElementById('config-modal-bg').classList.remove('open');
}}

async function loadProjectList(){{
  const r=await fetch('/api/projects');
  const projects=await r.json();
  let html='<div style="font-size:10px;color:#64748b;margin-bottom:8px">Cambiar proyecto:</div>';
  for(const p of projects){{
    html+=`<button class="btn btn-outline btn-sm" style="width:100%;text-align:left;margin-bottom:4px;padding:6px;font-size:11px" onclick="selectProject('${{p.project_id}}')">✓ ${{p.project_id}}: ${{p.name}}</button>`;
  }}
  document.getElementById('project-list').innerHTML=html;
}}

async function selectProject(projectId){{
  // TODO: Switch to project in backend
  alert('Proyecto cambiado a: '+projectId);
  location.reload();
}}

async function createProject(){{
  const id=document.getElementById('new-proj-id').value.trim();
  const name=document.getElementById('new-proj-name').value.trim();
  const desc=document.getElementById('new-proj-desc').value.trim();
  if(!id||!name){{alert('ID y Nombre son requeridos');return;}}
  const r=await fetch('/api/projects/create',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{project_id:id,name,description:desc,git_dirs:{{}}}})}});
  const d=await r.json();
  if(d.ok){{
    alert('Proyecto '+id+' creado correctamente');
    document.getElementById('new-proj-id').value='';
    document.getElementById('new-proj-name').value='';
    document.getElementById('new-proj-desc').value='';
    loadProjectList();
    location.reload();
  }}
  else alert('Error: '+(d.error||''));
}}

async function saveGitDirs(){{
  const back=document.getElementById('git-back').value.trim();
  const bo=document.getElementById('git-bo').value.trim();
  const mob=document.getElementById('git-mob').value.trim();
  const git_dirs={{}};
  if(back) git_dirs.BACK=back;
  if(bo) git_dirs.BO=bo;
  if(mob) git_dirs.MOB=mob;
  if(!Object.keys(git_dirs).length){{alert('Al menos una ruta requerida');return;}}

  const r=await fetch('/api/projects/SEGURO/config',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{git_dirs,directives:{{}}}})}});
  const d=await r.json();
  if(d.ok){{
    alert('Directorios Git guardados');
    document.getElementById('git-back').value='';
    document.getElementById('git-bo').value='';
    document.getElementById('git-mob').value='';
  }}
  else alert('Error: '+(d.error||''));
}}

async function saveDirectives(){{
  const merge=document.getElementById('directive-merge').value;
  const prefix=document.getElementById('directive-feature-prefix').value.trim();
  const branch=document.getElementById('directive-dev-branch').value.trim();

  const directives={{}};
  if(merge) directives['merge-strategy']=merge;
  if(prefix) directives['feature-prefix']=prefix;
  if(branch) directives['dev-branch']=branch;

  const r=await fetch('/api/projects/SEGURO/config',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{git_dirs:{{}},directives}})}});
  const d=await r.json();
  if(d.ok){{
    alert('Directivas guardadas');
  }}
  else alert('Error: '+(d.error||''));
}}

function openSprintModal(){{
  document.getElementById('sprint-modal-bg').classList.add('open');
}}
function closeSprintModal(){{
  document.getElementById('sprint-modal-bg').classList.remove('open');
}}
async function createSprint(){{
  const id=document.getElementById('sprint-id').value.trim();
  const name=document.getElementById('sprint-name').value.trim();
  const stack=document.getElementById('sprint-stack').value;
  const tasksJson=document.getElementById('sprint-tasks').value.trim();
  if(!id||!name){{alert('Sprint ID y Nombre requeridos');return;}}
  let tasks=[];
  try{{
    tasks=tasksJson?JSON.parse(tasksJson):[];
  }}catch(e){{
    alert('Error en JSON de tareas: '+e.message);
    return;
  }}
  const r=await fetch('/api/sprints/create',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{sprint_id:id,name,stack,tasks}})}});
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
        if p=="/api/system/start":     self._json(start_all())
        elif p=="/api/system/stop":    self._json(stop_all())
        elif p.endswith("/start"):      self._json(start_agent(p.split("/")[3]))
        elif p.endswith("/stop"):       self._json(stop_agent(p.split("/")[3]))
        elif p.endswith("/terminal"):   self._json(open_terminal(p.split("/")[3]))
        elif p.endswith("/enabled"):    self._json(set_agent_enabled(p.split("/")[3], bool(body.get("enabled", True))))
        elif p=="/api/agents":         self._json(add_agent(body))
        elif p=="/api/team/preset":    self._json(set_active_preset(body.get("preset", "")))
        elif p=="/api/team/stack":     self._json(set_agents_enabled_for_stack(body.get("stack_key", ""), bool(body.get("enabled", True))))
        elif p=="/api/schedule":       save_schedule(body);self._json({"ok":True})
        elif p.startswith("/api/sprint/") and p.endswith("/pause"):
            sid = p.split("/")[3]
            from app_core.memory_store import MemoryStore
            msg = MemoryStore().sprint_pause(sid)
            self._json({"ok": True, "message": msg})
        elif p.startswith("/api/sprint/") and p.endswith("/resume"):
            sid = p.split("/")[3]
            from app_core.memory_store import MemoryStore
            msg = MemoryStore().sprint_resume(sid)
            self._json({"ok": True, "message": msg})
        elif p == "/api/projects":
            from app_core.memory_store import MemoryStore
            self._json(MemoryStore().project_list())
        elif p == "/api/projects/create":
            from app_core.memory_store import MemoryStore
            try:
                MemoryStore().project_create(
                    body.get("project_id", ""),
                    body.get("name", ""),
                    body.get("description", ""),
                    body.get("git_dirs", {})
                )
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
        elif p.startswith("/api/projects/") and p.endswith("/config"):
            from app_core.memory_store import MemoryStore
            project_id = p.split("/")[3]
            try:
                MemoryStore().project_update_git_dirs(project_id, body.get("git_dirs", {}))
                for key, value in body.get("directives", {}).items():
                    MemoryStore().project_set_directive(project_id, key, value)
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
        elif p == "/api/sprints/create":
            from app_core.memory_store import MemoryStore
            from app_core.sprint_manager import create_sprint_from_plan
            try:
                # Expect: {sprint_id, name, stack, tasks: [{id, summary, depends_on, parallel}]}
                plan = {
                    "sprint_id": body.get("sprint_id", ""),
                    "name": body.get("name", ""),
                    "stack": body.get("stack", "BACK"),
                    "tasks": body.get("tasks", [])
                }
                result = create_sprint_from_plan(plan, MemoryStore())
                global _board_cache_ts
                _board_cache_ts = 0
                self._json({"ok": True, "sprint_id": plan["sprint_id"], "result": result})
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
