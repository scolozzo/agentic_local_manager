from __future__ import annotations

from pathlib import Path
import re

from app_core.agent_config import REPO_ROOT


_DOCS_ROOT = Path(REPO_ROOT) / "config" / "substack_skill_docs"


def _normalize_stack_key(stack_key: str) -> str:
    value = (stack_key or "").strip().upper()
    if not value:
        raise ValueError("stack_key is required")
    return value


def _normalize_substack(substack: str) -> str:
    value = (substack or "").strip().lower()
    if not value:
        raise ValueError("substack is required")
    return value


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower())
    text = re.sub(r"-{2,}", "-", text).strip("-")
    if not text:
        raise ValueError("A valid document title is required")
    return text


def _folder_for(stack_key: str, substack: str) -> Path:
    normalized_stack = _normalize_stack_key(stack_key)
    normalized_substack = _normalize_substack(substack)
    return _DOCS_ROOT / normalized_stack / normalized_substack


def _path_for(stack_key: str, substack: str, doc_id: str) -> Path:
    slug = _slugify(doc_id)
    return _folder_for(stack_key, substack) / f"{slug}.md"


def _infer_title(path: Path, content: str) -> str:
    for line in content.splitlines():
        if line.strip().startswith("#"):
            return line.lstrip("#").strip() or path.stem.replace("-", " ").title()
    return path.stem.replace("-", " ").title()


def list_skill_docs(stack_key: str, substack: str) -> list[dict]:
    folder = _folder_for(stack_key, substack)
    if not folder.exists():
        return []
    docs = []
    for path in sorted(folder.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        docs.append(
            {
                "id": path.stem,
                "title": _infer_title(path, content),
                "content": content,
                "path": str(path),
            }
        )
    return docs


def get_skill_doc(stack_key: str, substack: str, doc_id: str) -> dict:
    path = _path_for(stack_key, substack, doc_id)
    if not path.exists():
        raise FileNotFoundError(f"Skill doc not found: {doc_id}")
    content = path.read_text(encoding="utf-8")
    return {
        "id": path.stem,
        "title": _infer_title(path, content),
        "content": content,
        "path": str(path),
    }


def save_skill_doc(stack_key: str, substack: str, title: str, content: str, doc_id: str = "") -> dict:
    normalized_title = (title or "").strip()
    if not normalized_title:
        raise ValueError("title is required")
    normalized_content = (content or "").replace("\r\n", "\n").strip()
    if not normalized_content:
        raise ValueError("content is required")
    target_id = _slugify(normalized_title)
    folder = _folder_for(stack_key, substack)
    folder.mkdir(parents=True, exist_ok=True)
    target_path = folder / f"{target_id}.md"
    source_path = _path_for(stack_key, substack, doc_id) if doc_id else None
    if source_path and source_path.exists() and source_path != target_path:
        source_path.unlink()
    target_path.write_text(normalized_content + "\n", encoding="utf-8")
    return get_skill_doc(stack_key, substack, target_id)
