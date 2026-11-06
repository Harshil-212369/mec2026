---
name: check-tools
description: Check that this Windows laptop's dev tools (Git, Node, Python 3.14, VS Code, browser, Postman, Claude Code) match the MEC 2026 team reference in toolchain.json, explain any gaps, and guide installing the missing ones. Use when someone runs /check-tools, asks whether their setup matches the team, or a command fails because a tool is missing or the wrong version.
---

# Check the team toolchain

## 1. Run the check (read-only)
```bash
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-tools.ps1
```
It compares this laptop with `toolchain.json` (H's versions) and prints one row per tool: PASS / WARN / FAIL, this laptop's version, the team reference, and the fix. Exit code 0 = no FAIL, 1 = at least one FAIL, 2 = `toolchain.json` missing (tell them to `git pull`).

## 2. Report
- Show the table as the script printed it. Do not re-type or "correct" versions.
- For each FAIL or WARN, one plain sentence: what is wrong and why it matters for Saturday.
  - Git older than the reference: misses security fixes.
  - Node with a different major: npm and lockfile behaviour can differ between teammates.
  - No Python 3.14: our venv and pinned packages target 3.14. Other Python versions can stay installed.
  - Postman app missing: the organizers require it.
  - Claude Code missing: only H and J need it. A uses GPT, so ignore this for A.
  - python alias WARN: Windows Store stub. The fix is in Settings, not winget.

## 3. Fix (ask first)
- Installing changes the system, so **ask before running anything**. Recommend the person runs this themselves in a normal PowerShell window, because winget may show admin (UAC) prompts that you cannot click:
  ```powershell
  scripts\install-tools.cmd                    # only what is FAIL; shows the plan and asks y/n
  scripts\install-tools.cmd -WithClaudeCode    # J: also installs Claude Code
  ```
- After installing: **open a new terminal** (PATH only refreshes in new windows), then run the check again. That second run is the verdict. Do not declare success from installer output.

## 4. Never
- Never edit `toolchain.json`. Only H changes the team reference, with `scripts/check-tools.ps1 -WriteReference`.
- Never uninstall another Python or Node version to "fix" a mismatch. Side-by-side installs are fine.
- Never use WSL or Linux package managers for this repo's toolchain.
