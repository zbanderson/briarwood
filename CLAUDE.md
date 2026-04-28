# CLAUDE.md — Briarwood Rules of Engagement

This file is read automatically at the start of every Claude Code session operating in this repository. It is the Claude-specific startup contract for Briarwood; it should stay consistent with `CODEX.md` on project rules while preserving Claude's README-discipline skill workflow.

---

## Orient Yourself First

At the start of every Claude Code session, before taking user task work:

1. Read this file.
2. Read `.claude/skills/readme-discipline/SKILL.md` and execute Job 1 (the drift check). Report findings if any.
3. Read `AGENTS.md` for product direction, architecture rules, OpenAI boundaries, and verification expectations.
4. Read `docs/current_docs_index.md` for the current implementation/documentation map.
5. Verify these authoritative project-state docs exist and are readable: `ARCHITECTURE_CURRENT.md`, `GAP_ANALYSIS.md`, and `TOOL_REGISTRY.md`.
6. Read `CURRENT_STATE.md` if present.
7. Read the relevant sections of `DECISIONS.md` and `ROADMAP.md` for the task. For roadmap planning, handoff planning, large refactors, or ambiguous/high-impact work, read both in full.

Do not begin user task work until the applicable orientation is complete. The cost of orientation is minutes; the cost of skipping it is hours of rework against stale assumptions.

---

## Claude Operating Contract

Claude Code is expected to work as a README-disciplined implementation agent:

- Use `.claude/skills/readme-discipline/SKILL.md` at startup, before module modification, and after contract-level changes.
- Keep changes tied to the user request, `DECISIONS.md`, or `ROADMAP.md`.
- Preserve user work in a dirty tree. Do not revert unrelated changes.
- Use focused verification appropriate to the change, and report commands run plus any failures.
- Stop for explicit review pauses in handoff prompts.

---

## Authoritative Sources — In Priority Order

When information conflicts, the higher-priority source wins.

1. **The code itself.** What a function actually does at its cited line beats any description.
2. **Module READMEs.** Every README under `briarwood/` should reflect the module's actual contract. Trust a current module README over audit docs.
3. **`DECISIONS.md`.** The project owner's decisions on architecture, naming, scope, and contracts.
4. **Current docs.** `AGENTS.md`, `docs/current_docs_index.md`, `ARCHITECTURE_CURRENT.md`, `GAP_ANALYSIS.md`, `TOOL_REGISTRY.md`, and `ROADMAP.md`. These define current direction and system shape, but some may drift at field-name level.
5. **Historical audit docs** (`AUDIT_REPORT.md`, `BRIARWOOD-AUDIT.md`, `UX-ASSESSMENT.md`, `analysis/*.md`, and similar files). Useful for context, not implementation authority.

Briarwood is being built as an AI-native, queryable company. See `design_doc.md` § 3.4 and `ROADMAP.md` for the staged buildout. Treat those principles as constraints on architectural decisions.

If you find a contradiction between sources, never silently reconcile it. Surface it to the user. Add an entry to `DECISIONS.md` if the resolution requires judgment, or to `ROADMAP.md` if it is mechanical drift or cleanup work.

---

## README Discipline

At session startup, execute Job 1 from `.claude/skills/readme-discipline/SKILL.md`.

Before modifying any module under `briarwood/`, execute Job 2: read the module's README and the immediate dependency READMEs that shape its contract.

After any contract-level change to a module, execute Job 3: update the README's prose, update `Last Updated`, and append a dated changelog entry.

See the skill file for the full rules on what counts as a meaningful change and when READMEs should not be updated.

---

## Writing Discipline for Handoffs

Briarwood development is organized into discrete handoffs. Each handoff has an explicit prompt defining its scope. Within a handoff:

- Every change traces to a specific entry in `ROADMAP.md`, `DECISIONS.md`, or the handoff prompt itself. No drive-by fixes.
- If you see something broken that is not in scope, add it to `ROADMAP.md` and keep moving.
- Make one logical change at a time. Do not batch renames, wrapper changes, or dependency updates across multiple modules in a single change.
- Tests should pass after each logical change when practical. If they fail, fix the test or fix the change before continuing.
- Pauses in handoff prompts are mandatory. They exist for user review, not as suggestions.

Use `.github/PULL_REQUEST_TEMPLATE.md` as the canonical shape for change summaries, PR descriptions, and end-of-session handoffs.

---

## Contradictions, Drifts, and Bugs Found During Work

When you find something wrong while doing other work:

- **Contradiction with authoritative docs:** flag it and do not reconcile it silently. Usually add a `DECISIONS.md` entry.
- **Mechanical drift** (field-name mismatch, undeclared dependency, naming collision, stale README detail): add it to `ROADMAP.md`. Do not fix it unless it is in scope.
- **Live production bug:** add it to `ROADMAP.md` with appropriate priority. Do not pull it into the current handoff unless the prompt covers it.
- **Opinion about code quality, style, or architecture:** do not turn it into an unsolicited refactor. Briarwood has an intentional evolution path; ad-hoc cleanup fights that path.

---

## Copyright and Attribution

When writing documentation or READMEs, paraphrase source comments in your own words. Do not reproduce large verbatim blocks from the codebase into READMEs. Cite file paths and line numbers so the reader can inspect the source directly.

---

## Session Anti-Patterns

These are failure modes that have cost time in the past. Avoid them.

- Starting code work without the orientation set above.
- Skipping `.claude/skills/readme-discipline/SKILL.md` startup drift check.
- "Helpfully" fixing a bug that is not in scope.
- Batching multiple logical changes into one diff because they feel related.
- Updating a README to match code you have not actually read line by line.
- Asking the user for repo facts that are discoverable from the codebase or current docs.
- Silently reconciling a contradiction instead of surfacing it.
- Rewriting a template because you think it could be better. Templates are locked; propose changes, do not make them casually.
