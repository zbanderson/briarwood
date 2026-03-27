from __future__ import annotations

from briarwood.agents.scarcity.schemas import ScarcitySupportScore
from briarwood.agents.market_history.schemas import MarketValueHistoryOutput
from briarwood.agents.town_county.service import TownCountyOutlookResult
from briarwood.modules.market_value_history import get_market_value_history_payload
from briarwood.modules.scarcity_support import get_scarcity_support_payload
from briarwood.modules.town_county_outlook import get_town_county_outlook_payload
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


def get_town_county_outlook(report: AnalysisReport) -> TownCountyOutlookResult:
    return get_town_county_outlook_payload(report.get_module("town_county_outlook"))


def get_scarcity_support(report: AnalysisReport) -> ScarcitySupportScore:
    return get_scarcity_support_payload(report.get_module("scarcity_support"))


def get_market_value_history(report: AnalysisReport) -> MarketValueHistoryOutput:
    return get_market_value_history_payload(report.get_module("market_value_history"))
