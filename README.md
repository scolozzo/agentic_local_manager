# Multi-Agent Local Project Manager

Distributed agent orchestration system for intelligent task management across multiple technology stacks, with local SQLite storage, Telegram bot integration, and version control synchronization.

## 🎯 Project Overview

A flexible multi-agent platform that coordinates AI agents (PM, Developers, QA, Orchestrator) to manage software development workflows across multiple project stacks (Backend, Frontend, Mobile):

- **PM Agent**: Project coordinator that receives Telegram commands and creates work sprints
- **Dev Agents**: Execute development tasks with automatic retry logic and deadlock detection
- **QA Agent**: Reviews completed work, creates fix tasks, validates deliverables
- **Orchestrator**: Manages task lifecycle, assigns work, detects blockers
- **Local Board**: SQLite-based task tracking and project management
- **Dashboard**: Web UI for project monitoring, configuration, and sprint management

## 📦 Architecture

```
User Input (Telegram / Web UI)
    ↓ /sprint command or dashboard
PM Agent
    ↓ Parse requirements + create task list
Dashboard API (localhost:8888)
    ↓ Sprint creation with dependencies
Local Board (SQLite)
    ↓ Orchestrator detects Todo tasks
Orchestrator Agent
    ↓ Task assignment with deadlock detection
Dev/QA Agents
    ↓ Execute work + report status
Version Control (Git)
    ↓ Feature branches → Integration → Release
```

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install python-dotenv requests anthropic
```

### 2. Configure Environment
```bash
# Create .env file with your LLM and integration credentials
# Required keys:
# - LLM_API_KEY: Your AI provider API key
# - LLM_API_BASE: (optional) Custom API endpoint
# - TELEGRAM_BOT_TOKEN: Bot token for Telegram integration
# - TELEGRAM_CHAT_ID: Your Telegram chat ID
# - GIT_TOKEN: Version control access token
```

### 3. Initialize Database
```bash
python db_reset.py
# Creates local SQLite database with projects, sprints, and tasks tables
```

### 4. Start Dashboard
```bash
python dashboard.py
# Opens http://localhost:8888
```

### 5. Start Agents
```bash
# Launch all agents
python agent_manager.py

# Or start individually:
python pm_integration.py &
python orchestrator_integration.py &
python developer_integration.py &
python qa_integration.py &
```

## 📋 Configuration

### Projects & Stack Management
Via Dashboard Configuration Tab:
- Create new projects for different initiatives
- Configure repository directories per technology stack
- Set project directives (branching strategy, naming conventions, integration branch)

### Create a Sprint
Via Dashboard Sprint Creator:
```json
{
  "sprint_id": "sprint_01",
  "name": "Feature: User Authentication",
  "stack": "backend",
  "tasks": [
    {
      "id": "TASK-1",
      "summary": "Implement login endpoint",
      "depends_on": [],
      "parallel": true
    },
    {
      "id": "TASK-2",
      "summary": "Add JWT token validation",
      "depends_on": ["TASK-1"],
      "parallel": false
    }
  ]
}
```

Or via Telegram Bot:
```
/sprint sprint_01 "Feature: User Authentication"
- TASK-1: Implement login endpoint
- TASK-2: Add JWT token validation (depends TASK-1)
```

## 🧠 Core Modules

### Foundation (Local State Management)
- **memory_store.py** - SQLite-backed data store for tasks, sprints, and state history
- **state_manager.py** - Centralized task state transitions with automatic retries and deadlock detection
- **sprint_manager.py** - Sprint planning and parsing (JSON/Markdown formats)
- **status_router.py** - Query system for task status without LLM overhead
- **project_manager.py** - Multi-project lifecycle and configuration management
- **dependency_graph.py** - Task dependency validation and resolution

### Agent Coordination
- **agent_manager.py** - Agent lifecycle management (start, stop, configuration)
- **orchestrator_integration.py** - Central task coordinator with blocker detection
- **pm_integration.py** - Project manager with Telegram integration
- **developer_integration.py** - Developer task execution with version control integration
- **qa_integration.py** - Quality assurance with approval/rejection workflow

### Infrastructure
- **dashboard.py** - Web UI for monitoring and configuration (port 8888)
- **git_tools.py** - Version control integration (branching, merging, synchronization)
- **token_logger.py** - LLM usage tracking and cost analysis
- **config_loader.py** - Stack-aware configuration management
- **reasoning_control.py** - LLM reasoning mode control per task type

### Agent System Prompts
- **agent_manuals/pm_prompt.md** - Project manager responsibilities and authority
- **agent_manuals/developer_prompt.md** - Developer workflow and standards
- **agent_manuals/qa_prompt.md** - QA review criteria and approval process
- **agent_manuals/orchestrator_prompt.md** - Task coordination and blocker handling
- **config/prompts/** - Stack-specific specializations (backend, frontend, mobile, database)

## 📊 Database Schema

### Main Tables
```sql
-- Projects
projects(project_id, name, description, git_dirs, directives, created_at, updated_at)

-- Tasks (local board)
local_board(task_id, summary, description, state, assignee, priority, stack,
            sprint_id, acceptance_criteria, depends_on, parallel, created_at, updated_at)

-- Sprints
sprints(sprint_id, name, stack, status, created_at, started_at, ended_at)

-- Audit Trail
state_transitions(id, task_id, from_state, to_state, agent_id, attempt_num,
                 max_attempts, status, error_msg, reason, timestamp, duration_ms)

-- Comments
board_comments(id, task_id, author, text, created_at)

-- QA Results
qa_results(task_id, issues, passed, created_at)

-- Certified Endpoints
certified_endpoints(method, path, sprint_id, stack, certified_at)
```

## 🔄 Task Lifecycle

```
Todo
  ↓ Orchestrator.assign_pending_tasks()
InProgress (Dev assigned)
  ↓ Developer works + creates feature branch
  ↓ Developer pushes commits
QA (Ready for review)
  ↓ QA Agent reviews
  ├→ APPROVED: ReadyToMerge
  │   ↓ Orchestrator merges to develop/main
  │   ↓ Merged
  └→ REJECTED: Fixing
      ↓ QA creates FIX-* subtasks
      ↓ Dev fixes in subtask branch
      ↓ Back to QA review
```

## 🎮 StateManager

Centralized state transition handler with:
- **Automatic retries**: 3 attempts + exponential backoff (5s → 10s → 20s)
- **Deadlock detection**: Flags tasks stuck >5 minutes on same state
- **Race condition prevention**: Detects concurrent assignments
- **Audit trail**: All attempts logged to state_transitions table
- **Cross-agent notifications**: Internal events posted to board comments

```python
result = state_mgr.transition(
    task_id="TASK-123",
    target_state="InProgress assignee dev1",
    agent_id="orchestrator",
    reason="Auto-assign to available developer",
    max_retries=3
)
# Returns: {"ok": True, "attempts": 1, "error": None, "final_state": "InProgress"}
```

## 📡 User Integration (Telegram / Web)

PM Agent responds to user input via:
- **Status Query** - Current sprint and task status
- **Sprint Creation** - Create new sprint with task list and dependencies
- **Blocker Report** - List blocked tasks and their impediments
- **Team Status** - Next available work and team capacity
- **Sprint Control** - Pause/resume sprints as needed
- **Task Unblocking** - Manual intervention for stuck tasks

## 🔗 Version Control Integration

### Feature Branch Workflow
1. Developer receives task assignment
2. Create feature branch: `feature/TASK-XXX-description`
3. Developer pushes commits with conventional messages
4. QA reviews changes
5. On approval: Merge to integration branch (develop/staging)
6. For release: Merge integration branch to main with controlled strategy

### Multi-Stack Repository Configuration
Each technology stack has its own repository with configuration:
```json
{
  "backend": {
    "repository_url": "https://github.com/org/backend.git",
    "integration_branch": "develop",
    "release_branch": "main"
  },
  "frontend": {
    "repository_url": "https://github.com/org/frontend.git",
    "integration_branch": "develop",
    "release_branch": "main"
  },
  "mobile": {
    "repository_url": "https://github.com/org/mobile.git",
    "integration_branch": "develop",
    "release_branch": "main"
  }
}
```

## 💰 LLM Usage Tracking

Monitor AI model usage and costs by agent:

```python
from token_logger import TokenLogger

logger = TokenLogger()
logger.log_llm_call(
    agent_name="developer1",
    model="your-model-name",
    input_tokens=500,
    output_tokens=200,
    cost_usd=0.01
)

# Dashboard displays:
# Today: Total cost, number of calls, tokens used
# Monthly: Cumulative cost and usage patterns
```

## 🧪 Testing

Run test suite:
```bash
cd tests/
pytest test_memory_store.py -v
pytest test_state_manager.py -v
pytest test_sprint_manager.py -v
pytest test_status_router.py -v

# All: 109 tests (currently all passing)
```

## 📝 Agent Context Optimization

### Context Compiler
Minimal context for each agent based on:
- Current task details
- Relevant dependencies
- QA feedback (if any)
- Certified endpoints
- API contracts
- Stack-specific skills

Reduces token waste by ~70% vs full board history.

### Reasoning Control
```python
# Enable thinking for complex tasks
reasoning_control.set_thinking_enabled("dev1", "feature", enable=True)

# Disable for simple tasks
reasoning_control.set_thinking_enabled("qa", "acceptance-check", enable=False)
```

## 🏗️ Multi-Stack Project Management

Configure agents for different technology stacks:

Each stack can have specialized development and QA agents:
- **Backend**: Server-side logic, databases, APIs
- **Frontend**: User interface, web applications, responsive design
- **Mobile**: Native applications, platform-specific features
- **Infrastructure**: DevOps, deployment, monitoring

Agents learn stack-specific best practices through system prompts and configuration.

## 📈 Performance Metrics

- **Token efficiency**: 70% reduction via context compiler
- **State transitions**: <100ms (local SQLite)
- **Sprint creation**: <5 seconds (with API timeout fix)
- **Deadlock detection**: Runs every 30s, <200ms query
- **Dashboard**: ~2KB per request (optimized HTML)

## 🔐 Security & Privacy

- External integrations are minimal:
  - LLM API provider for agent reasoning
  - Messaging service for user notifications
  - Version control system for code management
- All task data stored locally (SQLite) - no cloud dependency
- Sensitive files protected (.env, *.key, *.pem ignored by git)
- API endpoints are local by default (http://localhost:8888)
- Add authentication/authorization if exposing to network

## 📚 Documentation

- `IMPLEMENTATION_STATUS.md` - Current project phase
- `PHASE2_STATUS.md` - PM Bot integration status
- `CONFIG_UI_IMPROVEMENTS.md` - Dashboard UI fixes
- `agent_manuals/` - Per-agent system prompts
- `VeloxIq/` - Module docstrings

## 🤝 Contributing

1. Create feature branch: `git checkout -b feature/TASK-description`
2. Make changes (follow existing code style and patterns)
3. Run tests: `pytest tests/ -v`
4. Commit with clear message: `feat(agent): description` or `fix(core): description`
5. Push to feature branch
6. Submit pull request with description of changes

## 📄 License

This project is provided as-is for local project management use.

## 🚀 Implementation Status

**Phase 1** ✅ Multi-agent foundation (orchestration, task management, state handling)
**Phase 2** ✅ User interface (dashboard, web API, notification integration)
**Phase 3** ✅ Workflow optimization (context compilation, deadlock detection, retry logic)
**Phase 4** 🔄 Production hardening (authentication, monitoring, multi-tenancy)

---

**Last Updated**: 2026-03-10
**Architecture**: Local SQLite, AI-agent orchestration, git-integrated workflow
**Default Setup**: 1 Orchestrator + 3 Developers + 1 QA Manager + 1 Project Manager (all AI agents)
