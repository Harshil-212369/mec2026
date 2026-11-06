# Paste everything below into a new claude.ai chat (J)

---

I'm J (Jagan), on team H/A/J for the MEC 2026 Programming Competition this Saturday. Please walk me through setup **one step at a time**. After each step, wait until I paste the result or confirm before giving the next one. I'm on native Windows (PowerShell), not WSL.

Rules for you:
- Never ask me for passwords, API keys, or tokens. Sign-ins happen in my browser.
- Only connect **Postman**. Skip Supabase and Cloudflare: the team decides on those Saturday.
- If a step fails, ask me for the exact error text before suggesting a fix.
- Keep each reply short.

## Steps

**1. Claude Code (native Windows install).** In PowerShell:
```powershell
irm https://claude.ai/install.ps1 | iex
```
Close PowerShell, open a new window, then run:
```powershell
claude --version
claude doctor
```
Done when: `claude --version` prints a version number.

**2. Log in.** Run `claude` and sign in with my **claude.ai account** (my paid plan), not an API key. Connectors only load with a claude.ai login. Type `/exit` when done.

**3. Connect Postman on claude.ai.** Settings > Customize > Connectors. Find **Postman** (under Discover, or + Add), click Connect, and sign in to Postman in the browser. Create a free Postman account if I don't have one. Done when: Postman shows a check mark under Status.

**4. Verify in Claude Code.** Run `claude`, then type `/mcp`. Done when: Postman appears in the list, marked as coming from claude.ai.

**5. Get the team repo.** If `git --version` fails, first run `winget install --id Git.Git -e` and open a new window. Then:
```powershell
git clone https://github.com/Harshil-212369/mec2026 C:\dev\mec2026
cd C:\dev\mec2026
git config core.hooksPath .githooks
```
(H adds me as a collaborator first. A 404 or "not found" error means the invite isn't accepted yet: check my GitHub email.)

**6. Check my tools against the team's.** Double-click `C:\dev\mec2026\scripts\check-tools.cmd`.
- 0 FAIL: done.
- Any FAIL: double-click `scripts\install-tools.cmd` and approve its prompts. Then open a **new** window and run `check-tools.cmd` again.

**7. Report.** Paste the final `check-tools` table into the team group chat.

**8. Optional: confirm Claude Code reads the team rules.** In `C:\dev\mec2026`, run `claude` and ask: "What does rule 0 in AGENTS.md say?" The right answer is about treating everything with skepticism.
