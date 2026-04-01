from __future__ import annotations

import inspect

from briarwood.schemas import AnalysisModule, AnalysisReport, ModuleResult, PropertyInput


class AnalysisEngine:
    def __init__(self, modules: list[AnalysisModule]) -> None:
        module_names = [module.name for module in modules]
        duplicate_names = sorted({name for name in module_names if module_names.count(name) > 1})
        if duplicate_names:
            raise ValueError(
                "AnalysisEngine received duplicate module names: "
                + ", ".join(duplicate_names)
            )
        self._modules = {module.name: module for module in modules}

    def run_module(self, module_name: str, property_input: PropertyInput) -> ModuleResult:
        module = self._modules[module_name]
        return module.run(property_input)

    def run_all(self, property_input: PropertyInput) -> AnalysisReport:
        prior_results: dict[str, ModuleResult] = {}
        module_results: dict[str, ModuleResult] = {}
        for name, module in self._modules.items():
            sig = inspect.signature(module.run)
            if "prior_results" in sig.parameters:
                result = module.run(property_input, prior_results=prior_results)
            else:
                result = module.run(property_input)
            prior_results[name] = result
            module_results[name] = result
        return AnalysisReport(
            property_id=property_input.property_id,
            address=property_input.address,
            module_results=module_results,
            property_input=property_input,
        )
