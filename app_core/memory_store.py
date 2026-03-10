from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app_core.agent_config import REPO_ROOT


class MemoryStore:
    def __init__(self) -> None:
        self.db_path = REPO_ROOT / "memory" / "veloxiq_memory.db"
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_db()

    def _connect(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self) -> None:
        con = self._connect()
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS local_board (
                task_id TEXT PRIMARY KEY,
                summary TEXT,
                description TEXT,
                state TEXT,
                assignee TEXT,
                priority TEXT,
                stack TEXT,
                sprint_id TEXT,
                acceptance_criteria TEXT,
                depends_on TEXT,
                parallel INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS board_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                author TEXT,
                text TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS sprints (
                sprint_id TEXT PRIMARY KEY,
                name TEXT,
                stack TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                ended_at TEXT
            );
            CREATE TABLE IF NOT EXISTS fix_task_links (
                fix_task_id TEXT PRIMARY KEY,
                fixing_task_id TEXT,
                priority TEXT,
                original_state TEXT
            );
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                template_id TEXT DEFAULT 'software_delivery_default',
                git_dirs TEXT,
                directives TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS qa_results (
                task_id TEXT PRIMARY KEY,
                issues TEXT,
                passed INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS certified_endpoints (
                method TEXT,
                path TEXT,
                sprint_id TEXT,
                stack TEXT,
                certified_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        try:
            con.execute("ALTER TABLE projects ADD COLUMN template_id TEXT DEFAULT 'software_delivery_default'")
            con.commit()
        except sqlite3.OperationalError:
            pass
        try:
            con.execute("ALTER TABLE sprints ADD COLUMN project_id TEXT DEFAULT 'SEGURO'")
            con.commit()
        except sqlite3.OperationalError:
            pass
        con.close()

    def board_create_task(self, task_id: str, summary: str, description: str = "", state: str = "Todo",
                          priority: str = "Medium", stack: str = "BACK", sprint_id: str = "",
                          acceptance_criteria=None, depends_on=None, parallel: bool = True) -> None:
        con = self._connect()
        con.execute(
            """
            INSERT OR REPLACE INTO local_board
            (task_id, summary, description, state, assignee, priority, stack, sprint_id, acceptance_criteria, depends_on, parallel, updated_at)
            VALUES (?, ?, ?, ?, COALESCE((SELECT assignee FROM local_board WHERE task_id = ?), ''), ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                task_id, summary, description, state, task_id, priority, stack, sprint_id,
                json.dumps(acceptance_criteria or []), json.dumps(depends_on or []), 1 if parallel else 0,
            ),
        )
        con.commit()
        con.close()

    def board_get_task(self, task_id: str):
        con = self._connect()
        row = con.execute("SELECT * FROM local_board WHERE task_id = ?", (task_id,)).fetchone()
        con.close()
        return self._row_to_task(row) if row else None

    def _row_to_task(self, row) -> dict:
        task = dict(row)
        task["acceptance_criteria"] = json.loads(task.get("acceptance_criteria") or "[]")
        task["depends_on"] = json.loads(task.get("depends_on") or "[]")
        task["parallel"] = bool(task.get("parallel", 1))
        return task

    def board_get_tasks_by_state(self, state: str, sprint_id: str = "") -> list[dict]:
        con = self._connect()
        if sprint_id:
            rows = con.execute(
                "SELECT * FROM local_board WHERE state = ? AND sprint_id = ? ORDER BY created_at ASC",
                (state, sprint_id),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM local_board WHERE state = ? ORDER BY created_at ASC",
                (state,),
            ).fetchall()
        con.close()
        return [self._row_to_task(row) for row in rows]

    def board_get_tasks_by_assignee(self, assignee: str, states=None) -> list[dict]:
        states = states or []
        con = self._connect()
        if states:
            placeholders = ",".join("?" for _ in states)
            rows = con.execute(
                f"SELECT * FROM local_board WHERE assignee = ? AND state IN ({placeholders}) ORDER BY created_at ASC",
                [assignee, *states],
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM local_board WHERE assignee = ?", (assignee,)).fetchall()
        con.close()
        return [self._row_to_task(row) for row in rows]

    def board_get_busy_assignees(self, state: str) -> list[str]:
        con = self._connect()
        rows = con.execute(
            "SELECT DISTINCT assignee FROM local_board WHERE state = ? AND assignee != ''",
            (state,),
        ).fetchall()
        con.close()
        return [row["assignee"] for row in rows]

    def board_update_state(self, task_id: str, state: str) -> None:
        con = self._connect()
        con.execute("UPDATE local_board SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE task_id = ?", (state, task_id))
        con.commit()
        con.close()

    def board_assign_and_set_state(self, task_id: str, assignee: str, state: str) -> None:
        con = self._connect()
        con.execute(
            "UPDATE local_board SET assignee = ?, state = ?, updated_at = CURRENT_TIMESTAMP WHERE task_id = ?",
            (assignee, state, task_id),
        )
        con.commit()
        con.close()

    def board_add_comment(self, task_id: str, author: str, text: str) -> None:
        con = self._connect()
        con.execute("INSERT INTO board_comments (task_id, author, text) VALUES (?, ?, ?)", (task_id, author, text))
        con.commit()
        con.close()

    def board_get_comments(self, task_id: str) -> list[dict]:
        con = self._connect()
        rows = con.execute(
            "SELECT task_id, author, text, created_at FROM board_comments WHERE task_id = ? ORDER BY created_at ASC, id ASC",
            (task_id,),
        ).fetchall()
        con.close()
        return [dict(row) for row in rows]

    def save_fix_task_link(self, fix_task_id: str, fixing_task_id: str, priority: str, original_state: str) -> None:
        con = self._connect()
        con.execute(
            "INSERT OR REPLACE INTO fix_task_links (fix_task_id, fixing_task_id, priority, original_state) VALUES (?, ?, ?, ?)",
            (fix_task_id, fixing_task_id, priority, original_state),
        )
        con.commit()
        con.close()

    def get_fix_tasks_for_task(self, fixing_task_id: str) -> list[dict]:
        con = self._connect()
        rows = con.execute("SELECT * FROM fix_task_links WHERE fixing_task_id = ?", (fixing_task_id,)).fetchall()
        con.close()
        return [dict(row) for row in rows]

    def get_fix_tasks_by_priority(self) -> list[dict]:
        con = self._connect()
        rows = con.execute("SELECT * FROM fix_task_links ORDER BY rowid ASC").fetchall()
        con.close()
        return [dict(row) for row in rows]

    def delete_fix_task_link(self, fix_task_id: str) -> None:
        con = self._connect()
        con.execute("DELETE FROM fix_task_links WHERE fix_task_id = ?", (fix_task_id,))
        con.commit()
        con.close()

    def save_qa_result(self, task_id: str, issues: list, passed: bool) -> None:
        con = self._connect()
        con.execute(
            "INSERT OR REPLACE INTO qa_results (task_id, issues, passed) VALUES (?, ?, ?)",
            (task_id, json.dumps(issues), 1 if passed else 0),
        )
        con.commit()
        con.close()

    def sprint_list(self) -> list[dict]:
        con = self._connect()
        rows = con.execute("SELECT * FROM sprints ORDER BY created_at DESC").fetchall()
        con.close()
        return [dict(row) for row in rows]

    def sprint_get_active(self):
        con = self._connect()
        row = con.execute("SELECT * FROM sprints WHERE status = 'active' ORDER BY created_at DESC LIMIT 1").fetchone()
        con.close()
        return dict(row) if row else None

    def sprint_set_project(self, sprint_id: str, project_id: str) -> None:
        con = self._connect()
        con.execute("UPDATE sprints SET project_id = ? WHERE sprint_id = ?", (project_id, sprint_id))
        con.commit()
        con.close()

    def sprint_pause(self, sprint_id: str) -> str:
        con = self._connect()
        con.execute("UPDATE sprints SET status = 'paused' WHERE sprint_id = ?", (sprint_id,))
        con.commit()
        con.close()
        return f"Sprint {sprint_id} pausado"

    def sprint_resume(self, sprint_id: str) -> str:
        con = self._connect()
        con.execute("UPDATE sprints SET status = 'active' WHERE sprint_id = ?", (sprint_id,))
        con.commit()
        con.close()
        return f"Sprint {sprint_id} reanudado"

    def project_list(self) -> list[dict]:
        con = self._connect()
        rows = con.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        con.close()
        projects = []
        for row in rows:
            item = dict(row)
            item["git_dirs"] = json.loads(item.get("git_dirs") or "{}")
            item["directives"] = json.loads(item.get("directives") or "{}")
            item.setdefault("template_id", "software_delivery_default")
            projects.append(item)
        return projects

    def project_create(self, project_id: str, name: str, description: str, git_dirs: dict, template_id: str = "software_delivery_default") -> None:
        con = self._connect()
        con.execute(
            "INSERT OR REPLACE INTO projects (project_id, name, description, template_id, git_dirs, updated_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (project_id, name, description, template_id, json.dumps(git_dirs)),
        )
        con.commit()
        con.close()

    def project_update_git_dirs(self, project_id: str, git_dirs: dict) -> None:
        con = self._connect()
        row = con.execute("SELECT directives FROM projects WHERE project_id = ?", (project_id,)).fetchone()
        directives = row["directives"] if row else "{}"
        con.execute(
            "INSERT OR REPLACE INTO projects (project_id, name, description, template_id, git_dirs, directives, updated_at) VALUES (?, COALESCE((SELECT name FROM projects WHERE project_id = ?), ?), COALESCE((SELECT description FROM projects WHERE project_id = ?), ''), COALESCE((SELECT template_id FROM projects WHERE project_id = ?), 'software_delivery_default'), ?, ?, CURRENT_TIMESTAMP)",
            (project_id, project_id, project_id, project_id, project_id, json.dumps(git_dirs), directives),
        )
        con.commit()
        con.close()

    def project_set_directive(self, project_id: str, key: str, value: str) -> None:
        con = self._connect()
        row = con.execute("SELECT directives FROM projects WHERE project_id = ?", (project_id,)).fetchone()
        directives = json.loads(row["directives"] if row and row["directives"] else "{}")
        directives[key] = value
        con.execute("UPDATE projects SET directives = ?, updated_at = CURRENT_TIMESTAMP WHERE project_id = ?", (json.dumps(directives), project_id))
        con.commit()
        con.close()

    def project_set_template(self, project_id: str, template_id: str) -> None:
        con = self._connect()
        con.execute(
            "UPDATE projects SET template_id = ?, updated_at = CURRENT_TIMESTAMP WHERE project_id = ?",
            (template_id, project_id),
        )
        con.commit()
        con.close()

    def purge_task_transitions(self, task_id: str) -> None:
        return None

    def mark_task_not_found(self, task_id: str, agent_id: str) -> None:
        return None
