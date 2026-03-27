from __future__ import annotations

from briarwood.schemas import AnalysisReport, ScenarioOutput, ValuationOutput


def get_valuation_output(report: AnalysisReport) -> ValuationOutput:
    module = report.get_module("cost_valuation")
    if not isinstance(module.payload, ValuationOutput):
        raise TypeError("cost_valuation module payload is not a ValuationOutput")
    return module.payload


def get_scenario_output(report: AnalysisReport) -> ScenarioOutput:
    module = report.get_module("bull_base_bear")
    if not isinstance(module.payload, ScenarioOutput):
        raise TypeError("bull_base_bear module payload is not a ScenarioOutput")
    return module.payload
