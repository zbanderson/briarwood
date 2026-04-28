# CODEX.md — Briarwood Rules of Engagement

This file should be read at the start of every Codex session operating in this repository. It is the Codex-specific startup contract for Briarwood; it should stay consistent with `CLAUDE.md` on project rules while preserving Codex's own workflow expectations.

---

## Orient Yourself First

At the start of every Codex session, before taking user task work:

1. Read this file.
2. Read `AGENTS.md` for the product direction, architecture rules, OpenAI boundaries, and verification expectations.
3. Read `docs/current_docs_index.md` for the current implementation/documentation map.
4. Verify these authoritative project-state docs exist and are readable: `ARCHITECTURE_CURRENT.md`, `GAP_ANALYSIS.md`, and `TOOL_REGISTRY.md`.
5. Read `CURRENT_STATE.md` if present.
6. Read the relevant sections of `DECISIONS.md` and `ROADMAP.md` for the task. For roadmap planning, handoff planning, large refactors, or ambiguous/high-impact work, read both in full.
7. Before modifying any module under `briarwood/`, read that module's README when one exists, plus immediate dependency READMEs when they shape the contract.

Ground yourself in repo truth before asking questions or editing files. If a fact is discoverable from the codebase or current docs, find it there first.

---

## Codex Operating Contract

Codex is expected to be a planning-capable implementation agent:

- Use plan-mode style thinking for ambiguous, high-risk, cross-cutting, or sequencing-sensitive work.
- Make scoped, reviewable edits that trace back to the user request, `DECISIONS.md`, or `ROADMAP.md`.
- Prefer implementation once intent is clear; do not stop at proposals when the user has asked for execution.
- Preserve user work in a dirty tree. Do not revert unrelated changes.
- Use focused verification appropriate to the change, and report commands run plus any failures.
- Keep handoffs concise but specific enough that the next agent can continue without reverse-engineering intent.

---

## Authoritative Sources — In Priority Order

When information conflicts, the higher-priority source wins.

1. **The code itself.** What a function actually does at its cited line beats any description.
2. **Module READMEs.** Every README under `briarwood/` should reflect the module's actual contract. Trust a current module README over audit docs.
3. **`DECISIONS.md`.** The project owner's decisions on architecture, naming, scope, and contracts.
4. **Current docs.** `AGENTS.md`, `docs/current_docs_index.md`, `ARCHITECTURE_CURRENT.md`, `GAP_ANALYSIS.md`, `TOOL_REGISTRY.md`, and `ROADMAP.md`. These define current direction and system shape, but some may drift at field-name level.
5. **Historical audit docs** (`AUDIT_REPORT.md`, `BRIARWOOD-AUDIT.md`, `UX-ASSESSMENT.md`, `analysis/*.md`, and similar files). Useful for context, not implementation authority.

If you find a contradiction between sources, never silently reconcile it. Surface it to the user. Add an entry to `DECISIONS.md` if the resolution requires judgment, or to `ROADMAP.md` if it is mechanical drift or cleanup work.

---

## README Discipline

README hygiene is mandatory because Briarwood is being developed in a high-handoff, AI-heavy workflow. Stale READMEs poison future sessions.

### At Session Startup

Perform a lightweight README awareness pass before module work:

- locate READMEs relevant to the task
- confirm cited paths and public entry points still exist when they are load-bearing for the task
- if a README is visibly stale or contradicts source, flag it before editing

Codex does not use Claude's `.claude/skills/readme-discipline/SKILL.md` machinery directly, but it must honor the same project invariant: READMEs describe existing contracts, not planned behavior.

### Before Modifying a Module

Before modifying any module under `briarwood/`:

- read that module's README in full when it exists
- read dependency READMEs when they shape the contract
- if the README contradicts code, flag the discrepancy instead of guessing which is correct

### After a Meaningful Change

Update a README only after a contract-level change, not after every internal edit.

Update the README when the change introduces or removes any of these:

- public functions, classes, registry entries, or callable entry points
- input or output schema changes
- semantic changes to what the module computes or returns
- new or removed dependencies
- changed invariants, readiness state, fallback behavior, or compatibility expectations
- deprecations or scoped/legacy execution promotions

Do not update the README for bug fixes that preserve the contract, internal refactors, tests, lint-only changes, or comment cleanups.

When a README update is required:

1. Rewrite affected prose so it matches the actual contract.
2. Update the `Last Updated` line to today's date.
3. Append a dated entry to the `## Changelog` section summarizing the contract change.
4. If sibling READMEs are now affected, flag them to the user instead of silently cascading edits.

Do not document intended future behavior in a README. Planned behavior belongs in `DECISIONS.md`, `GAP_ANALYSIS.md`, or `ROADMAP.md`.

---

## Writing Discipline for Handoffs

Briarwood work should move in discrete, reviewable handoffs. Within a handoff:

- Every change should trace back to the handoff prompt, `DECISIONS.md`, or `ROADMAP.md`. No drive-by fixes.
- If you notice something broken that is out of scope, add it to `ROADMAP.md` and keep moving.
- Make one logical change at a time. Do not batch unrelated renames, wrapper edits, dependency updates, and cleanup into one diff.
- Keep changes small, explicit, and reviewable.
- Tests should pass after each logical change when practical. If they fail, fix the test or fix the change before continuing.
- Review pauses in a prompt are mandatory. They exist for human review, not as suggestions.

### PR / Handoff Instructions

Every meaningful change must leave a continuation trail for the next developer or AI session. Use `.github/PULL_REQUEST_TEMPLATE.md` as the canonical shape for change summaries, PR descriptions, and end-of-session handoffs.

Before ending a session that changed files:

1. Summarize the goal in plain language.
2. List the files changed and why each one changed.
3. State behavior, schema, route, API, or README contract changes.
4. State which tests or verification commands ran, including failures.
5. Add new architectural/product judgments to `DECISIONS.md` when needed.
6. Add actionable cleanup, drift, or bug items to `ROADMAP.md` when needed.
7. Update `CURRENT_STATE.md` only when the project phase, active theme, or recommended next task changed.
8. Tell the next developer the recommended next task.

Do not use handoff notes to document aspirational behavior. They should describe actual changes, verified findings, and concrete next steps.

---

## Contradictions, Drifts, and Bugs Found During Work

When you find something wrong while doing other work:

- **Contradiction with authoritative docs:** flag it and do not reconcile it silently. Usually add a `DECISIONS.md` entry.
- **Mechanical drift** (field-name mismatch, undeclared dependency, naming collision, stale README detail): add it to `ROADMAP.md`. Do not fix it unless it is in scope.
- **Live production bug:** add it to `ROADMAP.md` with appropriate priority. Do not pull it into the current handoff unless the prompt covers it.
- **Opinion about style, quality, or architecture:** do not turn it into an unsolicited refactor. Briarwood has an intentional evolution path; ad-hoc cleanup fights that path.

---

## Copyright and Attribution

When writing documentation or READMEs, paraphrase code comments and source behavior in your own words. Do not paste large verbatim blocks from the codebase into docs. Cite file paths and line numbers so the reader can inspect the source directly.

---

## Session Anti-Patterns

These are failure modes that have already cost time. Avoid them.

- Starting task work without reading the orientation set above.
- Treating audit docs as more trustworthy than current code or module READMEs.
- "Helpfully" fixing a bug that is not in scope.
- Batching multiple logical changes into one diff because they seem related.
- Updating a README to match code you have not actually read line by line.
- Asking the user for repo facts that are discoverable from the codebase or current docs.
- Silently reconciling contradictions instead of surfacing them.
- Rewriting a template or shared pattern because it feels improvable. Templates are locked; propose changes, do not make them casually.
