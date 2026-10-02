"""Skill loading / registry tests."""

from pathlib import Path

from src.skills import SkillRegistry, load_skill_dir, load_skills


def _write_skill(
    folder: Path,
    *,
    name: str = "demo-skill",
    description: str = "Short description",
    caption: str = "Demo",
    body: str = "System prompt body",
    include_skill_md: bool = True,
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    if not include_skill_md:
        return
    (folder / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"caption: {caption}\n"
        f"description: |\n  {description}\n"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )


def test_load_project_skill(skills_dir: Path) -> None:
    skills = load_skills(skills_dir)
    assert "meeting-minutes" in skills
    assert skills["meeting-minutes"].has_files is True


def test_invalid_name_skipped(tmp_path: Path, caplog) -> None:
    _write_skill(tmp_path / "bad", name="Invalid_Name")
    with caplog.at_level("WARNING"):
        assert load_skills(tmp_path) == {}


def test_empty_body_skipped(tmp_path: Path, caplog) -> None:
    _write_skill(tmp_path / "empty", body="   ")
    with caplog.at_level("WARNING"):
        assert load_skills(tmp_path) == {}


def test_long_description_skipped(tmp_path: Path, caplog) -> None:
    _write_skill(tmp_path / "long", description="x" * 1025)
    with caplog.at_level("WARNING"):
        assert load_skills(tmp_path) == {}


def test_missing_skill_md_skipped(tmp_path: Path, caplog) -> None:
    _write_skill(tmp_path / "no-md", include_skill_md=False)
    with caplog.at_level("WARNING"):
        assert load_skills(tmp_path) == {}


def test_registry_reload(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    _write_skill(root / "alpha", name="alpha", caption="Alpha")
    registry = SkillRegistry(root)
    assert [s.name for s in registry.list_skills()] == ["alpha"]

    _write_skill(root / "beta", name="beta", caption="Beta Search")
    registry.reload()
    assert [s.name for s in registry.list_skills()] == ["alpha", "beta"]
    assert [s.name for s in registry.list_skills("search")] == ["beta"]


def test_folder_name_fallback(tmp_path: Path) -> None:
    folder = tmp_path / "folder-skill"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\ndescription: Desc\ncaption: Cap\n---\n\nBody\n",
        encoding="utf-8",
    )
    assert load_skill_dir(folder).name == "folder-skill"
