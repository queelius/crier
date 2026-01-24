"""Claude Code skill installation for crier."""

from importlib.resources import files
from pathlib import Path

SKILL_NAME = "crier"

# Claude Code skills directory structure
GLOBAL_SKILLS_DIR = Path.home() / ".claude" / "skills"
LOCAL_SKILLS_DIR = Path(".claude") / "skills"


def _load_skill_content() -> str:
    """Load SKILL.md content from package resources."""
    return files("crier").joinpath("SKILL.md").read_text()


# Keep for backwards compatibility, but load from file
_SKILL_CONTENT_CACHE: str | None = None


def get_skill_content() -> str:
    """Get the skill content from package resource."""
    global _SKILL_CONTENT_CACHE
    if _SKILL_CONTENT_CACHE is None:
        _SKILL_CONTENT_CACHE = _load_skill_content()
    return _SKILL_CONTENT_CACHE


def get_skill_dir(local: bool = False) -> Path:
    """Get the skills directory path."""
    if local:
        return LOCAL_SKILLS_DIR / SKILL_NAME
    return GLOBAL_SKILLS_DIR / SKILL_NAME


def get_skill_path(local: bool = False) -> Path:
    """Get the SKILL.md file path."""
    return get_skill_dir(local) / "SKILL.md"


def is_installed(local: bool | None = None) -> dict[str, bool]:
    """Check if skill is installed.

    Args:
        local: If True, check only local. If False, check only global.
               If None, check both.

    Returns:
        Dict with 'global' and 'local' keys indicating installation status.
    """
    result = {"global": False, "local": False}

    if local is None or local is False:
        result["global"] = get_skill_path(local=False).exists()

    if local is None or local is True:
        result["local"] = get_skill_path(local=True).exists()

    return result


def install(local: bool = False) -> Path:
    """Install the crier skill.

    Args:
        local: If True, install to .claude/skills/ (repo-local).
               If False, install to ~/.claude/skills/ (global).

    Returns:
        Path to the installed SKILL.md file.
    """
    skill_dir = get_skill_dir(local)
    skill_path = get_skill_path(local)

    # Create directory
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Write skill file
    skill_path.write_text(get_skill_content())

    return skill_path


def uninstall(local: bool = False) -> bool:
    """Uninstall the crier skill.

    Args:
        local: If True, uninstall from .claude/skills/.
               If False, uninstall from ~/.claude/skills/.

    Returns:
        True if skill was removed, False if it wasn't installed.
    """
    skill_path = get_skill_path(local)
    skill_dir = get_skill_dir(local)

    if not skill_path.exists():
        return False

    # Remove the skill file
    skill_path.unlink()

    # Remove the directory if empty
    try:
        skill_dir.rmdir()
    except OSError:
        pass  # Directory not empty or other error

    return True


