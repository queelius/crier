"""Tests for crier.skill module."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from crier.skill import (
    SKILL_NAME,
    GLOBAL_SKILLS_DIR,
    LOCAL_SKILLS_DIR,
    get_skill_content,
    get_skill_dir,
    get_skill_path,
    is_installed,
    install,
    uninstall,
    _load_skill_content,
    _SKILL_CONTENT_CACHE,
)
import crier.skill as skill_module


class TestConstants:
    """Tests for module-level constants."""

    def test_skill_name(self):
        assert SKILL_NAME == "crier"

    def test_global_skills_dir(self):
        assert GLOBAL_SKILLS_DIR == Path.home() / ".claude" / "skills"

    def test_local_skills_dir(self):
        assert LOCAL_SKILLS_DIR == Path(".claude") / "skills"


class TestGetSkillContent:
    """Tests for get_skill_content()."""

    def test_returns_string(self):
        content = get_skill_content()
        assert isinstance(content, str)

    def test_content_not_empty(self):
        content = get_skill_content()
        assert len(content) > 0

    def test_content_contains_crier_reference(self):
        """SKILL.md should reference crier somewhere."""
        content = get_skill_content()
        assert "crier" in content.lower()

    def test_caching_returns_same_object(self):
        """Subsequent calls return the cached content."""
        content1 = get_skill_content()
        content2 = get_skill_content()
        # Should be the exact same string object due to caching
        assert content1 is content2

    def test_load_skill_content_reads_from_package(self):
        """_load_skill_content reads from package resources."""
        content = _load_skill_content()
        assert isinstance(content, str)
        assert len(content) > 0


class TestGetSkillDir:
    """Tests for get_skill_dir()."""

    def test_global_skill_dir(self):
        result = get_skill_dir(local=False)
        expected = Path.home() / ".claude" / "skills" / "crier"
        assert result == expected

    def test_local_skill_dir(self):
        result = get_skill_dir(local=True)
        expected = Path(".claude") / "skills" / "crier"
        assert result == expected

    def test_default_is_global(self):
        result = get_skill_dir()
        expected = get_skill_dir(local=False)
        assert result == expected


class TestGetSkillPath:
    """Tests for get_skill_path()."""

    def test_global_skill_path(self):
        result = get_skill_path(local=False)
        expected = Path.home() / ".claude" / "skills" / "crier" / "SKILL.md"
        assert result == expected

    def test_local_skill_path(self):
        result = get_skill_path(local=True)
        expected = Path(".claude") / "skills" / "crier" / "SKILL.md"
        assert result == expected

    def test_default_is_global(self):
        result = get_skill_path()
        expected = get_skill_path(local=False)
        assert result == expected

    def test_path_ends_with_skill_md(self):
        assert get_skill_path(local=False).name == "SKILL.md"
        assert get_skill_path(local=True).name == "SKILL.md"


class TestIsInstalled:
    """Tests for is_installed()."""

    def test_not_installed_returns_false(self, tmp_path, monkeypatch):
        """When no SKILL.md exists, both are False."""
        monkeypatch.setattr(
            "crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills"
        )
        monkeypatch.setattr(
            "crier.skill.LOCAL_SKILLS_DIR", tmp_path / "local_skills"
        )
        result = is_installed()
        assert result == {"global": False, "local": False}

    def test_global_installed(self, tmp_path, monkeypatch):
        """When global SKILL.md exists, global is True."""
        global_dir = tmp_path / "global_skills" / "crier"
        global_dir.mkdir(parents=True)
        (global_dir / "SKILL.md").write_text("skill content")

        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills")
        monkeypatch.setattr("crier.skill.LOCAL_SKILLS_DIR", tmp_path / "local_skills")

        result = is_installed()
        assert result["global"] is True
        assert result["local"] is False

    def test_local_installed(self, tmp_path, monkeypatch):
        """When local SKILL.md exists, local is True."""
        local_dir = tmp_path / "local_skills" / "crier"
        local_dir.mkdir(parents=True)
        (local_dir / "SKILL.md").write_text("skill content")

        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills")
        monkeypatch.setattr("crier.skill.LOCAL_SKILLS_DIR", tmp_path / "local_skills")

        result = is_installed()
        assert result["global"] is False
        assert result["local"] is True

    def test_both_installed(self, tmp_path, monkeypatch):
        """When both exist, both are True."""
        global_dir = tmp_path / "global_skills" / "crier"
        global_dir.mkdir(parents=True)
        (global_dir / "SKILL.md").write_text("global skill")

        local_dir = tmp_path / "local_skills" / "crier"
        local_dir.mkdir(parents=True)
        (local_dir / "SKILL.md").write_text("local skill")

        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills")
        monkeypatch.setattr("crier.skill.LOCAL_SKILLS_DIR", tmp_path / "local_skills")

        result = is_installed()
        assert result["global"] is True
        assert result["local"] is True

    def test_check_only_local(self, tmp_path, monkeypatch):
        """local=True checks only local."""
        local_dir = tmp_path / "local_skills" / "crier"
        local_dir.mkdir(parents=True)
        (local_dir / "SKILL.md").write_text("local skill")

        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills")
        monkeypatch.setattr("crier.skill.LOCAL_SKILLS_DIR", tmp_path / "local_skills")

        result = is_installed(local=True)
        assert result["global"] is False  # Not checked
        assert result["local"] is True

    def test_check_only_global(self, tmp_path, monkeypatch):
        """local=False checks only global."""
        global_dir = tmp_path / "global_skills" / "crier"
        global_dir.mkdir(parents=True)
        (global_dir / "SKILL.md").write_text("global skill")

        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills")
        monkeypatch.setattr("crier.skill.LOCAL_SKILLS_DIR", tmp_path / "local_skills")

        result = is_installed(local=False)
        assert result["global"] is True
        assert result["local"] is False  # Not checked


class TestInstall:
    """Tests for install()."""

    def test_install_global(self, tmp_path, monkeypatch):
        """Install globally creates SKILL.md in global dir."""
        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills")

        result_path = install(local=False)

        assert result_path.exists()
        assert result_path == tmp_path / "global_skills" / "crier" / "SKILL.md"
        content = result_path.read_text()
        assert len(content) > 0

    def test_install_local(self, tmp_path, monkeypatch):
        """Install locally creates SKILL.md in local dir."""
        monkeypatch.setattr("crier.skill.LOCAL_SKILLS_DIR", tmp_path / "local_skills")

        result_path = install(local=True)

        assert result_path.exists()
        assert result_path == tmp_path / "local_skills" / "crier" / "SKILL.md"
        content = result_path.read_text()
        assert len(content) > 0

    def test_install_creates_directories(self, tmp_path, monkeypatch):
        """Install creates parent directories if they do not exist."""
        deep_path = tmp_path / "a" / "b" / "c" / "skills"
        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", deep_path)

        result_path = install(local=False)

        assert result_path.exists()
        assert (deep_path / "crier").is_dir()

    def test_install_default_is_global(self, tmp_path, monkeypatch):
        """Default install() is global."""
        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills")

        result_path = install()

        assert result_path == tmp_path / "global_skills" / "crier" / "SKILL.md"
        assert result_path.exists()

    def test_install_overwrites_existing(self, tmp_path, monkeypatch):
        """Install overwrites an existing SKILL.md."""
        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills")

        # Create existing file with old content
        skill_dir = tmp_path / "global_skills" / "crier"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("old content")

        result_path = install(local=False)

        # Content should be replaced with actual skill content
        new_content = result_path.read_text()
        assert new_content != "old content"
        assert len(new_content) > 0

    def test_install_content_matches_get_skill_content(self, tmp_path, monkeypatch):
        """Installed file matches get_skill_content()."""
        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills")

        result_path = install(local=False)
        installed_content = result_path.read_text()
        expected_content = get_skill_content()
        assert installed_content == expected_content


class TestUninstall:
    """Tests for uninstall()."""

    def test_uninstall_global(self, tmp_path, monkeypatch):
        """Uninstall removes the global SKILL.md."""
        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills")

        # Install first
        install(local=False)
        skill_path = get_skill_path(local=False)
        assert skill_path.exists()

        # Uninstall
        result = uninstall(local=False)
        assert result is True
        assert not skill_path.exists()

    def test_uninstall_local(self, tmp_path, monkeypatch):
        """Uninstall removes the local SKILL.md."""
        monkeypatch.setattr("crier.skill.LOCAL_SKILLS_DIR", tmp_path / "local_skills")

        install(local=True)
        skill_path = get_skill_path(local=True)
        assert skill_path.exists()

        result = uninstall(local=True)
        assert result is True
        assert not skill_path.exists()

    def test_uninstall_not_installed_returns_false(self, tmp_path, monkeypatch):
        """Uninstall returns False when not installed."""
        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills")

        result = uninstall(local=False)
        assert result is False

    def test_uninstall_removes_empty_directory(self, tmp_path, monkeypatch):
        """Uninstall removes the crier skill directory if empty after removal."""
        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills")

        install(local=False)
        skill_dir = get_skill_dir(local=False)
        assert skill_dir.exists()

        uninstall(local=False)
        # Directory should be removed since it was empty
        assert not skill_dir.exists()

    def test_uninstall_preserves_nonempty_directory(self, tmp_path, monkeypatch):
        """Uninstall preserves directory if other files exist."""
        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills")

        install(local=False)
        skill_dir = get_skill_dir(local=False)

        # Add another file to the directory
        (skill_dir / "other_file.txt").write_text("keep me")

        uninstall(local=False)
        # Directory should still exist because of the other file
        assert skill_dir.exists()
        assert (skill_dir / "other_file.txt").exists()
        assert not (skill_dir / "SKILL.md").exists()

    def test_uninstall_default_is_global(self, tmp_path, monkeypatch):
        """Default uninstall() is global."""
        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills")

        install(local=False)
        result = uninstall()
        assert result is True


class TestInstallUninstallRoundtrip:
    """Integration tests for install/uninstall cycle."""

    def test_install_then_check_then_uninstall(self, tmp_path, monkeypatch):
        """Full lifecycle: install, verify installed, uninstall, verify gone."""
        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", tmp_path / "global_skills")
        monkeypatch.setattr("crier.skill.LOCAL_SKILLS_DIR", tmp_path / "local_skills")

        # Initially not installed
        status = is_installed()
        assert status["global"] is False
        assert status["local"] is False

        # Install globally
        install(local=False)
        status = is_installed()
        assert status["global"] is True
        assert status["local"] is False

        # Also install locally
        install(local=True)
        status = is_installed()
        assert status["global"] is True
        assert status["local"] is True

        # Uninstall global only
        uninstall(local=False)
        status = is_installed()
        assert status["global"] is False
        assert status["local"] is True

        # Uninstall local
        uninstall(local=True)
        status = is_installed()
        assert status["global"] is False
        assert status["local"] is False
