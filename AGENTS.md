# AGENTS.md

## Purpose

Briarwood is a residential real estate decision-intelligence platform.

The product is decision-first, not dashboard-first. Conversational or search-like input should route into structured analysis and then into a user-facing decision output. Prefer flows that answer "what should I do?" before exposing deeper evidence, tables, or diagnostics.

Relevant repo areas:

- `briarwood/router.py` and `briarwood/routing_schema.py`: routing contracts and rules
- `briarwood/orchestrator.py`: routing and synthesis orchestration boundary
- `briarwood/dash_app/`: orchestration, routing, and decision-first presentation
- `docs/current_docs_index.md`: preferred documentation starting point
- `briarwood/decision_engine.py` and `briarwood/decision_model/`: Briarwood-native decision and scoring logic
- `briarwood/modules/` and `briarwood/agents/`: deterministic analysis modules
- `briarwood/local_intelligence/`: structured extraction and synthesis boundary
- `tests/`: unit coverage, including decision-first views and agent behavior

## Architecture

Briarwood is a decision-intelligence platform for residential real estate.

The routing layer determines:

- intent
- analysis depth
- question focus

The execution layer determines:

- selected modules
- dependency modules
- execution order

Unified Intelligence synthesizes structured module outputs into the user-facing answer. It is a synthesis layer, not a calculator.

## V2 Execution Rules

- Do not run the full legacy engine by default for routed analyses when scoped execution is supported.
- Prefer module-scoped execution.
- Use legacy fallback only when required modules are not yet supported in the scoped registry.
- Use a registry + planner + executor pattern.

Every executable module must have:

- a clear input contract
- a clear output contract
- declared dependencies
- no hidden reliance on full-engine state

Question depth should dictate module scope. Keep intent, analysis depth, and question focus separate from execution planning.

## OpenAI Rules

OpenAI usage is allowed only for:

- intent parsing
- structured output synthesis

Do not use OpenAI for:

- valuation logic
- rent math
- scenario math
- comp selection
- risk scoring
- legal classification
- storage

All numeric and analytical logic must remain in Briarwood-native Python modules. LLM layers may classify or synthesize, but they must not become hidden calculators or decision engines.

## Engineering Rules

- Prefer small, reviewable changes.
- Keep logic explicit, readable, and typed.
- Use `pydantic` for contracts and structured boundaries where appropriate.
- Avoid hidden magic, implicit side effects, and over-abstraction.
- Wrap legacy logic before rewriting it.
- Add docstrings to public functions and core classes.
- Preserve backward compatibility where practical, especially around current Dash flows, saved-property artifacts, and report builders.
- Prefer current docs over historical docs when they conflict.
- Treat `AUDIT_REPORT.md`, `BRIARWOOD-AUDIT.md`, `UX-ASSESSMENT.md`, and `analysis/*.md` as historical context unless a current doc explicitly marks them as authoritative.

## Verification Rules

- Add or update focused unit tests for planner behavior.
- Add or update focused unit tests for dependency resolution.
- Add or update focused unit tests for executor behavior.
- Add or update focused unit tests for legacy fallback.
- Code should compile.
- Imports should resolve.
- Scoped execution paths should be directly testable.

For this repo, start with focused `unittest` runs such as:

```bash
python3 -m unittest tests.test_quick_decision
python3 -m unittest tests.test_decision_engine
python3 -m unittest discover -s tests
```

If no tests cover the touched planner or executor behavior, add focused unit tests rather than relying on manual UI checks alone.
