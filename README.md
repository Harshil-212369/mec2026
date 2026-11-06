# MEC 2026: Team H / A / J

The problem is revealed Saturday at 10:00. Until then this repo holds only the team rules, the tool check, and the setup handoff.

## Teammates: do this once, in order
| # | Step | Who |
|---|---|---|
| 1 | If `git --version` fails: `winget install --id Git.Git -e`, then open a new PowerShell window | A, J |
| 2 | `git clone https://github.com/Harshil-212369/mec2026 C:\dev\mec2026` (not inside OneDrive) | A, J |
| 3 | `cd C:\dev\mec2026` then `git config core.hooksPath .githooks` | A, J |
| 4 | Double-click `scripts\check-tools.cmd`. It compares your tools with H's versions | A, J |
| 5 | Any FAIL: double-click `scripts\install-tools.cmd` (J: run `scripts\install-tools.cmd -WithClaudeCode` in PowerShell), approve the prompts, open a **new** window, and repeat step 4 | A, J |
| 6 | Paste the final table in the group chat | A, J |
| 7 | Paste `handoff\J_setup_paste_into_claude.md` into a claude.ai chat (Claude Code + Postman connector) | J |
| 8 | Point your GPT/VS Code assistant at `AGENTS.md` (the team rules) | A |

## What is in here
| File | Purpose |
|---|---|
| `AGENTS.md` | Team rules for every AI tool and every person |
| `CLAUDE.md` | Imports `AGENTS.md` and adds Claude Code-only rules |
| `toolchain.json` | H's tool versions: the team reference |
| `scripts\check-tools.*` | Read-only comparison against `toolchain.json` |
| `scripts\install-tools.*` | Installs or upgrades only what failed (winget), asks first |
| `.claude\skills\check-tools` | `/check-tools` in Claude Code: runs the check and explains it |
| `.claude\skills\cloudflare-credits` | Cost rules for H's Cloudflare credits (loads automatically) |
| `.claude\settings.json` | Blocks reading `.env`, no AI commit trailers, asks before push/delete/install |
| `.githooks\commit-msg` | Rejects `Co-Authored-By` trailers from any tool |
| `handoff\` | Paste-in setup guide for J |
