#!/usr/bin/env python3
"""
Test complete sprint creation flow:
1. Create project via dashboard API
2. Create sprint via PM bot command
3. Verify tasks appear in board
4. Verify orchestrator can see them
"""
import requests
import json
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "memory" / "veloxiq_memory.db"
DASHBOARD_URL = "http://localhost:8888"

def test_project_creation():
    """Test 1: Create project via API"""
    print("[TEST 1] Creating project via Dashboard API...")
    payload = {
        "project_id": "SEGURO",
        "name": "SEGURO Platform",
        "description": "Main project",
        "git_dirs": {
            "BACK": "C:\\repos\\backend",
            "BO": "C:\\repos\\backoffice",
            "MOB": "C:\\repos\\mobile"
        }
    }
    try:
        r = requests.post(f"{DASHBOARD_URL}/api/projects/create", json=payload, timeout=30)
        result = r.json()
        if result.get("ok"):
            print("  [OK] Project SEGURO created")
            return True
        else:
            print(f"  [FAIL] {result.get('error')}")
            return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False

def test_sprint_creation_via_api():
    """Test 2: Create sprint directly via API (simulating PM bot)"""
    print("\n[TEST 2] Creating sprint via Dashboard API...")
    payload = {
        "sprint_id": "sprint_01",
        "name": "Initial Sprint",
        "stack": "BACK",
        "tasks": [
            {
                "id": "VEL-1",
                "summary": "Login endpoint",
                "depends_on": [],
                "parallel": True
            },
            {
                "id": "VEL-2",
                "summary": "JWT validation",
                "depends_on": ["VEL-1"],
                "parallel": False
            },
            {
                "id": "VEL-3",
                "summary": "Logout endpoint",
                "depends_on": [],
                "parallel": True
            }
        ]
    }
    try:
        r = requests.post(f"{DASHBOARD_URL}/api/sprints/create", json=payload, timeout=30)
        result = r.json()
        if result.get("ok"):
            print(f"  [OK] Sprint sprint_01 created with {result['result']['tasks_created']} tasks")
            return True
        else:
            print(f"  [FAIL] {result.get('error')}")
            return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False

def test_board_data():
    """Test 3: Verify tasks appear in board"""
    print("\n[TEST 3] Verifying tasks in board...")
    try:
        con = sqlite3.connect(str(DB))
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT task_id, summary, state, sprint_id FROM local_board ORDER BY task_id").fetchall()
        con.close()

        if not rows:
            print("  [FAIL] No tasks found in board")
            return False

        print(f"  [OK] Found {len(rows)} tasks:")
        for row in rows:
            print(f"       {row['task_id']:6} | {row['summary'][:30]:30} | {row['state']:10} | {row['sprint_id']}")

        # Check if expected tasks exist
        task_ids = {row['task_id'] for row in rows}
        expected = {"VEL-1", "VEL-2", "VEL-3"}
        if expected.issubset(task_ids):
            print(f"  [OK] All expected tasks present")
            return True
        else:
            missing = expected - task_ids
            print(f"  [FAIL] Missing tasks: {missing}")
            return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False

def test_sprint_data():
    """Test 4: Verify sprint exists"""
    print("\n[TEST 4] Verifying sprint in database...")
    try:
        con = sqlite3.connect(str(DB))
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT sprint_id, name, stack, status FROM sprints WHERE sprint_id='sprint_01'").fetchone()
        con.close()

        if not row:
            print("  [FAIL] Sprint not found")
            return False

        print(f"  [OK] Sprint found:")
        print(f"       ID: {row['sprint_id']}, Name: {row['name']}, Stack: {row['stack']}, Status: {row['status']}")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False

def test_orchestrator_readiness():
    """Test 5: Verify orchestrator can see tasks"""
    print("\n[TEST 5] Checking orchestrator readiness...")
    try:
        con = sqlite3.connect(str(DB))
        con.row_factory = sqlite3.Row

        # Get Todo tasks (what orchestrator would assign)
        todo_tasks = con.execute(
            "SELECT task_id, summary, depends_on FROM local_board WHERE state='Todo' ORDER BY task_id"
        ).fetchall()
        con.close()

        if not todo_tasks:
            print("  [FAIL] No Todo tasks found (orchestrator has nothing to do)")
            return False

        print(f"  [OK] Found {len(todo_tasks)} Todo tasks ready for orchestrator:")
        for task in todo_tasks:
            depends = json.loads(task['depends_on'] or '[]')
            print(f"       {task['task_id']:6} | {task['summary'][:25]:25} | deps: {len(depends)}")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False

def main():
    print("=" * 70)
    print("VeloxIq Sprint Creation Flow Test")
    print("=" * 70)

    results = []
    results.append(("Project Creation", test_project_creation()))
    results.append(("Sprint Creation", test_sprint_creation_via_api()))
    results.append(("Board Data", test_board_data()))
    results.append(("Sprint Data", test_sprint_data()))
    results.append(("Orchestrator Readiness", test_orchestrator_readiness()))

    print("\n" + "=" * 70)
    print("Test Results:")
    print("=" * 70)
    for name, passed in results:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}")

    all_passed = all(r[1] for r in results)
    print("\n" + ("All tests passed! System ready." if all_passed else "Some tests failed. Check output above."))
    return 0 if all_passed else 1

if __name__ == "__main__":
    exit(main())
