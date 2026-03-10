from app_core.assignment_policy import LocalBoardDefaultAssignmentPolicy


class FakeMemoryStore:
    def __init__(self, tasks, fix_links=None, sprints=None):
        self.tasks = {task["task_id"]: dict(task) for task in tasks}
        self.fix_links = list(fix_links or [])
        self.sprints = list(sprints or [])
        self.comments = []

    def sprint_list(self):
        return list(self.sprints)

    def sprint_get_active(self):
        for sprint in self.sprints:
            if sprint.get("status") == "active":
                return sprint
        return None

    def board_get_busy_assignees(self, state):
        return [task["assignee"] for task in self.tasks.values() if task.get("state") == state and task.get("assignee")]

    def board_get_tasks_by_state(self, state, sprint_id=""):
        tasks = [dict(task) for task in self.tasks.values() if task.get("state") == state]
        if sprint_id:
            tasks = [task for task in tasks if task.get("sprint_id") == sprint_id]
        return sorted(tasks, key=lambda task: task["task_id"])

    def board_get_task(self, task_id):
        task = self.tasks.get(task_id)
        return dict(task) if task else None

    def get_fix_tasks_by_priority(self):
        return list(self.fix_links)

    def get_fix_tasks_for_task(self, fixing_task_id):
        return [link for link in self.fix_links if link["fixing_task_id"] == fixing_task_id]

    def delete_fix_task_link(self, fix_task_id):
        self.fix_links = [link for link in self.fix_links if link["fix_task_id"] != fix_task_id]

    def board_add_comment(self, task_id, author, text):
        self.comments.append((task_id, author, text))


class FakeStateManager:
    def __init__(self, store):
        self.store = store
        self.transitions = []

    def check_concurrent_assignment(self, task_id, agent_id):
        return False, ""

    def transition(self, task_id, target_state, agent_id, reason="", max_retries=1):
        self.transitions.append((task_id, target_state, agent_id, reason))
        task = self.store.tasks[task_id]
        if target_state.startswith("InProgress assignee "):
            task["state"] = "InProgress"
            task["assignee"] = target_state.split("InProgress assignee ", 1)[1]
        else:
            task["state"] = target_state
        return {"ok": True}


def test_assignment_policy_prioritizes_fixes_and_respects_stack(monkeypatch):
    tasks = [
        {"task_id": "FIX-1", "state": "Todo", "assignee": "", "priority": "Critical", "stack": "BACK", "parallel": True, "depends_on": [], "sprint_id": "S1"},
        {"task_id": "VEL-1", "state": "Todo", "assignee": "", "priority": "High", "stack": "BO", "parallel": True, "depends_on": [], "sprint_id": "S1"},
        {"task_id": "VEL-2", "state": "Todo", "assignee": "", "priority": "Medium", "stack": "BACK", "parallel": False, "depends_on": [], "sprint_id": "S1"},
        {"task_id": "VEL-3", "state": "Todo", "assignee": "", "priority": "Medium", "stack": "BACK", "parallel": True, "depends_on": ["VEL-9"], "sprint_id": "S1"},
        {"task_id": "SEQ-0", "state": "InProgress", "assignee": "busy-back", "priority": "Medium", "stack": "BACK", "parallel": False, "depends_on": [], "sprint_id": "S1"},
    ]
    fix_links = [{"fix_task_id": "FIX-1", "fixing_task_id": "VEL-0", "priority": "Critical", "original_state": "QA"}]
    sprints = [{"sprint_id": "S1", "status": "active"}]
    store = FakeMemoryStore(tasks, fix_links=fix_links, sprints=sprints)
    state = FakeStateManager(store)
    policy = LocalBoardDefaultAssignmentPolicy(store, state, lambda *args: None)

    def fake_list_eligible_agents(*, role=None, stack_key=None, preset_name=None):
        agents = [
            {"id": "dev-back", "role": "developer", "stack_key": "BACK", "login": "back-dev", "enabled": True},
            {"id": "dev-bo", "role": "developer", "stack_key": "BO", "login": "bo-dev", "enabled": True},
        ]
        result = [agent for agent in agents if role in (None, agent["role"])]
        if stack_key:
            result = [agent for agent in result if agent["stack_key"] == stack_key]
        return result

    monkeypatch.setattr("app_core.assignment_policy.list_eligible_agents", fake_list_eligible_agents)

    stats = policy.assign_pending_tasks()

    assert stats["assigned"] == 2
    assert store.tasks["FIX-1"]["assignee"] == "back-dev"
    assert store.tasks["VEL-1"]["assignee"] == "bo-dev"
    assert store.tasks["VEL-2"]["state"] == "Todo"
    assert store.tasks["VEL-3"]["state"] == "Todo"


def test_assignment_policy_handles_fixing_queue(monkeypatch):
    tasks = [
        {"task_id": "VEL-10", "state": "Fixing", "assignee": "", "priority": "Medium", "stack": "BACK", "parallel": True, "depends_on": [], "sprint_id": "S1"},
        {"task_id": "FIX-VEL-10-1", "state": "Todo", "assignee": "", "priority": "Medium", "stack": "MOB", "parallel": True, "depends_on": [], "sprint_id": "S1"},
    ]
    fix_links = [{"fix_task_id": "FIX-VEL-10-1", "fixing_task_id": "VEL-10", "priority": "Medium", "original_state": "QA"}]
    store = FakeMemoryStore(tasks, fix_links=fix_links)
    state = FakeStateManager(store)
    events = []
    policy = LocalBoardDefaultAssignmentPolicy(store, state, lambda *args: events.append(args))

    def fake_list_eligible_agents(*, role=None, stack_key=None, preset_name=None):
        agents = [
            {"id": "qa-mob", "role": "qa", "stack_key": "MOB", "login": "qa-mob", "enabled": True},
            {"id": "dev-mob", "role": "developer", "stack_key": "MOB", "login": "mob-dev", "enabled": True},
        ]
        result = [agent for agent in agents if role in (None, agent["role"])]
        if stack_key:
            result = [agent for agent in result if agent["stack_key"] == stack_key]
        return result

    monkeypatch.setattr("app_core.assignment_policy.list_eligible_agents", fake_list_eligible_agents)

    stats = policy.assign_fixing_tasks()

    assert stats["assigned"] == 1
    assert store.tasks["FIX-VEL-10-1"]["assignee"] == "mob-dev"
