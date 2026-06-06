"""Configuration parser for DevOps pipeline definitions.

Parses and validates pipeline configuration files in YAML-like
dictionary format for CI/CD workflows.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineStage:
    """A single stage in a CI/CD pipeline."""

    name: str
    commands: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    timeout: int = 300
    allow_failure: bool = False

    def validate(self) -> list[str]:
        """Validate stage configuration. Returns list of errors."""
        errors = []
        if not self.name:
            errors.append("Stage name cannot be empty")
        if not self.name.replace("-", "").replace("_", "").isalnum():
            errors.append(
                f"Stage name '{self.name}' contains invalid characters"
            )
        if not self.commands:
            errors.append(f"Stage '{self.name}' has no commands")
        if self.timeout <= 0:
            errors.append(
                f"Stage '{self.name}' has invalid timeout: {self.timeout}"
            )
        return errors


@dataclass
class PipelineConfig:
    """Full pipeline configuration."""

    name: str
    stages: list[PipelineStage] = field(default_factory=list)
    global_env: dict[str, str] = field(default_factory=dict)
    trigger_branches: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        """Validate entire pipeline config. Returns list of errors."""
        errors = []
        if not self.name:
            errors.append("Pipeline name cannot be empty")
        if not self.stages:
            errors.append("Pipeline must have at least one stage")

        stage_names = set()
        for stage in self.stages:
            if stage.name in stage_names:
                errors.append(f"Duplicate stage name: '{stage.name}'")
            stage_names.add(stage.name)
            errors.extend(stage.validate())

        for stage in self.stages:
            for dep in stage.depends_on:
                if dep not in stage_names:
                    errors.append(
                        f"Stage '{stage.name}' depends on "
                        f"unknown stage '{dep}'"
                    )

        return errors

    def get_execution_order(self) -> list[list[str]]:
        """Determine stage execution order respecting dependencies.

        Returns list of lists (parallel groups).
        Raises ValueError if circular dependencies are detected.
        """
        if not self.stages:
            return []

        remaining = {s.name: set(s.depends_on) for s in self.stages}
        order: list[list[str]] = []

        while remaining:
            ready = [
                name
                for name, deps in remaining.items()
                if not deps
            ]
            if not ready:
                raise ValueError(
                    "Circular dependency detected among stages: "
                    + ", ".join(remaining.keys())
                )
            order.append(sorted(ready))
            for name in ready:
                del remaining[name]
            for deps in remaining.values():
                deps -= set(ready)

        return order


def parse_pipeline(config: dict[str, Any]) -> PipelineConfig:
    """Parse a pipeline configuration dictionary.

    Args:
        config: Dictionary with pipeline definition.

    Returns:
        PipelineConfig object.

    Raises:
        ValueError: If required fields are missing.
    """
    if not isinstance(config, dict):
        raise ValueError("Config must be a dictionary")

    name = config.get("name")
    if not name:
        raise ValueError("Pipeline config must have a 'name' field")

    global_env = config.get("environment", {})
    if not isinstance(global_env, dict):
        raise ValueError("'environment' must be a dictionary")

    trigger_branches = config.get("trigger_branches", ["main"])
    if not isinstance(trigger_branches, list):
        raise ValueError("'trigger_branches' must be a list")

    stages_data = config.get("stages", [])
    if not isinstance(stages_data, list):
        raise ValueError("'stages' must be a list")

    stages = []
    for stage_data in stages_data:
        if not isinstance(stage_data, dict):
            raise ValueError("Each stage must be a dictionary")
        stage = PipelineStage(
            name=stage_data.get("name", ""),
            commands=stage_data.get("commands", []),
            environment=stage_data.get("environment", {}),
            depends_on=stage_data.get("depends_on", []),
            timeout=stage_data.get("timeout", 300),
            allow_failure=stage_data.get("allow_failure", False),
        )
        stages.append(stage)

    return PipelineConfig(
        name=name,
        stages=stages,
        global_env=global_env,
        trigger_branches=trigger_branches,
    )


def merge_configs(
    base: dict[str, Any], override: dict[str, Any]
) -> dict[str, Any]:
    """Deep merge two config dicts, with override taking precedence."""
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = merge_configs(merged[key], value)
        else:
            merged[key] = value
    return merged
