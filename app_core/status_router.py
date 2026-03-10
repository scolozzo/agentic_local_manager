from __future__ import annotations


class LocalBoardStatusClient:
    def get_sprint_summary(self) -> str:
        return "No sprint data available."

    def get_sprint_status(self) -> str:
        return "No active tasks."

    def get_blocked_tasks(self) -> str:
        return "No blocked tasks."


def handle_pm_query(text: str, client: LocalBoardStatusClient, token_logger) -> str | None:
    normalized = text.strip().lower()
    if normalized in {"status", "/status", "estado"}:
        return "\n\n".join([
            client.get_sprint_summary(),
            client.get_sprint_status(),
            client.get_blocked_tasks(),
        ])
    return None
