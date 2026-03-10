from __future__ import annotations


def sync_feature_with_develop(feature_branch: str, project_id: str, gitlab_url: str, token: str,
                              telegram_bot_token: str, telegram_chat_id: str, target_branch: str) -> dict:
    return {"status": "synced", "feature_branch": feature_branch, "target_branch": target_branch}
