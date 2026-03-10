from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StorageAdapter:
    name: str
    source_of_truth: str


@dataclass(frozen=True)
class MessagingAdapter:
    name: str
    channel: str


@dataclass(frozen=True)
class RepositoryAdapter:
    name: str
    provider: str


@dataclass(frozen=True)
class LLMAdapter:
    name: str
    provider: str


@dataclass(frozen=True)
class DashboardAdapter:
    name: str
    surface: str


def get_default_adapters() -> dict:
    return {
        "storage": StorageAdapter(name="local_board", source_of_truth="sqlite"),
        "messaging": MessagingAdapter(name="telegram_optional", channel="telegram"),
        "repository": RepositoryAdapter(name="gitlab_repository", provider="gitlab"),
        "llm": LLMAdapter(name="provider_catalog", provider="multi-provider"),
        "dashboard": DashboardAdapter(name="local_http_dashboard", surface="http://localhost:8888"),
    }
