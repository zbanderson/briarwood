# CLAUDE.md — Briarwood Rules of Engagement

This file is read automatically at the start of every Claude Code session
operating in this repository. The rules below apply to every session,
every handoff, every task.

---

## Orient Yourself First

At the start of every session, before taking any user task:

1. Read this file (you are doing that now).
2. Read `.claude/skills/readme-discipline/SKILL.md` and execute Job 1
   (the drift check). Report findings if any.
3. Verify that the three authoritative docs exist and are readable:
   `ARCHITECTURE_CURRENT.md`, `GAP_ANALYSIS.md`, `TOOL_REGISTRY.md`.
4. Read `DECISIONS.md` and `ROADMAP.md` — in full, not skimmed. These
   are the chronological record of what we've decided and what's queued.
   Context for any current task lives in these two files.

Do not begin user task work until the above is complete. The cost of
orientation is minutes; the cost of skipping it is hours of rework
against stale assumptions.

---

## Authoritative Sources — In Priority Order

When information conflicts, the higher-priority source wins.

1. **The code itself.** What a function actually does at its cited line
   beats any description.
2. **READMEs.** Every module under `briarwood/` has a README that was
   written against actual source. Trust them over the audit docs.
3. **DECISIONS.md.** The project owner's calls on architecture, naming,
   and contracts.
4. **ARCHITECTURE_CURRENT.md / TOOL_REGISTRY.md / GAP_ANALYSIS.md.**
   The audit docs. Authoritative for system-level shape, but known to
   drift at the field-name level — any conflict with a README means
   the audit doc is wrong.
5. **Historical audit docs** (`AUDIT_REPORT.md`, `VERIFICATION_REPORT.md`,
   etc.). Reference only; not authoritative.

Briarwood is being built as an AI-native, "queryable" company. See
`design_doc.md` § 3.4 (AI-Native Principles) and `ROADMAP.md`
(staged buildout) for the load-bearing principles. Treat them as
constraints on any architectural decision — when a tradeoff is in front
of you, the side that honors more of those principles wins.

If you find a contradiction between sources, never silently reconcile.
Surface it to the user. Add an entry to DECISIONS.md if the resolution
requires judgment, or to ROADMAP.md if it's mechanical.

---

## README Discipline

At session startup, execute Job 1 from
`.claude/skills/readme-discipline/SKILL.md` (the drift check).

Before modifying any module under `briarwood/`, execute Job 2 (read the
module's README and its immediate dependencies' READMEs).

After any contract-level change to a module, execute Job 3 (update the
README's prose and append a dated changelog entry).

See the skill file for the full rules on what counts as a meaningful
change and when READMEs should NOT be updated.

---

## Writing Discipline for Handoffs

Briarwood development is organized into discrete handoffs. Each handoff
has an explicit prompt defining its scope. Within a handoff:

- Every change traces to a specific entry in ROADMAP.md, DECISIONS.md,
  or the handoff prompt itself. No drive-by fixes. If you see something
  broken that isn't in scope, add it to ROADMAP.md and keep moving.
- One logical change at a time. Do not batch renames, wrapper changes,
  or dependency updates across multiple modules in a single commit.
- Tests must pass after every change. If they don't, fix the test or
  fix the change — do not proceed with a red suite.
- Pauses in handoff prompts are mandatory. They exist for user review,
  not as suggestions.

---

## Contradictions, Drifts, and Bugs Found During Work

When you find something wrong while doing other work:

- **Contradiction with authoritative docs:** flag, do not reconcile.
  Add DECISIONS.md entry.
- **Mechanical drift** (field-name mismatch, undeclared dependency,
  naming collision): add to ROADMAP.md. Do not fix unless it's in
  the current handoff's scope.
- **Live production bug:** add to ROADMAP.md as high-priority. Do
  not fix unless it's in the current handoff's scope. A bug found
  during a documentation handoff does not become part of that handoff.
- **Opinion about code quality, style, or architecture:** keep it to
  yourself unless asked. Briarwood has a specific evolution arc; ad-hoc
  improvements fight that arc.

---

## Copyright and Attribution

When writing documentation or READMEs, paraphrase source comments in
your own words. Do not reproduce large verbatim blocks from the
codebase into READMEs. Cite file paths and line numbers so the reader
can go to the source.

---

## Session Anti-Patterns

These are failure modes that have cost time in the past. Avoid them.

- Starting code work without reading DECISIONS.md and ROADMAP.md first.
- "Helpfully" fixing a bug that isn't in scope.
- Batching multiple logical changes into one diff because they "feel
  related."
- Updating a README to match code you haven't actually read line by line.
- Skipping the plan-mode planning step because the task "seems simple."
- Silently reconciling a contradiction instead of surfacing it.
- Rewriting a template because you think it could be better — templates
  are locked; propose changes, don't make them.