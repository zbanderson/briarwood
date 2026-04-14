from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from briarwood.execution.registry import ModuleSpec


class ExecutionPlan(BaseModel):
    """Dependency-aware execution plan for one routed Briarwood run."""

    model_config = ConfigDict(extra="forbid")

    selected_modules: list[str] = Field(default_factory=list)
    ordered_modules: list[str] = Field(default_factory=list)
    dependency_modules: list[str] = Field(default_factory=list)
    skipped_modules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def expand_dependencies(
    selected_modules: list[str],
    registry: dict[str, ModuleSpec],
) -> set[str]:
    """Expand a selected module set to include all transitive dependencies."""

    if not isinstance(registry, dict):
        raise TypeError("registry must be a dict[str, ModuleSpec].")

    expanded: set[str] = set()
    visiting: set[str] = set()
    visited: set[str] = set()

    def _visit(module_name: str) -> None:
        if module_name not in registry:
            raise ValueError(f"Unknown module name: {module_name}")
        if module_name in visited:
            return
        if module_name in visiting:
            cycle = " -> ".join(list(visiting) + [module_name])
            raise ValueError(f"Circular dependency detected: {cycle}")

        visiting.add(module_name)
        spec = registry[module_name]
        for dependency in spec.depends_on:
            _visit(dependency)
        visiting.remove(module_name)
        visited.add(module_name)
        expanded.add(module_name)

    for module_name in selected_modules:
        _visit(module_name)

    return expanded


def topological_sort_modules(
    module_names: set[str] | list[str],
    registry: dict[str, ModuleSpec],
) -> list[str]:
    """Return modules in dependency-safe execution order."""

    if not isinstance(registry, dict):
        raise TypeError("registry must be a dict[str, ModuleSpec].")

    target_modules = set(module_names)
    for module_name in target_modules:
        if module_name not in registry:
            raise ValueError(f"Unknown module name: {module_name}")

    ordered: list[str] = []
    temporary: set[str] = set()
    permanent: set[str] = set()

    def _visit(module_name: str, path: list[str]) -> None:
        if module_name in permanent:
            return
        if module_name in temporary:
            cycle = " -> ".join(path + [module_name])
            raise ValueError(f"Circular dependency detected: {cycle}")

        temporary.add(module_name)
        spec = registry[module_name]
        for dependency in spec.depends_on:
            if dependency in target_modules:
                _visit(dependency, path + [module_name])
        temporary.remove(module_name)
        permanent.add(module_name)
        ordered.append(module_name)

    for module_name in sorted(target_modules):
        _visit(module_name, [])

    return ordered


def build_execution_plan(
    selected_modules: list[str],
    registry: dict[str, ModuleSpec],
) -> ExecutionPlan:
    """Build a full execution plan from selected modules and a registry."""

    normalized_selected = [str(name) for name in selected_modules]
    if not normalized_selected:
        return ExecutionPlan(
            selected_modules=[],
            ordered_modules=[],
            dependency_modules=[],
            skipped_modules=sorted(registry.keys()),
            warnings=["No modules were selected for this run."],
        )

    expanded = expand_dependencies(normalized_selected, registry)
    ordered = topological_sort_modules(expanded, registry)
    selected_set = set(normalized_selected)
    dependency_modules = [name for name in ordered if name not in selected_set]
    skipped_modules = [name for name in sorted(registry.keys()) if name not in expanded]

    warnings: list[str] = []
    if dependency_modules:
        warnings.append(
            "Planner added dependency modules automatically: "
            + ", ".join(dependency_modules)
        )

    return ExecutionPlan(
        selected_modules=normalized_selected,
        ordered_modules=ordered,
        dependency_modules=dependency_modules,
        skipped_modules=skipped_modules,
        warnings=warnings,
    )


__all__ = [
    "ExecutionPlan",
    "build_execution_plan",
    "expand_dependencies",
    "topological_sort_modules",
]
