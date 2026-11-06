# CLAUDE.md: MEC 2026 (Claude Code: H and J)

@AGENTS.md

The shared team rules are above. The rules below apply only to Claude Code.

## Shell on Windows
- Your Bash tool runs in **Git Bash**: use forward slashes and the venv interpreter (`.venv/Scripts/python -m pytest -q`).
- Run PowerShell scripts as `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/<name>.ps1`.

## Session hygiene
- New feature or module: **plan mode first**. Write nothing until the teammate approves the plan. Each plan step names the command that will show it working.
- Check `/context`. At about half full, start fresh with `/clear` instead of `/compact`, then re-read this file and your `docs/handoff/<H|J>.md`.
- Read `docs/problem_statement.md` and `docs/rubric.md` from the repo; do not re-extract the original PDF or photo each session.
- After editing `AGENTS.md` or this file, start a fresh session and confirm the new rule loaded.

## Enforced settings
`.claude/settings.json` blocks reading `.env`, turns off commit/PR attribution, and asks before `git push`, hard resets, deletes, and installs. If a rule blocks you, stop and ask; do not try an equivalent command.

## Connectors
- **Postman** (H, J): read-only use any time; creating or changing collections needs the teammate's OK.
- **Supabase / Cloudflare**: only if chosen at intake (AGENTS rule 7). Any write needs the teammate's OK. For Cloudflare, load the `cloudflare-credits` skill first. Never create, pause, or delete Supabase projects.
- If a connector is missing from `/mcp`, say so and continue with Tier 1. Never ask for API keys in chat.

## Skills in this repo
- `/check-tools`: compare this laptop's toolchain with `toolchain.json` and fix gaps.
- `cloudflare-credits`: loads automatically for any Cloudflare work.
