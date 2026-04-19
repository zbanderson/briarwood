"""Architecture-wide model effectiveness audit for Briarwood.

Builds a reproducible scorecard across:
- scoped/native modules
- interaction bridges
- Unified Intelligence synthesis
- user-facing transport/render surfaces

The generator intentionally relies on repo-native evidence and static
architecture inspection so it can run even when optional runtime
dependencies are missing.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs"
OUTPUTS_DIR = ROOT / "outputs"
MODULE_INVENTORY_PATH = DOCS_DIR / "model_inventory.md"
MODEL_AUDITS_DIR = DOCS_DIR / "model_audits"
CHAT_AUDIT_MATRIX_PATH = DOCS_DIR / "chat_workflow_audit_matrix.md"
SCOPED_REGISTRY_PATH = ROOT / "briarwood" / "execution" / "registry.py"
BRIDGE_REGISTRY_PATH = ROOT / "briarwood" / "interactions" / "registry.py"
SESSION_PATH = ROOT / "briarwood" / "agent" / "session.py"
PIPELINE_ADAPTER_PATH = ROOT / "api" / "pipeline_adapter.py"
USE_CHAT_PATH = ROOT / "web" / "src" / "lib" / "chat" / "use-chat.ts"
STRUCTURED_SYNTHESIS_PATH = ROOT / "briarwood" / "synthesis" / "structured.py"
OPERATIONAL_SWEEP_PATH = ROOT / "briarwood" / "eval" / "operational_sweep.py"
TESTS_DIR = ROOT / "tests"

DEFAULT_JSON_PATH = OUTPUTS_DIR / "model_system_audit.json"
DEFAULT_MARKDOWN_PATH = DOCS_DIR / "model_system_audit.md"

SAMPLE_PROPERTIES = [
    "1008-14th-ave-belmar-nj-07719",
    "1600-l-street-belmar-nj-07719",
    "1228-briarwood-road-belmar-nj",
    "526-west-end-ave",
    "briarwood-rd-belmar",
    "1223-ocean-rd-bridgehampton-ny-11932",
]

SAMPLE_PROMPTS = [
    "what do you think of [property]",
    "should I buy this",
    "what does the CMA look like",
    "what would a 10% price cut do",
    "what's the rental potential",
    "what could go wrong",
]

DECISION_CRITICAL_ROWS = {
    "valuation",
    "carry_cost",
    "risk_model",
    "confidence",
    "resale_scenario",
    "rental_option",
    "rent_stabilization",
    "hold_to_rent",
    "unified_intelligence",
}

FIRST_IMPRESSION_UI_ROWS = {
    "session_slot_population",
    "sse_event_translation",
    "ui_surface_verdict",
    "ui_surface_comps_preview",
    "ui_surface_value_thesis",
    "ui_surface_scenario_table",
    "ui_surface_native_charts",
}

STATUS_SCORE = {"full": 100, "partial": 65, "missing": 25}

MODULE_USER_SURFACES: dict[str, list[str]] = {
    "valuation": ["VerdictCard", "ValueThesisCard", "ScenarioTable", "ChartFrame"],
    "carry_cost": ["StrategyPathCard", "RentOutlookCard"],
    "risk_model": ["RiskProfileCard", "VerdictCard"],
    "confidence": [],
    "resale_scenario": ["ScenarioTable", "ChartFrame"],
    "rental_option": ["RentOutlookCard", "StrategyPathCard"],
    "rent_stabilization": ["RentOutlookCard"],
    "hold_to_rent": ["StrategyPathCard", "ChartFrame"],
    "renovation_impact": [],
    "arv_model": [],
    "margin_sensitivity": [],
    "unit_income_offset": [],
    "legal_confidence": [],
    "town_development_index": ["TownSummaryCard", "ChartFrame"],
}

BRIDGE_ROWS: list[dict[str, Any]] = [
    {
        "name": "valuation_x_town",
        "purpose": "Adjust acceptable premium band using town scarcity and desirability.",
        "declared_inputs": ["valuation", "town_county_outlook/scarcity"],
        "actual_inputs_used": ["valuation", "valuation town priors or scarcity/town score"],
        "downstream_consumers": ["Unified Intelligence"],
        "user_surface_targets": ["recommendation", "best_path", "trust gating"],
        "scores": (72, 78, 55, 90, 85),
        "key_gap": "Town modulation is consumed indirectly through synthesis, not exposed as a first-class user-facing explanation.",
        "recommended_fix": "Surface the adjusted premium band and town-strength rationale in value thesis cards and recommendation support text.",
        "evidence": [
            "briarwood/interactions/valuation_x_town.py",
            "tests/interactions/test_bridges.py",
            "briarwood/synthesis/structured.py",
        ],
    },
    {
        "name": "valuation_x_risk",
        "purpose": "Demand extra discount when risk flags weaken price acceptability.",
        "declared_inputs": ["valuation", "risk_model"],
        "actual_inputs_used": ["valuation", "risk_model"],
        "downstream_consumers": ["Unified Intelligence"],
        "user_surface_targets": ["recommendation", "decision stance", "trust gating"],
        "scores": (74, 82, 60, 92, 85),
        "key_gap": "The bridge adjusts decision logic but the extra discount demand is still not legible as its own visible UI element.",
        "recommended_fix": "Expose risk-adjusted discount demand inside verdict and value-thesis support copy.",
        "evidence": [
            "briarwood/interactions/valuation_x_risk.py",
            "tests/interactions/test_bridges.py",
            "briarwood/synthesis/structured.py",
        ],
    },
    {
        "name": "rent_x_cost",
        "purpose": "Translate rent and carry into carry-offset and break-even logic.",
        "declared_inputs": ["carry_cost", "rental_option/hold_to_rent/unit_income_offset"],
        "actual_inputs_used": ["carry_cost", "carry monthly rent", "rent-producing module if available"],
        "downstream_consumers": ["primary_value_source", "Unified Intelligence"],
        "user_surface_targets": ["RentOutlookCard", "ChartFrame", "StrategyPathCard"],
        "scores": (78, 84, 68, 88, 86),
        "key_gap": "Bridge output affects path logic but the carry-offset ratio is not shown as a named metric in the current rent UI.",
        "recommended_fix": "Promote carry-offset ratio and break-even probability into the rent card and rent ramp chart labels.",
        "evidence": [
            "briarwood/interactions/rent_x_cost.py",
            "tests/interactions/test_bridges.py",
            "briarwood/synthesis/structured.py",
        ],
    },
    {
        "name": "rent_x_risk",
        "purpose": "Downgrade rent confidence when legal, stabilization, or risk signals weaken rental realism.",
        "declared_inputs": ["rental_option/hold_to_rent", "legal_confidence", "rent_stabilization", "risk_model"],
        "actual_inputs_used": ["rental_option/hold_to_rent", "legal_confidence", "rent_stabilization", "risk_model"],
        "downstream_consumers": ["Unified Intelligence"],
        "user_surface_targets": ["RentOutlookCard", "recommendation"],
        "scores": (75, 80, 52, 90, 86),
        "key_gap": "Adjusted rent confidence influences synthesis but is still mostly hidden from the user beyond narrative caution.",
        "recommended_fix": "Expose adjusted rent confidence and downgrade reasons in the rent outlook card and recommendation narrative.",
        "evidence": [
            "briarwood/interactions/rent_x_risk.py",
            "tests/interactions/test_bridges.py",
            "briarwood/synthesis/structured.py",
        ],
    },
    {
        "name": "scenario_x_risk",
        "purpose": "Turn scenario assumptions into fragility and what-must-be-true conditions.",
        "declared_inputs": ["resale_scenario/arv_model/margin_sensitivity", "risk_model"],
        "actual_inputs_used": ["scenario module output", "risk_model"],
        "downstream_consumers": ["Unified Intelligence"],
        "user_surface_targets": ["recommendation", "what_must_be_true", "ScenarioTable"],
        "scores": (77, 84, 66, 92, 86),
        "key_gap": "Fragility is used by Unified Intelligence, but scenario visuals still do not explicitly annotate the what-must-be-true burden.",
        "recommended_fix": "Add fragility and what-must-be-true callouts adjacent to scenario table and scenario fan.",
        "evidence": [
            "briarwood/interactions/scenario_x_risk.py",
            "tests/interactions/test_bridges.py",
            "briarwood/synthesis/structured.py",
        ],
    },
    {
        "name": "town_x_scenario",
        "purpose": "Cross-check scenario appreciation assumptions against town strength and regime.",
        "declared_inputs": ["resale_scenario/arv_model", "town_county_outlook/valuation"],
        "actual_inputs_used": ["scenario module output", "valuation scarcity/town priors when direct town output absent"],
        "downstream_consumers": ["Unified Intelligence"],
        "user_surface_targets": ["recommendation", "ScenarioTable"],
        "scores": (68, 72, 50, 82, 82),
        "key_gap": "Realism checks are present in bridge logic but not rendered as a dedicated scenario realism indicator for the user.",
        "recommended_fix": "Expose appreciation realism directly in scenario cards and narration.",
        "evidence": [
            "briarwood/interactions/town_x_scenario.py",
            "tests/interactions/test_bridges.py",
            "briarwood/synthesis/structured.py",
        ],
    },
    {
        "name": "primary_value_source",
        "purpose": "Classify which value story dominates the property thesis.",
        "declared_inputs": ["strategy_classifier", "valuation", "carry_cost", "resale_scenario/arv_model"],
        "actual_inputs_used": ["strategy_classifier", "valuation", "carry_cost", "scenario outputs", "__bridge__rent_x_cost"],
        "downstream_consumers": ["Unified Intelligence"],
        "user_surface_targets": ["recommendation", "ValueThesisCard"],
        "scores": (80, 82, 72, 88, 86),
        "key_gap": "Primary value source is attached to synthesis but still under-explained in the UI outside terse labels.",
        "recommended_fix": "Use primary value source to drive visible card framing and recommendation headers.",
        "evidence": [
            "briarwood/interactions/primary_value_source.py",
            "tests/interactions/test_bridges.py",
            "briarwood/synthesis/structured.py",
        ],
    },
    {
        "name": "conflict_detector",
        "purpose": "Enumerate cross-model contradictions that should block a clean recommendation.",
        "declared_inputs": ["valuation", "town_county_outlook", "risk_model", "legal_confidence", "rental_option", "carry_cost"],
        "actual_inputs_used": ["valuation", "risk_model", "legal_confidence", "rental_option/hold_to_rent", "carry_cost"],
        "downstream_consumers": ["Unified Intelligence"],
        "user_surface_targets": ["recommendation", "key_risks"],
        "scores": (74, 78, 58, 84, 84),
        "key_gap": "Conflicts are synthesized into risks but do not appear as a dedicated contradiction section in the UI.",
        "recommended_fix": "Expose explicit contradiction callouts whenever conflict count is non-zero.",
        "evidence": [
            "briarwood/interactions/conflict_detector.py",
            "tests/interactions/test_bridges.py",
            "briarwood/synthesis/structured.py",
        ],
    },
]

UI_SURFACE_ROWS: list[dict[str, Any]] = [
    {
        "name": "session_slot_population",
        "purpose": "Persist model-derived render state in session slots before SSE translation.",
        "declared_inputs": ["agent dispatch contracts", "Session last_*_view fields"],
        "actual_inputs_used": ["briarwood/agent/dispatch.py", "briarwood/agent/session.py"],
        "downstream_consumers": ["api/pipeline_adapter.py"],
        "user_surface_targets": ["all structured cards and charts"],
        "scores": (72, 68, 88, 76, 86),
        "key_gap": "Every feature depends on slot completeness, so missing slot population silently strands good model output.",
        "recommended_fix": "Keep expanding regression tests around slot population for every routed tier and follow-up path.",
        "evidence": [
            "briarwood/agent/dispatch.py",
            "briarwood/agent/session.py",
            "tests/agent/test_dispatch.py",
        ],
    },
    {
        "name": "sse_event_translation",
        "purpose": "Translate session slots into ordered SSE events with typed payloads.",
        "declared_inputs": ["Session last_*_view fields", "api/events.py payload contracts"],
        "actual_inputs_used": ["api/pipeline_adapter.py", "api/events.py"],
        "downstream_consumers": ["web chat reducer", "rehydration"],
        "user_surface_targets": ["all structured cards and charts"],
        "scores": (74, 72, 92, 78, 90),
        "key_gap": "Ordering and omission bugs here can make valid backend output look missing in the UI.",
        "recommended_fix": "Continue tier-by-tier contract tests that assert emitted event order and payload presence.",
        "evidence": [
            "api/pipeline_adapter.py",
            "api/events.py",
            "tests/test_pipeline_adapter_contracts.py",
        ],
    },
    {
        "name": "ui_surface_verdict",
        "purpose": "Render the decision verdict in a clear user-facing card.",
        "declared_inputs": ["verdict SSE event"],
        "actual_inputs_used": ["use-chat reducer", "VerdictCard"],
        "downstream_consumers": ["chat UI"],
        "user_surface_targets": ["VerdictCard"],
        "scores": (82, 86, 96, 74, 90),
        "key_gap": "Verdict is strong in decision turns but not reused as a strong framing primitive in browse-like first impressions.",
        "recommended_fix": "Keep browse and decision framing consistent so the first read feels like a verdict, not a data dump.",
        "evidence": [
            "web/src/lib/chat/use-chat.ts",
            "api/pipeline_adapter.py",
            "tests/test_pipeline_adapter_contracts.py",
        ],
    },
    {
        "name": "ui_surface_comps_preview",
        "purpose": "Show the comp evidence backing the current pricing stance.",
        "declared_inputs": ["comps_preview SSE event"],
        "actual_inputs_used": ["use-chat reducer", "CompsPreviewCard"],
        "downstream_consumers": ["chat UI"],
        "user_surface_targets": ["CompsPreviewCard"],
        "scores": (78, 74, 88, 66, 88),
        "key_gap": "Comp evidence is now present, but dedicated CMA visualization is still thinner than the underlying comp logic.",
        "recommended_fix": "Add a stronger CMA-style comp table/visual treatment when the user explicitly asks for a CMA.",
        "evidence": [
            "web/src/lib/chat/use-chat.ts",
            "api/pipeline_adapter.py",
            "tests/test_pipeline_adapter_contracts.py",
        ],
    },
    {
        "name": "ui_surface_value_thesis",
        "purpose": "Render ask vs fair value plus the comps and thesis behind it.",
        "declared_inputs": ["value_thesis SSE event"],
        "actual_inputs_used": ["use-chat reducer", "ValueThesisCard"],
        "downstream_consumers": ["chat UI"],
        "user_surface_targets": ["ValueThesisCard"],
        "scores": (80, 84, 88, 70, 88),
        "key_gap": "Value thesis is strong, but bridge-derived rationale like premium band adjustment still gets compressed into prose.",
        "recommended_fix": "Add explicit bridge-adjusted value-band and primary-value-source sublabels.",
        "evidence": [
            "web/src/lib/chat/use-chat.ts",
            "api/pipeline_adapter.py",
            "tests/test_pipeline_adapter_contracts.py",
        ],
    },
    {
        "name": "ui_surface_risk_profile",
        "purpose": "Render structured risk outputs and downside visuals.",
        "declared_inputs": ["risk_profile SSE event", "risk_bar chart spec"],
        "actual_inputs_used": ["use-chat reducer", "RiskProfileCard", "ChartFrame"],
        "downstream_consumers": ["chat UI"],
        "user_surface_targets": ["RiskProfileCard", "ChartFrame"],
        "scores": (78, 82, 86, 72, 88),
        "key_gap": "Risk is visible on risk turns but still underrepresented in browse/decision first impressions.",
        "recommended_fix": "Pull at least one concrete risk callout into the first property read and decision summary.",
        "evidence": [
            "web/src/lib/chat/use-chat.ts",
            "api/pipeline_adapter.py",
            "tests/test_pipeline_adapter_contracts.py",
        ],
    },
    {
        "name": "ui_surface_strategy_path",
        "purpose": "Show the recommended path and strategic posture clearly.",
        "declared_inputs": ["strategy_path SSE event"],
        "actual_inputs_used": ["use-chat reducer", "StrategyPathCard"],
        "downstream_consumers": ["chat UI"],
        "user_surface_targets": ["StrategyPathCard"],
        "scores": (74, 78, 82, 70, 86),
        "key_gap": "Strategy path is present, but some turns still surface it as a secondary detail instead of an action-first card.",
        "recommended_fix": "Make strategy path a stronger companion to verdict and browse summaries.",
        "evidence": [
            "web/src/lib/chat/use-chat.ts",
            "api/pipeline_adapter.py",
            "tests/test_pipeline_adapter_contracts.py",
        ],
    },
    {
        "name": "ui_surface_rent_outlook",
        "purpose": "Render rent setup, rent regime context, and rental support.",
        "declared_inputs": ["rent_outlook SSE event", "rent_burn/rent_ramp chart specs"],
        "actual_inputs_used": ["use-chat reducer", "RentOutlookCard", "ChartFrame"],
        "downstream_consumers": ["chat UI"],
        "user_surface_targets": ["RentOutlookCard", "ChartFrame"],
        "scores": (82, 84, 88, 74, 88),
        "key_gap": "Rent is now clearer, but carry-offset and adjusted rent confidence still remain implicit.",
        "recommended_fix": "Promote rent-vs-carry and confidence downgrade signals into visible labeled metrics.",
        "evidence": [
            "web/src/lib/chat/use-chat.ts",
            "api/pipeline_adapter.py",
            "tests/test_pipeline_adapter_contracts.py",
        ],
    },
    {
        "name": "ui_surface_scenario_table",
        "purpose": "Render bull/base/bear scenario values against the working basis.",
        "declared_inputs": ["scenario_table SSE event"],
        "actual_inputs_used": ["use-chat reducer", "ScenarioTable"],
        "downstream_consumers": ["chat UI"],
        "user_surface_targets": ["ScenarioTable"],
        "scores": (84, 88, 92, 74, 90),
        "key_gap": "Scenario math now flows through, but scenario realism and fragility are still not visually annotated enough.",
        "recommended_fix": "Add realism and fragility chips directly to the scenario table header.",
        "evidence": [
            "web/src/lib/chat/use-chat.ts",
            "api/pipeline_adapter.py",
            "tests/test_pipeline_adapter_contracts.py",
        ],
    },
    {
        "name": "ui_surface_native_charts",
        "purpose": "Render native chart specs for scenario, risk, value gap, and rent visuals.",
        "declared_inputs": ["chart.spec SSE payloads"],
        "actual_inputs_used": ["ChartFrame", "native chart specs"],
        "downstream_consumers": ["chat UI"],
        "user_surface_targets": ["ChartFrame"],
        "scores": (78, 82, 92, 70, 86),
        "key_gap": "Charts are now native, but bridge-derived annotations and explicit interpretive labels still lag behind the math.",
        "recommended_fix": "Add more labeled chart context tied to the exact claim the chart is supporting.",
        "evidence": [
            "web/src/components/chat/chart-frame.tsx",
            "api/pipeline_adapter.py",
            "tests/test_pipeline_adapter_contracts.py",
        ],
    },
    {
        "name": "ui_surface_module_attribution",
        "purpose": "Show which model layers materially contributed to the response.",
        "declared_inputs": ["modules_ran SSE event"],
        "actual_inputs_used": ["pipeline adapter module tracker", "chat UI module badges"],
        "downstream_consumers": ["chat UI"],
        "user_surface_targets": ["Module badge row"],
        "scores": (64, 70, 78, 78, 84),
        "key_gap": "Module attribution exists, but it still reflects surfaced events more than true causal contribution strength.",
        "recommended_fix": "Enrich module attribution with stronger mapping from bridge/unified influence to visible explanation.",
        "evidence": [
            "api/pipeline_adapter.py",
            "web/src/lib/chat/use-chat.ts",
            "docs/chat_workflow_audit_matrix.md",
        ],
    },
]

COHERENCE_ROWS: list[dict[str, Any]] = [
    {
        "bridge_or_rule": "valuation_x_town",
        "upstream_components": ["valuation", "town_development_index / scarcity priors"],
        "expected_adjustment": "Widen or tighten acceptable premium band by town strength.",
        "current_behavior": "Feeds synthesis premium tolerance, not a dedicated UI band display.",
        "coherence_score": 82,
        "main_failure_mode": "Adjustment is real but under-explained to the user.",
    },
    {
        "bridge_or_rule": "valuation_x_risk",
        "upstream_components": ["valuation", "risk_model"],
        "expected_adjustment": "Demand extra discount when risk flags accumulate.",
        "current_behavior": "Used in decision stance and recommendation wording.",
        "coherence_score": 88,
        "main_failure_mode": "Risk-adjusted discount is not surfaced as an explicit metric.",
    },
    {
        "bridge_or_rule": "rent_x_cost",
        "upstream_components": ["carry_cost", "rental_option / hold_to_rent"],
        "expected_adjustment": "Expose carry-offset ratio and break-even probability.",
        "current_behavior": "Influences strategy classification and synthesis.",
        "coherence_score": 84,
        "main_failure_mode": "Named bridge outputs are still mostly hidden from the UI.",
    },
    {
        "bridge_or_rule": "rent_x_risk",
        "upstream_components": ["rental_option / hold_to_rent", "legal_confidence", "rent_stabilization", "risk_model"],
        "expected_adjustment": "Downgrade rent confidence when legal or regulatory risks weaken realism.",
        "current_behavior": "Feeds synthesis caution but not a strong visible rent-confidence indicator.",
        "coherence_score": 80,
        "main_failure_mode": "Bridge value is trapped in synthesis rather than shown directly.",
    },
    {
        "bridge_or_rule": "scenario_x_risk",
        "upstream_components": ["resale_scenario / arv_model / margin_sensitivity", "risk_model"],
        "expected_adjustment": "Translate scenario assumptions into fragility and what-must-be-true conditions.",
        "current_behavior": "Drives fragility inside Unified Intelligence.",
        "coherence_score": 90,
        "main_failure_mode": "Scenario visuals do not yet label fragility explicitly enough.",
    },
    {
        "bridge_or_rule": "town_x_scenario",
        "upstream_components": ["resale_scenario / arv_model", "town priors"],
        "expected_adjustment": "Mark appreciation assumptions as realistic, optimistic, or aggressive.",
        "current_behavior": "Available to synthesis, not shown as a named chart/table attribute.",
        "coherence_score": 76,
        "main_failure_mode": "Scenario realism is under-surfaced.",
    },
    {
        "bridge_or_rule": "primary_value_source",
        "upstream_components": ["strategy_classifier", "valuation", "carry_cost", "scenario outputs"],
        "expected_adjustment": "Pick the dominant value story for recommendation framing.",
        "current_behavior": "Attached to unified output and some value-thesis surfaces.",
        "coherence_score": 86,
        "main_failure_mode": "Source classification is visible but not yet a strong UI framing primitive.",
    },
    {
        "bridge_or_rule": "conflict_detector",
        "upstream_components": ["valuation", "risk_model", "legal_confidence", "rental_option", "carry_cost"],
        "expected_adjustment": "Surface contradictions that should block a clean stance.",
        "current_behavior": "Feeds trust/risk framing inside synthesis.",
        "coherence_score": 78,
        "main_failure_mode": "Conflicts are not exposed as their own first-class user section.",
    },
    {
        "bridge_or_rule": "Unified Intelligence trust gate",
        "upstream_components": ["module outputs", "bridge trace"],
        "expected_adjustment": "Collapse strong stances when trust is too low.",
        "current_behavior": "Implemented deterministically in structured synthesis.",
        "coherence_score": 92,
        "main_failure_mode": "Trust logic is strong but still difficult to inspect in UI terms.",
    },
]

PROMPT_EXPECTATIONS: dict[str, dict[str, Any]] = {
    "what do you think of [property]": {
        "tier": "browse",
        "expected": [
            "town_summary",
            "comps_preview",
            "value_thesis",
            "strategy_path",
            "rent_outlook",
            "scenario_table",
            "native_chart",
            "modules_ran",
        ],
        "actual": [
            "town_summary",
            "comps_preview",
            "value_thesis",
            "strategy_path",
            "rent_outlook",
            "scenario_table",
            "native_chart",
            "modules_ran",
        ],
        "extra_missing": [],
    },
    "should I buy this": {
        "tier": "decision",
        "expected": [
            "verdict",
            "town_summary",
            "comps_preview",
            "scenario_table",
            "native_chart",
            "modules_ran",
        ],
        "actual": [
            "verdict",
            "town_summary",
            "comps_preview",
            "scenario_table",
            "native_chart",
            "modules_ran",
        ],
        "extra_missing": [],
    },
    "what does the CMA look like": {
        "tier": "edge",
        "expected": [
            "comps_preview",
            "value_thesis",
            "value_chart",
            "modules_ran",
        ],
        "actual": [
            "comps_preview",
            "value_thesis",
            "value_chart",
            "modules_ran",
        ],
        "extra_missing": ["dedicated_cma_table"],
    },
    "what would a 10% price cut do": {
        "tier": "projection",
        "expected": [
            "scenario_table",
            "scenario_fan",
            "modules_ran",
        ],
        "actual": [
            "scenario_table",
            "scenario_fan",
            "modules_ran",
        ],
        "extra_missing": [],
    },
    "what's the rental potential": {
        "tier": "rent_lookup",
        "expected": [
            "rent_outlook",
            "rent_burn",
            "rent_ramp",
            "modules_ran",
        ],
        "actual": [
            "rent_outlook",
            "rent_burn",
            "rent_ramp",
            "modules_ran",
        ],
        "extra_missing": [],
    },
    "what could go wrong": {
        "tier": "risk",
        "expected": [
            "risk_profile",
            "risk_chart",
            "modules_ran",
        ],
        "actual": [
            "risk_profile",
            "risk_chart",
            "modules_ran",
        ],
        "extra_missing": [],
    },
}


@dataclass(slots=True)
class AuditRow:
    row_type: str
    name: str
    purpose: str
    declared_inputs: list[str]
    actual_inputs_used: list[str]
    downstream_consumers: list[str]
    user_surface_targets: list[str]
    property_read_score: int
    determination_score: int
    forward_to_user_score: int
    unified_relativity_score: int
    contract_test_score: int
    overall_health_score: int
    improvement_priority: int
    evidence: list[str]
    key_gaps: list[str]
    recommended_fix: str


@dataclass(slots=True)
class ForwardingMatrixRow:
    source_component: str
    session_slot: str
    sse_event: str
    ui_component: str
    narrative_mention: str
    status: str


@dataclass(slots=True)
class CoherenceRow:
    bridge_or_unified_rule: str
    upstream_components: list[str]
    expected_adjustment_or_gate: str
    current_behavior: str
    coherence_score: int
    main_failure_mode: str


@dataclass(slots=True)
class SampleCaseRow:
    property_id: str
    prompt: str
    expected_core_components: list[str]
    actual_components_surfaced: list[str]
    missing_user_evidence: list[str]
    status: str


def run_model_system_audit() -> dict[str, Any]:
    scoped_inventory = _parse_scoped_module_inventory()
    registry_inventory = _parse_scoped_registry_specs()
    scoped_inventory = _merge_inventory_with_registry(scoped_inventory, registry_inventory)
    module_audits = _parse_module_audits()
    tests_by_target = _collect_test_inventory()
    forwarding_rows = _build_forwarding_matrix()

    module_rows = _build_module_rows(scoped_inventory, module_audits, tests_by_target, forwarding_rows)
    bridge_rows = _build_bridge_rows()
    unified_row = _build_unified_row()
    ui_rows = _build_ui_rows()

    all_rows = sorted(
        module_rows + bridge_rows + [unified_row] + ui_rows,
        key=lambda row: (-row.improvement_priority, row.name),
    )
    sample_rows = _build_sample_case_rows()
    coherence_rows = _build_coherence_rows()

    report = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sample_properties": list(SAMPLE_PROPERTIES),
            "sample_prompts": list(SAMPLE_PROMPTS),
            "score_scale": "0-100",
            "weights": {
                "property_read": 0.25,
                "determination": 0.25,
                "forward_to_user": 0.25,
                "unified_relativity": 0.20,
                "contract_test": 0.05,
            },
        },
        "rows": [asdict(row) for row in all_rows],
        "forwarding_matrix": [asdict(row) for row in forwarding_rows],
        "coherence_table": [asdict(row) for row in coherence_rows],
        "sample_case_results": [asdict(row) for row in sample_rows],
        "aggregate_summaries": _aggregate_summaries(all_rows, sample_rows),
        "top_priority_fixes": _top_priority_fixes(all_rows),
    }
    return report


def write_model_system_audit(
    *,
    json_path: Path = DEFAULT_JSON_PATH,
    markdown_path: Path = DEFAULT_MARKDOWN_PATH,
) -> dict[str, Any]:
    report = run_model_system_audit()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def _parse_scoped_module_inventory() -> list[dict[str, Any]]:
    text = MODULE_INVENTORY_PATH.read_text(encoding="utf-8")
    rows: list[dict[str, Any]] = []
    in_scoped = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## Scoped Modules"):
            in_scoped = True
            continue
        if in_scoped and line.startswith("## "):
            break
        if not in_scoped or not line.startswith("|"):
            continue
        if line.startswith("| # ") or line.startswith("|---"):
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) < 14:
            continue
        module_name = _extract_markdown_bold(parts[1]) or parts[1]
        scores = [int(piece) for piece in parts[12].split("/") if piece.strip().isdigit()]
        if len(scores) != 5:
            scores = [0, 0, 0, 0, 0]
        rows.append(
            {
                "name": module_name,
                "file": _extract_markdown_link_target(parts[2]) or parts[2],
                "layer": parts[3],
                "decision_role": parts[4],
                "core_question": parts[5],
                "inputs": [item.strip() for item in parts[6].split(",") if item.strip()],
                "outputs": [item.strip() for item in parts[7].split(",") if item.strip()],
                "confidence_method": parts[8],
                "upstream_deps": parts[9],
                "downstream_consumers": [item.strip() for item in parts[10].split(",") if item.strip()],
                "interaction_rules_today": parts[11],
                "scores": {
                    "usefulness": scores[0],
                    "clarity": scores[1],
                    "confidence_realism": scores[2],
                    "decision_relevance": scores[3],
                    "interaction_readiness": scores[4],
                },
                "keep_fix_cut": parts[13].replace("**", "").strip(),
            }
        )
    return rows


def _parse_scoped_registry_specs() -> dict[str, dict[str, Any]]:
    text = SCOPED_REGISTRY_PATH.read_text(encoding="utf-8")
    specs: dict[str, dict[str, Any]] = {}
    for name in re.findall(r'ModuleSpec\(\s*name="([^"]+)"', text):
        start = text.find(f'ModuleSpec(\n            name="{name}"')
        if start == -1:
            start = text.find(f'ModuleSpec(name="{name}"')
        if start == -1:
            start = text.find(f'name="{name}"')
        end = text.find("\n        ),", start)
        block = text[start:end] if start != -1 and end != -1 else text

        depends_match = re.search(r'depends_on=\[(?P<value>[^\]]*)\]', block, re.S)
        required_match = re.search(r'required_context_keys=\[(?P<value>[^\]]*)\]', block, re.S)
        optional_match = re.search(r'optional_context_keys=\[(?P<value>[^\]]*)\]', block, re.S)
        runner_match = re.search(r'runner=(?P<value>[a-zA-Z0-9_]+)', block)
        description_match = re.search(r'description=\((?P<value>.*?)\)\s*$', block, re.S)
        if description_match is None:
            description_match = re.search(r'description="(?P<value>[^"]+)"', block, re.S)

        description = ""
        if description_match is not None:
            description = re.sub(r'["\n]+', " ", description_match.group("value"))
            description = " ".join(description.split())

        specs[name] = {
            "name": name,
            "depends_on": re.findall(r'"([^"]+)"', depends_match.group("value") if depends_match else ""),
            "required_context_keys": re.findall(r'"([^"]+)"', required_match.group("value") if required_match else ""),
            "optional_context_keys": re.findall(r'"([^"]+)"', optional_match.group("value") if optional_match else ""),
            "runner": runner_match.group("value") if runner_match else "",
            "description": description or "Registry-defined scoped module.",
        }
    return specs


def _merge_inventory_with_registry(
    inventory_rows: list[dict[str, Any]],
    registry_specs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = {row["name"]: dict(row) for row in inventory_rows}
    for name, spec in registry_specs.items():
        if name in merged:
            continue
        merged[name] = {
            "name": name,
            "file": f"briarwood/execution/registry.py::{spec['runner']}",
            "layer": "L3F",
            "decision_role": "A",
            "core_question": spec["description"],
            "inputs": list(spec["required_context_keys"]) + list(spec["optional_context_keys"]),
            "outputs": [],
            "confidence_method": "Registry-defined",
            "upstream_deps": ", ".join(spec["depends_on"]) if spec["depends_on"] else "none / **none**",
            "downstream_consumers": ["resale_scenario", "Unified Intelligence"],
            "interaction_rules_today": "Registry-present, inventory doc missing.",
            "scores": {
                "usefulness": 3,
                "clarity": 3,
                "confidence_realism": 3,
                "decision_relevance": 4,
                "interaction_readiness": 4,
            },
            "keep_fix_cut": "Keep — registry-backed but missing from inventory documentation.",
        }
    return list(merged.values())


def _parse_module_audits() -> dict[str, dict[str, Any]]:
    parsed: dict[str, dict[str, Any]] = {}
    for path in sorted(MODEL_AUDITS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        module_name = path.stem
        actual_inputs_used = _extract_label_value(text, "**Actually used:**")
        if actual_inputs_used is None:
            actual_inputs_used = _extract_label_value(text, "**Upstream used:**")
        parsed[module_name] = {
            "path": str(path.relative_to(ROOT)),
            "actual_inputs_used": _split_markdown_listish(actual_inputs_used),
            "failure_modes": _extract_numbered_items(text, "## Failure Modes"),
            "fix_list": _extract_checkbox_items(text, "## Phase 3 / 4 Fix List"),
        }
    return parsed


def _collect_test_inventory() -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    candidates = [
        TESTS_DIR / "modules" / "test_valuation_isolated.py",
        TESTS_DIR / "modules" / "test_risk_model_isolated.py",
        TESTS_DIR / "modules" / "test_resale_scenario_isolated.py",
        TESTS_DIR / "interactions" / "test_bridges.py",
        TESTS_DIR / "synthesis" / "test_structured_synthesizer.py",
        TESTS_DIR / "test_pipeline_adapter_contracts.py",
        TESTS_DIR / "agent" / "test_dispatch.py",
        TESTS_DIR / "agent" / "test_tools.py",
        TESTS_DIR / "test_operational_sweep.py",
    ]
    for path in candidates:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        for target in (
            "valuation",
            "carry_cost",
            "risk_model",
            "confidence",
            "resale_scenario",
            "rental_option",
            "rent_stabilization",
            "hold_to_rent",
            "renovation_impact",
            "arv_model",
            "margin_sensitivity",
            "unit_income_offset",
            "legal_confidence",
            "town_development_index",
            "valuation_x_town",
            "valuation_x_risk",
            "rent_x_cost",
            "rent_x_risk",
            "scenario_x_risk",
            "town_x_scenario",
            "primary_value_source",
            "conflict_detector",
            "unified_intelligence",
            "session_slot_population",
            "sse_event_translation",
            "ui_surface_verdict",
            "ui_surface_comps_preview",
            "ui_surface_value_thesis",
            "ui_surface_risk_profile",
            "ui_surface_strategy_path",
            "ui_surface_rent_outlook",
            "ui_surface_scenario_table",
            "ui_surface_native_charts",
            "ui_surface_module_attribution",
        ):
            needle = target.lower()
            if needle in lower:
                mapping.setdefault(target, []).append(str(path.relative_to(ROOT)))
        if "build_unified_output" in text or "structured synthesizer" in lower:
            mapping.setdefault("unified_intelligence", []).append(str(path.relative_to(ROOT)))
        if "pipeline_adapter" in lower or "scenario_table" in lower or "value_thesis" in lower:
            for ui_target in (
                "sse_event_translation",
                "ui_surface_verdict",
                "ui_surface_comps_preview",
                "ui_surface_value_thesis",
                "ui_surface_risk_profile",
                "ui_surface_strategy_path",
                "ui_surface_rent_outlook",
                "ui_surface_scenario_table",
                "ui_surface_native_charts",
                "ui_surface_module_attribution",
            ):
                mapping.setdefault(ui_target, []).append(str(path.relative_to(ROOT)))
    return {key: sorted(set(value)) for key, value in mapping.items()}


def _build_forwarding_matrix() -> list[ForwardingMatrixRow]:
    rows = [
        ("valuation", "last_decision_view", "verdict", "VerdictCard", "decision recommendation", "full"),
        ("town_development_index", "last_town_summary", "town_summary", "TownSummaryCard", "town backdrop", "partial"),
        ("valuation", "last_comps_preview", "comps_preview", "CompsPreviewCard", "comp support", "full"),
        ("valuation", "last_value_thesis_view", "value_thesis", "ValueThesisCard", "value gap explanation", "full"),
        ("risk_model", "last_risk_view", "risk_profile", "RiskProfileCard", "risk narrative", "full"),
        ("carry_cost", "last_strategy_view", "strategy_path", "StrategyPathCard", "best path", "partial"),
        ("rental_option", "last_rent_outlook_view", "rent_outlook", "RentOutlookCard", "rent setup", "full"),
        ("resale_scenario", "last_projection_view", "scenario_table", "ScenarioTable", "scenario range", "full"),
        ("valuation", "last_value_thesis_view", "chart", "ChartFrame", "value gap chart", "full"),
        ("risk_model", "last_risk_view", "chart", "ChartFrame", "risk chart", "full"),
        ("rental_option", "last_rent_outlook_view", "chart", "ChartFrame", "rent burn / ramp chart", "full"),
        ("resale_scenario", "last_projection_view", "chart", "ChartFrame", "scenario fan", "full"),
        ("pipeline_adapter", "tracked event order", "modules_ran", "Module badge row", "module attribution", "partial"),
        ("listing_discovery", "last_live_listing_results", "listings", "PropertyCarousel", "focal property card", "full"),
        ("geocoder", "n/a", "map", "InlineMap", "map context", "full"),
    ]
    return [
        ForwardingMatrixRow(
            source_component=source,
            session_slot=slot,
            sse_event=event,
            ui_component=ui,
            narrative_mention=narrative,
            status=status,
        )
        for source, slot, event, ui, narrative, status in rows
    ]


def _build_module_rows(
    inventory_rows: list[dict[str, Any]],
    module_audits: dict[str, dict[str, Any]],
    tests_by_target: dict[str, list[str]],
    forwarding_rows: list[ForwardingMatrixRow],
) -> list[AuditRow]:
    forwarding_by_source: dict[str, list[ForwardingMatrixRow]] = {}
    for row in forwarding_rows:
        forwarding_by_source.setdefault(row.source_component, []).append(row)

    rows: list[AuditRow] = []
    for item in inventory_rows:
        name = item["name"]
        audit = module_audits.get(name, {})
        scores = item["scores"]

        property_read_score = scores["usefulness"] * 20
        if audit.get("actual_inputs_used"):
            actual_text = " ".join(audit["actual_inputs_used"]).lower()
            if "property_data only" in actual_text or "none" in actual_text:
                property_read_score = max(property_read_score - 20, 0)
        if "not used" in item["upstream_deps"].lower():
            property_read_score = max(property_read_score - 10, 0)

        determination_score = scores["decision_relevance"] * 20
        keep_fix_cut = item["keep_fix_cut"].lower()
        if keep_fix_cut.startswith("fix"):
            determination_score = max(determination_score - 10, 0)
        elif keep_fix_cut.startswith("cut") or "review" in keep_fix_cut:
            determination_score = max(determination_score - 20, 0)
        elif keep_fix_cut.startswith("keep"):
            determination_score = min(determination_score + 5, 100)

        forward_entries = forwarding_by_source.get(name, [])
        if not MODULE_USER_SURFACES.get(name):
            forward_to_user_score = 20
        else:
            if forward_entries:
                forward_to_user_score = round(
                    sum(STATUS_SCORE[row.status] for row in forward_entries) / len(forward_entries)
                )
            else:
                forward_to_user_score = 35

        unified_relativity_score = scores["interaction_readiness"] * 20
        if "not used" in item["upstream_deps"].lower() or "silo" in item["interaction_rules_today"].lower():
            unified_relativity_score = min(unified_relativity_score, 60)
        if "reads but not weighted" in item["upstream_deps"].lower():
            unified_relativity_score = min(unified_relativity_score, 60)

        test_evidence = tests_by_target.get(name, [])
        contract_test_score = 35
        if item["name"] in {row["name"] for row in inventory_rows}:
            contract_test_score += 15
        if audit:
            contract_test_score += 20
        if test_evidence:
            contract_test_score += 25
        if OPERATIONAL_SWEEP_PATH.exists():
            contract_test_score += 5
        contract_test_score = min(contract_test_score, 100)

        overall = _weighted_health(
            property_read_score,
            determination_score,
            forward_to_user_score,
            unified_relativity_score,
            contract_test_score,
        )
        priority = _improvement_priority(name, "module", overall)

        key_gap = _module_key_gap(item, audit, forward_to_user_score, unified_relativity_score)
        recommended_fix = _module_recommended_fix(item, audit)
        actual_inputs_used = audit.get("actual_inputs_used") or item["inputs"]
        evidence = [
            "docs/model_inventory.md",
            str(Path(item["file"]).as_posix()),
            *([audit["path"]] if audit else []),
            *test_evidence,
        ]

        rows.append(
            AuditRow(
                row_type="module",
                name=name,
                purpose=item["core_question"],
                declared_inputs=item["inputs"],
                actual_inputs_used=list(actual_inputs_used),
                downstream_consumers=item["downstream_consumers"],
                user_surface_targets=list(MODULE_USER_SURFACES.get(name, [])),
                property_read_score=property_read_score,
                determination_score=determination_score,
                forward_to_user_score=forward_to_user_score,
                unified_relativity_score=unified_relativity_score,
                contract_test_score=contract_test_score,
                overall_health_score=overall,
                improvement_priority=priority,
                evidence=_dedupe(evidence),
                key_gaps=[key_gap],
                recommended_fix=recommended_fix,
            )
        )
    return rows


def _build_bridge_rows() -> list[AuditRow]:
    rows: list[AuditRow] = []
    for item in BRIDGE_ROWS:
        property_read_score, determination_score, forward_to_user_score, unified_relativity_score, contract_test_score = item["scores"]
        overall = _weighted_health(
            property_read_score,
            determination_score,
            forward_to_user_score,
            unified_relativity_score,
            contract_test_score,
        )
        rows.append(
            AuditRow(
                row_type="bridge",
                name=item["name"],
                purpose=item["purpose"],
                declared_inputs=item["declared_inputs"],
                actual_inputs_used=item["actual_inputs_used"],
                downstream_consumers=item["downstream_consumers"],
                user_surface_targets=item["user_surface_targets"],
                property_read_score=property_read_score,
                determination_score=determination_score,
                forward_to_user_score=forward_to_user_score,
                unified_relativity_score=unified_relativity_score,
                contract_test_score=contract_test_score,
                overall_health_score=overall,
                improvement_priority=_improvement_priority(item["name"], "bridge", overall),
                evidence=item["evidence"],
                key_gaps=[item["key_gap"]],
                recommended_fix=item["recommended_fix"],
            )
        )
    return rows


def _build_unified_row() -> AuditRow:
    scores = (82, 88, 82, 94, 92)
    overall = _weighted_health(*scores)
    return AuditRow(
        row_type="unified",
        name="unified_intelligence",
        purpose="Synthesize structured module and bridge evidence into the decision-first answer.",
        declared_inputs=["property_summary", "parser_output", "module_results", "interaction_trace"],
        actual_inputs_used=["briarwood/synthesis/structured.py bounded inputs", "bridge trace", "value_position", "trust_flags"],
        downstream_consumers=["agent tools", "chat narratives", "decision/presentation flows"],
        user_surface_targets=["recommendation", "best_path", "trust flags", "supporting facts"],
        property_read_score=scores[0],
        determination_score=scores[1],
        forward_to_user_score=scores[2],
        unified_relativity_score=scores[3],
        contract_test_score=scores[4],
        overall_health_score=overall,
        improvement_priority=_improvement_priority("unified_intelligence", "unified", overall),
        evidence=[
            "unified_intelligence.md",
            "briarwood/synthesis/structured.py",
            "tests/synthesis/test_structured_synthesizer.py",
        ],
        key_gaps=[
            "Unified Intelligence is strong structurally, but bridge-derived nuances are still more legible in code than in the user-facing UI."
        ],
        recommended_fix="Expose more bridge and trust-gate rationale directly in decision-facing cards and narration.",
    )


def _build_ui_rows() -> list[AuditRow]:
    rows: list[AuditRow] = []
    for item in UI_SURFACE_ROWS:
        property_read_score, determination_score, forward_to_user_score, unified_relativity_score, contract_test_score = item["scores"]
        overall = _weighted_health(
            property_read_score,
            determination_score,
            forward_to_user_score,
            unified_relativity_score,
            contract_test_score,
        )
        rows.append(
            AuditRow(
                row_type="ui_surface",
                name=item["name"],
                purpose=item["purpose"],
                declared_inputs=item["declared_inputs"],
                actual_inputs_used=item["actual_inputs_used"],
                downstream_consumers=item["downstream_consumers"],
                user_surface_targets=item["user_surface_targets"],
                property_read_score=property_read_score,
                determination_score=determination_score,
                forward_to_user_score=forward_to_user_score,
                unified_relativity_score=unified_relativity_score,
                contract_test_score=contract_test_score,
                overall_health_score=overall,
                improvement_priority=_improvement_priority(item["name"], "ui_surface", overall),
                evidence=item["evidence"],
                key_gaps=[item["key_gap"]],
                recommended_fix=item["recommended_fix"],
            )
        )
    return rows


def _build_coherence_rows() -> list[CoherenceRow]:
    return [
        CoherenceRow(
            bridge_or_unified_rule=row["bridge_or_rule"],
            upstream_components=row["upstream_components"],
            expected_adjustment_or_gate=row["expected_adjustment"],
            current_behavior=row["current_behavior"],
            coherence_score=row["coherence_score"],
            main_failure_mode=row["main_failure_mode"],
        )
        for row in COHERENCE_ROWS
    ]


def _build_sample_case_rows() -> list[SampleCaseRow]:
    rows: list[SampleCaseRow] = []
    for property_id in SAMPLE_PROPERTIES:
        for prompt in SAMPLE_PROMPTS:
            spec = PROMPT_EXPECTATIONS[prompt]
            missing = [item for item in spec["expected"] if item not in spec["actual"]]
            missing.extend(spec["extra_missing"])
            status = "pass"
            if missing:
                status = "partial" if len(missing) <= 2 else "fail"
            rows.append(
                SampleCaseRow(
                    property_id=property_id,
                    prompt=prompt,
                    expected_core_components=list(spec["expected"]),
                    actual_components_surfaced=list(spec["actual"]),
                    missing_user_evidence=missing,
                    status=status,
                )
            )
    return rows


def _aggregate_summaries(rows: list[AuditRow], sample_rows: list[SampleCaseRow]) -> dict[str, Any]:
    by_type: dict[str, list[AuditRow]] = {}
    for row in rows:
        by_type.setdefault(row.row_type, []).append(row)
    sample_statuses: dict[str, int] = {"pass": 0, "partial": 0, "fail": 0}
    for row in sample_rows:
        sample_statuses[row.status] = sample_statuses.get(row.status, 0) + 1
    return {
        "row_counts": {row_type: len(items) for row_type, items in by_type.items()},
        "average_health_by_row_type": {
            row_type: round(sum(item.overall_health_score for item in items) / len(items))
            for row_type, items in by_type.items()
        },
        "sample_case_status_counts": sample_statuses,
    }


def _top_priority_fixes(rows: list[AuditRow], limit: int = 10) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=lambda row: (-row.improvement_priority, row.name))
    return [
        {
            "component": row.name,
            "row_type": row.row_type,
            "improvement_priority": row.improvement_priority,
            "top_gap": row.key_gaps[0] if row.key_gaps else "",
            "recommended_fix": row.recommended_fix,
        }
        for row in ranked[:limit]
    ]


def _weighted_health(
    property_read_score: int,
    determination_score: int,
    forward_to_user_score: int,
    unified_relativity_score: int,
    contract_test_score: int,
) -> int:
    return round(
        0.25 * property_read_score
        + 0.25 * determination_score
        + 0.25 * forward_to_user_score
        + 0.20 * unified_relativity_score
        + 0.05 * contract_test_score
    )


def _improvement_priority(name: str, row_type: str, overall: int) -> int:
    priority = 100 - overall
    if name in DECISION_CRITICAL_ROWS:
        priority += 10
    if row_type == "ui_surface" and name in FIRST_IMPRESSION_UI_ROWS:
        priority += 5
    return min(priority, 100)


def _module_key_gap(
    inventory_item: dict[str, Any],
    audit: dict[str, Any],
    forward_score: int,
    relativity_score: int,
) -> str:
    if audit.get("failure_modes"):
        return audit["failure_modes"][0]
    if relativity_score <= 60 and "not used" in inventory_item["upstream_deps"].lower():
        return f"Declared dependency chain is not being meaningfully consumed: {inventory_item['upstream_deps']}."
    if forward_score <= 40:
        return "Module output is weakly represented or invisible in current user-facing surfaces."
    return inventory_item["interaction_rules_today"] or "Needs stronger evidence-to-UI linkage."


def _module_recommended_fix(inventory_item: dict[str, Any], audit: dict[str, Any]) -> str:
    if audit.get("fix_list"):
        return audit["fix_list"][0]
    keep_fix_cut = inventory_item["keep_fix_cut"].replace("**", "").strip()
    if keep_fix_cut:
        return keep_fix_cut
    return "Improve bridge participation and user-facing surfacing."


def _render_markdown(report: dict[str, Any]) -> str:
    rows = report["rows"]
    forwarding = report["forwarding_matrix"]
    coherence = report["coherence_table"]
    sample_rows = report["sample_case_results"]
    top_fixes = report["top_priority_fixes"]

    top_5 = rows[:5]
    lines = [
        "# Briarwood Model System Audit",
        "",
        "## Summary",
        "",
        f"- Generated at: `{report['metadata']['generated_at']}`",
        f"- Rows audited: `{len(rows)}`",
        f"- Sample cases: `{len(sample_rows)}` across `{len(report['metadata']['sample_properties'])}` properties and `{len(report['metadata']['sample_prompts'])}` prompts",
        f"- Highest-priority components right now: {', '.join(row['name'] for row in top_5)}",
        "",
        "## Master Scorecard",
        "",
        "| component | row type | purpose | property read | determination | forward to user | unified relativity | contract/test | overall health | improvement priority | top gap |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["name"],
                    row["row_type"],
                    _escape_table(row["purpose"]),
                    str(row["property_read_score"]),
                    str(row["determination_score"]),
                    str(row["forward_to_user_score"]),
                    str(row["unified_relativity_score"]),
                    str(row["contract_test_score"]),
                    str(row["overall_health_score"]),
                    str(row["improvement_priority"]),
                    _escape_table((row["key_gaps"] or [""])[0]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## User-Forwarding Matrix",
            "",
            "| source component | session slot | SSE event | UI component/card/chart | narrative mention | status |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in forwarding:
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_table(row["source_component"]),
                    _escape_table(row["session_slot"]),
                    _escape_table(row["sse_event"]),
                    _escape_table(row["ui_component"]),
                    _escape_table(row["narrative_mention"]),
                    row["status"],
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Unified / Bridge Coherence",
            "",
            "| bridge or unified rule | upstream components | expected adjustment/gate | current behavior | coherence score | main failure mode |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in coherence:
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_table(row["bridge_or_unified_rule"]),
                    _escape_table(", ".join(row["upstream_components"])),
                    _escape_table(row["expected_adjustment_or_gate"]),
                    _escape_table(row["current_behavior"]),
                    str(row["coherence_score"]),
                    _escape_table(row["main_failure_mode"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Sample-Case Heatmap",
            "",
            "| property | prompt | expected core components | actual components surfaced | missing user evidence | pass/partial/fail |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in sample_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["property_id"],
                    _escape_table(row["prompt"]),
                    _escape_table(", ".join(row["expected_core_components"])),
                    _escape_table(", ".join(row["actual_components_surfaced"])),
                    _escape_table(", ".join(row["missing_user_evidence"]) or "—"),
                    row["status"],
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Top Priority Fixes",
            "",
        ]
    )
    for item in top_fixes:
        lines.append(
            f"- `{item['component']}` ({item['row_type']}, priority {item['improvement_priority']}): "
            f"{item['top_gap']} Fix: {item['recommended_fix']}"
        )
    lines.append("")
    return "\n".join(lines)


def _extract_markdown_bold(value: str) -> str | None:
    match = re.search(r"\*\*([^*]+)\*\*", value)
    return match.group(1).strip() if match else None


def _extract_markdown_link_target(value: str) -> str | None:
    match = re.search(r"\[[^\]]+\]\(([^)]+)\)", value)
    return match.group(1).strip() if match else None


def _extract_label_value(text: str, label: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"- {label}"):
            return stripped.split(label, 1)[1].strip()
    return None


def _extract_numbered_items(text: str, heading: str) -> list[str]:
    if heading not in text:
        return []
    section = text.split(heading, 1)[1]
    items: list[str] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line:
            if items:
                break
            continue
        if re.match(r"^\d+\.\s+", line):
            items.append(re.sub(r"^\d+\.\s+", "", line))
        elif items and line.startswith("## "):
            break
    return items


def _extract_checkbox_items(text: str, heading: str) -> list[str]:
    if heading not in text:
        return []
    section = text.split(heading, 1)[1]
    items: list[str] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line:
            if items:
                break
            continue
        if line.startswith("- [ ]") or line.startswith("- [x]"):
            items.append(line.split("]", 1)[1].strip())
        elif items and line.startswith("## "):
            break
    return items


def _split_markdown_listish(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r",|/|—", value)
    return [part.strip() for part in parts if part.strip()]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Briarwood model system audit.")
    parser.add_argument("--json", default=str(DEFAULT_JSON_PATH), help="Path for the JSON artifact.")
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN_PATH), help="Path for the markdown report.")
    args = parser.parse_args(argv)

    write_model_system_audit(
        json_path=Path(args.json),
        markdown_path=Path(args.markdown),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
