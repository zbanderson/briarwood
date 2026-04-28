---
name: readme-discipline
description: Enforces README-first discipline across the Briarwood codebase. Use this skill at the start of EVERY Claude Code session and before touching any module that has an associated README. Also use this skill after making any meaningful change to a module's contract (new public function, changed input/output schema, new dependency, changed invariants) — the skill governs when and how to update READMEs and changelog entries. Trigger this skill even when the user hasn't explicitly mentioned READMEs, whenever the task involves modifying, extending, or calling any module under briarwood/ that has a README.md present. Also trigger at session startup to perform the drift check.
---

# Briarwood README Discipline

This skill enforces the documentation discipline that keeps Briarwood's READMEs trustworthy across AI-assisted development sessions. Without this discipline, READMEs rot within weeks: prose describes contracts the code no longer has, file paths point to functions that were renamed, and the whole documentation layer becomes noise. With this discipline, every module README stays a reliable contract between you and any future Claude Code session.

The skill has three jobs. Read the section for whichever one applies to your current task.

## Job 1: Session Startup — Drift Check

Run this at the start of every Claude Code session, before doing any other work.

**What to do:**

1. Locate every `README.md` file under `briarwood/` (exclude the repo root README and any READMEs inside `node_modules/`, `.venv/`, or other dependency directories).
2. For each README, perform a lightweight drift check:
   - Does the file path(s) mentioned in the "Entry Point" or "Location" section still exist?
   - Do the function names mentioned in "Entry" or "Public API" still exist in that file?
   - Does the "Last Updated" date match a recent-enough state (if older than 30 days AND the module has been touched since, flag it)?
3. Produce a short startup report in this format:

   ```
   README Drift Check — [date]
   
   ✅ Clean: [N] READMEs verified
   ⚠️  Drift detected: [N] READMEs
      - briarwood/modules/risk_model/README.md
        - Entry `run_risk_model(context)` not found at cited path
      - briarwood/agents/router/README.md
        - Last updated 2026-01-15; router.py modified 2026-04-20
   📋 Missing: [N] modules without READMEs
      - briarwood/modules/comparable_sales/
   ```

4. If drift is detected, DO NOT auto-fix. Report it to the user and ask whether to fix now or defer. Silent auto-fixes defeat the point of the drift check — the user needs to see what changed.
5. If the user's current task touches a module with flagged drift, resolve that module's drift before proceeding.

**Why this matters:** READMEs are only useful if they're honest. One stale README poisons every future session that reads it, because Claude Code will treat it as ground truth. The startup check is cheap insurance against that compounding error.

## Job 2: Before Modifying a Module — Read First

Triggered when the current task involves reading, modifying, extending, or calling any module under `briarwood/` that has a README.

**What to do:**

1. Before reading the module's source code, read its `README.md` in full.
2. Before reading a sibling module that the target module depends on, read that sibling's README too.
3. If the README references a parent or orchestrator (e.g., a model's README references the scoped registry), read that parent README as well.
4. Only after the README context is loaded, begin reading and modifying the source code.

**Important:** Treat the README as the contract. If the source code appears to contradict the README, don't assume the source is right. Flag the discrepancy to the user and ask which is authoritative. This is how drift is caught in flight.

**Scope discipline:** Don't read every README in the repo for every task. Only read READMEs for modules directly involved in the current task plus their immediate dependencies.

## Job 3: After a Meaningful Change — Update the README

Triggered when a change has been made to a module's *contract*, not its internals.

### What counts as a meaningful change (update the README)

- New public function, class, or tool registry entry
- Change to function signature, Pydantic schema, or input/output types
- Change to what the module computes or produces (semantic change)
- New dependency on another module
- Removed dependency on another module
- Change to invariants (e.g., "confidence is always 0–1" becomes "confidence may be null if inputs sparse")
- Change to the module's readiness status (e.g., NEEDS_ADAPTER → READY)
- Promotion from legacy to scoped registry (or vice versa)
- Deprecation

### What does NOT count (do not update the README)

- Bug fix that preserves the contract
- Internal refactoring with no contract change
- Adding tests
- Performance optimization with no behavior change
- Typo fixes in code comments
- Linting fixes

### How to update

1. Update the descriptive prose to reflect the new contract. Do not leave stale prose and append a correction; rewrite the affected sentences.
2. Append a dated entry to the `## Changelog` section at the bottom of the README. Format:

   ```markdown
   ## Changelog
   
   ### 2026-04-24
   - Added `min_confidence` optional input parameter (default 0.5)
   - Output schema: `ValuationResult.confidence` is now always float, never null
   - Contract change: breaks any caller that checked `confidence is None`
   ```

3. Update the `## Last Updated` line at the top of the README to today's date.
4. If the change affects other modules that depend on this one, note which sibling READMEs also need updating. Flag them to the user — do not cascade updates silently.

### Changelog discipline

- One entry per dated session, not per commit. Group related changes.
- Lead with contract changes; internal notes are optional.
- Use "Contract change:" prefix for anything that could break callers. This is what future-you will grep for when something mysteriously breaks.
- Never delete old changelog entries. The history is the point.

## README Templates

Two templates exist, and each module uses the one that fits.

- **Scoped-registry models** (the 15 models registered in `briarwood/execution/registry.py`) use `references/template_model.md`.
- **Agents, pipelines, and orchestration modules** (router, dispatch, composer, representation agent, value scout, claims pipeline, synthesis, etc.) use `references/template_agent.md`.

When creating a new README, copy the appropriate template and fill in every section. Do not delete sections — if a section doesn't apply, write "N/A" with one sentence explaining why. Empty sections communicate nothing; explicit N/A communicates that you considered it.

When in doubt about which template applies: if the module exposes a single callable entry point with typed inputs and outputs that could be called in isolation by an orchestrating LLM, use the model template. Otherwise use the agent template.

## Anti-patterns to avoid

- **Drive-by README edits.** Do not update a README unless you made the change that justifies the update. Reading a README does not grant permission to edit it.
- **Speculative documentation.** Do not document planned contracts. READMEs describe what exists, not what is intended. Intent belongs in `DECISIONS.md` or `GAP_ANALYSIS.md`.
- **Changelog bloat.** If every session produces a changelog entry, the changelog is not tracking meaningful change — it's tracking activity. Prune the trigger: only contract-level changes go in.
- **Silent drift correction.** If the startup drift check finds a stale README, never "just fix it." Report it first, let the user approve the correction. This preserves the invariant that READMEs only change deliberately.
- **Cascading updates.** If a change affects three modules, update three READMEs — but flag each one to the user individually. A single session that silently edits five READMEs is a session that will accidentally break something.

## Integration with CLAUDE.md

This skill is wired into every session via `CLAUDE.md` at the repo root. The CLAUDE.md entry reads:

```
At session startup, run the README drift check defined in
.claude/skills/readme-discipline/SKILL.md Job 1.
Before modifying any module under briarwood/, execute Job 2.
After any contract-level change, execute Job 3.
```

If you are reading this skill but CLAUDE.md does not contain that entry, flag it to the user — the skill cannot do its job reliably without the startup trigger.
