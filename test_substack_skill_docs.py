from pathlib import Path

import app_core.substack_skill_docs as skill_docs


def test_save_skill_doc_creates_markdown_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(skill_docs, "_DOCS_ROOT", tmp_path / "skill_docs")

    result = skill_docs.save_skill_doc(
        "BO",
        "backoffice",
        "Query Patterns",
        "# Query Patterns\n\nUse server pagination.",
    )

    assert result["id"] == "query-patterns"
    assert result["title"] == "Query Patterns"
    assert (tmp_path / "skill_docs" / "BO" / "backoffice" / "query-patterns.md").exists()


def test_save_skill_doc_renames_existing_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(skill_docs, "_DOCS_ROOT", tmp_path / "skill_docs")
    skill_docs.save_skill_doc("BACK", "api", "Old Name", "# Old Name\n\nOld.")

    result = skill_docs.save_skill_doc(
        "BACK",
        "api",
        "New Name",
        "# New Name\n\nUpdated.",
        doc_id="old-name",
    )

    assert result["id"] == "new-name"
    assert not (tmp_path / "skill_docs" / "BACK" / "api" / "old-name.md").exists()
    assert (tmp_path / "skill_docs" / "BACK" / "api" / "new-name.md").exists()


def test_list_skill_docs_returns_saved_content(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(skill_docs, "_DOCS_ROOT", tmp_path / "skill_docs")
    skill_docs.save_skill_doc("MOB", "android", "Ui Notes", "# Ui Notes\n\nPrefer native navigation.")

    docs = skill_docs.list_skill_docs("MOB", "android")

    assert len(docs) == 1
    assert docs[0]["title"] == "Ui Notes"
    assert "Prefer native navigation." in docs[0]["content"]
