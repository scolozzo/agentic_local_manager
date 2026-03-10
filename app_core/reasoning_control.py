from __future__ import annotations


def classify_dev_task(task_summary: str) -> str:
    return "development"


def classify_qa_task(is_full_review: bool = True) -> str:
    return "qa_review" if is_full_review else "qa_check"


def get_llm_params(task_type: str, model: str) -> dict:
    return {"model": model}
