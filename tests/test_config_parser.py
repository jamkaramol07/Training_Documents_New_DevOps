"""Tests for devops_tools.config_parser module."""

import pytest

from devops_tools.config_parser import (
    PipelineStage,
    PipelineConfig,
    parse_pipeline,
    merge_configs,
)


class TestPipelineStage:
    def test_defaults(self):
        stage = PipelineStage(name="build")
        assert stage.name == "build"
        assert stage.commands == []
        assert stage.environment == {}
        assert stage.depends_on == []
        assert stage.timeout == 300
        assert stage.allow_failure is False

    def test_valid_stage(self):
        stage = PipelineStage(
            name="test",
            commands=["pytest"],
            timeout=600,
        )
        errors = stage.validate()
        assert errors == []

    def test_empty_name(self):
        stage = PipelineStage(name="", commands=["echo hi"])
        errors = stage.validate()
        assert any("cannot be empty" in e for e in errors)

    def test_invalid_name_characters(self):
        stage = PipelineStage(name="build stage!", commands=["make"])
        errors = stage.validate()
        assert any("invalid characters" in e for e in errors)

    def test_valid_name_with_dashes_underscores(self):
        stage = PipelineStage(name="build-test_stage", commands=["make"])
        errors = stage.validate()
        assert errors == []

    def test_no_commands(self):
        stage = PipelineStage(name="empty")
        errors = stage.validate()
        assert any("no commands" in e for e in errors)

    def test_invalid_timeout(self):
        stage = PipelineStage(name="slow", commands=["sleep"], timeout=0)
        errors = stage.validate()
        assert any("invalid timeout" in e for e in errors)

    def test_negative_timeout(self):
        stage = PipelineStage(name="neg", commands=["x"], timeout=-1)
        errors = stage.validate()
        assert any("invalid timeout" in e for e in errors)


class TestPipelineConfig:
    def test_valid_config(self):
        config = PipelineConfig(
            name="ci",
            stages=[
                PipelineStage(name="build", commands=["make build"]),
                PipelineStage(name="test", commands=["make test"], depends_on=["build"]),
            ],
        )
        errors = config.validate()
        assert errors == []

    def test_empty_name(self):
        config = PipelineConfig(
            name="",
            stages=[PipelineStage(name="build", commands=["make"])],
        )
        errors = config.validate()
        assert any("Pipeline name cannot be empty" in e for e in errors)

    def test_no_stages(self):
        config = PipelineConfig(name="empty")
        errors = config.validate()
        assert any("at least one stage" in e for e in errors)

    def test_duplicate_stage_names(self):
        config = PipelineConfig(
            name="dup",
            stages=[
                PipelineStage(name="build", commands=["make"]),
                PipelineStage(name="build", commands=["make again"]),
            ],
        )
        errors = config.validate()
        assert any("Duplicate stage name" in e for e in errors)

    def test_unknown_dependency(self):
        config = PipelineConfig(
            name="bad-dep",
            stages=[
                PipelineStage(
                    name="test", commands=["pytest"], depends_on=["nonexistent"]
                ),
            ],
        )
        errors = config.validate()
        assert any("unknown stage 'nonexistent'" in e for e in errors)

    def test_execution_order_no_deps(self):
        config = PipelineConfig(
            name="parallel",
            stages=[
                PipelineStage(name="a", commands=["x"]),
                PipelineStage(name="b", commands=["y"]),
                PipelineStage(name="c", commands=["z"]),
            ],
        )
        order = config.get_execution_order()
        assert order == [["a", "b", "c"]]

    def test_execution_order_with_deps(self):
        config = PipelineConfig(
            name="sequential",
            stages=[
                PipelineStage(name="build", commands=["make"]),
                PipelineStage(name="test", commands=["pytest"], depends_on=["build"]),
                PipelineStage(name="deploy", commands=["deploy"], depends_on=["test"]),
            ],
        )
        order = config.get_execution_order()
        assert order == [["build"], ["test"], ["deploy"]]

    def test_execution_order_diamond(self):
        config = PipelineConfig(
            name="diamond",
            stages=[
                PipelineStage(name="build", commands=["make"]),
                PipelineStage(name="lint", commands=["lint"], depends_on=["build"]),
                PipelineStage(name="test", commands=["test"], depends_on=["build"]),
                PipelineStage(
                    name="deploy",
                    commands=["deploy"],
                    depends_on=["lint", "test"],
                ),
            ],
        )
        order = config.get_execution_order()
        assert order == [["build"], ["lint", "test"], ["deploy"]]

    def test_execution_order_circular_dependency(self):
        config = PipelineConfig(
            name="circular",
            stages=[
                PipelineStage(name="a", commands=["x"], depends_on=["b"]),
                PipelineStage(name="b", commands=["y"], depends_on=["a"]),
            ],
        )
        with pytest.raises(ValueError, match="Circular dependency"):
            config.get_execution_order()

    def test_execution_order_empty(self):
        config = PipelineConfig(name="empty", stages=[])
        order = config.get_execution_order()
        assert order == []


class TestParsePipeline:
    def test_minimal_config(self):
        data = {
            "name": "ci",
            "stages": [{"name": "build", "commands": ["make"]}],
        }
        config = parse_pipeline(data)
        assert config.name == "ci"
        assert len(config.stages) == 1
        assert config.stages[0].name == "build"
        assert config.trigger_branches == ["main"]

    def test_full_config(self):
        data = {
            "name": "full-pipeline",
            "environment": {"CI": "true"},
            "trigger_branches": ["main", "develop"],
            "stages": [
                {
                    "name": "build",
                    "commands": ["make build"],
                    "environment": {"BUILD_ENV": "prod"},
                    "timeout": 600,
                },
                {
                    "name": "test",
                    "commands": ["pytest", "mypy"],
                    "depends_on": ["build"],
                    "allow_failure": True,
                },
            ],
        }
        config = parse_pipeline(data)
        assert config.name == "full-pipeline"
        assert config.global_env == {"CI": "true"}
        assert config.trigger_branches == ["main", "develop"]
        assert len(config.stages) == 2
        assert config.stages[0].timeout == 600
        assert config.stages[1].allow_failure is True
        assert config.stages[1].depends_on == ["build"]

    def test_not_a_dict(self):
        with pytest.raises(ValueError, match="must be a dictionary"):
            parse_pipeline("not a dict")

    def test_missing_name(self):
        with pytest.raises(ValueError, match="must have a 'name' field"):
            parse_pipeline({"stages": []})

    def test_empty_name(self):
        with pytest.raises(ValueError, match="must have a 'name' field"):
            parse_pipeline({"name": "", "stages": []})

    def test_invalid_environment_type(self):
        with pytest.raises(ValueError, match="'environment' must be a dictionary"):
            parse_pipeline({"name": "x", "environment": "bad"})

    def test_invalid_trigger_branches_type(self):
        with pytest.raises(ValueError, match="'trigger_branches' must be a list"):
            parse_pipeline({"name": "x", "trigger_branches": "main"})

    def test_invalid_stages_type(self):
        with pytest.raises(ValueError, match="'stages' must be a list"):
            parse_pipeline({"name": "x", "stages": "not-a-list"})

    def test_invalid_stage_item(self):
        with pytest.raises(ValueError, match="Each stage must be a dictionary"):
            parse_pipeline({"name": "x", "stages": ["not-a-dict"]})


class TestMergeConfigs:
    def test_simple_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = merge_configs(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"env": {"A": "1", "B": "2"}, "name": "base"}
        override = {"env": {"B": "override", "C": "3"}}
        result = merge_configs(base, override)
        assert result == {"env": {"A": "1", "B": "override", "C": "3"}, "name": "base"}

    def test_override_non_dict_with_dict(self):
        base = {"x": "string"}
        override = {"x": {"nested": True}}
        result = merge_configs(base, override)
        assert result == {"x": {"nested": True}}

    def test_override_dict_with_non_dict(self):
        base = {"x": {"nested": True}}
        override = {"x": "flat"}
        result = merge_configs(base, override)
        assert result == {"x": "flat"}

    def test_empty_base(self):
        result = merge_configs({}, {"a": 1})
        assert result == {"a": 1}

    def test_empty_override(self):
        result = merge_configs({"a": 1}, {})
        assert result == {"a": 1}

    def test_deeply_nested(self):
        base = {"l1": {"l2": {"l3": {"a": 1, "b": 2}}}}
        override = {"l1": {"l2": {"l3": {"b": 99, "c": 3}}}}
        result = merge_configs(base, override)
        assert result == {"l1": {"l2": {"l3": {"a": 1, "b": 99, "c": 3}}}}
