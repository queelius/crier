# Crier Claude Code Plugin Design

**Goal:** Extract crier's Claude Code skill from the mf plugin into a standalone `crier` plugin in the alex-claude-plugins marketplace. Add a slash command and autonomous agent.

**Location:** `alex-claude-plugins/crier/` (alongside mf, repoindex, etc.)

---

## Plugin Structure

```
alex-claude-plugins/crier/
├── README.md
├── LICENSE
├── skills/
│   └── crier/
│       └── SKILL.md          # CLI reference + workflow guidance + rewrite guidelines
├── commands/
│   └── crier.md              # /crier slash command for quick audit/publish
└── agents/
    └── cross-poster.md       # Autonomous agent for bulk cross-posting
```

## Components

### 1. Skill (`skills/crier/SKILL.md`)

The existing mf crier skill content, updated for:
- Global-only config (no `.crier/config.yaml`, no `--project`)
- `site_root` in `~/.config/crier/config.yaml`
- Registry at `<site_root>/.crier/registry.yaml`
- Current CLI commands and options

Content sections:
- Platform reference table (modes, limits, update support)
- CLI command reference (all commands)
- Checking publication status workflow
- Complete dialogue examples (API, short-form, import, paste modes)
- Rewrite guidelines per platform (voice, format, anti-patterns)
- Bulk operations and filters
- Configuration (global-only, site_root)
- Front matter requirements

### 2. Slash Command (`commands/crier.md`)

`/crier` — Quick cross-posting workflow. When invoked:
1. Run `crier audit` to show what needs publishing
2. Present summary and let user choose scope
3. Guide through publish: API platforms auto-post, short-form get rewrites, manual/import get instructions
4. Report results

### 3. Agent (`agents/cross-poster.md`)

Autonomous agent for bulk cross-posting tasks. Can be dispatched via `Task` tool:
- Given a scope (path, date range, platform filter)
- Runs audit, publishes to API platforms
- Writes rewrites for short-form platforms
- Handles manual/import platform instructions
- Reports full results

## Related Changes

### mf plugin
- Remove `skills/crier/SKILL.md` from `alex-claude-plugins/mf/skills/crier/`
- Add note in mf's SKILL.md: "For cross-posting, see the `crier` plugin"

### Built-in `crier skill` command
- Add deprecation warning to `crier skill install/uninstall/status/show`
- Message: "The built-in skill is deprecated. Install the crier Claude Code plugin instead."
- Keep functional for backward compat, remove in next major version

### CLAUDE.md
- Update for global-only config
- Remove references to local `.crier/config.yaml`
- Document `site_root`
- Note plugin replaces built-in skill

---

## Implementation Tasks

### Task 1: Create crier plugin in alex-claude-plugins
- Create `alex-claude-plugins/crier/` directory structure
- Write `skills/crier/SKILL.md` (adapted from mf's version, updated for global config)
- Write `commands/crier.md`
- Write `agents/cross-poster.md`
- Add README.md and LICENSE

### Task 2: Update mf plugin
- Remove `alex-claude-plugins/mf/skills/crier/` directory
- Add cross-reference in mf SKILL.md

### Task 3: Deprecate built-in skill
- Add deprecation warning to `skill.py` functions
- Update CLI `skill` command to show warning
- Update tests

### Task 4: Update crier docs
- Update CLAUDE.md for global-only config + plugin reference
- Update README.md
