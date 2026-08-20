# AGENTS.md

> **OpenAI Codex Agent Instructions**
> Points to: [AI_INSTRUCTIONS.md](AI_INSTRUCTIONS.md)

## Quick Reference

| Item | Value |
|------|-------|
| **Test** | `./venv/bin/python -m pytest --tb=short -q` |
| **Config** | `config.yaml` (read-only without approval) |
| **Secrets** | `.env` (NEVER read or commit) |
| **Context** | `PROJECT_CONTEXT.md` (read and update) |

## Before Any Session
1. Read `AI_INSTRUCTIONS.md` (full rules)
2. Read `PROJECT_CONTEXT.md` (current state)
3. Check `git status` and `git log -5 --oneline`

## Commit Format
```
codex: action: description

Examples:
codex: feat: add new filter engine
codex: fix: resolve VCP calculation bug
codex: test: add unit tests
```

## Documentation
- Document ALL changes with date/time in PROJECT_CONTEXT.md
- Update "Last updated" in AI_INSTRUCTIONS.md when rules change
- Never claim completion if tests fail

---
*For full rules, see AI_INSTRUCTIONS.md*
