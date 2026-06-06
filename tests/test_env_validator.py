"""Tests for devops_tools.env_validator module."""

from unittest.mock import patch, MagicMock
import subprocess

import pytest

from devops_tools.env_validator import (
    ToolCheck,
    ValidationReport,
    check_tool,
    validate_environment,
    get_missing_tools,
    REQUIRED_TOOLS,
)


class TestToolCheck:
    def test_tool_check_defaults(self):
        tc = ToolCheck(name="git", installed=True)
        assert tc.name == "git"
        assert tc.installed is True
        assert tc.version == ""
        assert tc.path == ""

    def test_tool_check_full(self):
        tc = ToolCheck(
            name="docker", installed=True, version="24.0.1", path="/usr/bin/docker"
        )
        assert tc.name == "docker"
        assert tc.version == "24.0.1"
        assert tc.path == "/usr/bin/docker"

    def test_tool_check_not_installed(self):
        tc = ToolCheck(name="missing", installed=False)
        assert tc.installed is False


class TestValidationReport:
    def test_empty_report(self):
        report = ValidationReport()
        assert report.all_passed is True
        assert report.passed_count == 0
        assert report.failed_count == 0
        assert report.summary() == "0/0 tools available"

    def test_all_passed(self):
        report = ValidationReport(
            checks=[
                ToolCheck(name="git", installed=True),
                ToolCheck(name="docker", installed=True),
            ]
        )
        assert report.all_passed is True
        assert report.passed_count == 2
        assert report.failed_count == 0
        assert report.summary() == "2/2 tools available"

    def test_some_failed(self):
        report = ValidationReport(
            checks=[
                ToolCheck(name="git", installed=True),
                ToolCheck(name="docker", installed=False),
                ToolCheck(name="terraform", installed=False),
            ]
        )
        assert report.all_passed is False
        assert report.passed_count == 1
        assert report.failed_count == 2
        assert report.summary() == "1/3 tools available"

    def test_all_failed(self):
        report = ValidationReport(
            checks=[
                ToolCheck(name="x", installed=False),
                ToolCheck(name="y", installed=False),
            ]
        )
        assert report.all_passed is False
        assert report.passed_count == 0
        assert report.failed_count == 2


class TestCheckTool:
    @patch("devops_tools.env_validator.shutil.which")
    @patch("devops_tools.env_validator.subprocess.run")
    def test_tool_found_with_version(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/git"
        mock_run.return_value = MagicMock(
            stdout="git version 2.40.0", stderr=""
        )

        result = check_tool("git", "--version")
        assert result.installed is True
        assert result.name == "git"
        assert result.version == "git version 2.40.0"
        assert result.path == "/usr/bin/git"

    @patch("devops_tools.env_validator.shutil.which")
    def test_tool_not_found(self, mock_which):
        mock_which.return_value = None

        result = check_tool("nonexistent")
        assert result.installed is False
        assert result.name == "nonexistent"
        assert result.version == ""
        assert result.path == ""

    @patch("devops_tools.env_validator.shutil.which")
    @patch("devops_tools.env_validator.subprocess.run")
    def test_tool_version_from_stderr(self, mock_run, mock_which):
        mock_which.return_value = "/usr/local/bin/aws"
        mock_run.return_value = MagicMock(
            stdout="", stderr="aws-cli/2.13.0"
        )

        result = check_tool("aws", "--version")
        assert result.installed is True
        assert result.version == "aws-cli/2.13.0"

    @patch("devops_tools.env_validator.shutil.which")
    @patch("devops_tools.env_validator.subprocess.run")
    def test_tool_timeout(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/slow"
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="slow", timeout=10)

        result = check_tool("slow")
        assert result.installed is True
        assert result.version == "unknown"
        assert result.path == "/usr/bin/slow"

    @patch("devops_tools.env_validator.shutil.which")
    @patch("devops_tools.env_validator.subprocess.run")
    def test_tool_os_error(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/broken"
        mock_run.side_effect = OSError("Permission denied")

        result = check_tool("broken")
        assert result.installed is True
        assert result.version == "unknown"
        assert result.path == "/usr/bin/broken"

    @patch("devops_tools.env_validator.shutil.which")
    @patch("devops_tools.env_validator.subprocess.run")
    def test_multi_word_version_flag(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/kubectl"
        mock_run.return_value = MagicMock(
            stdout="v1.28.0", stderr=""
        )

        result = check_tool("kubectl", "version --client --short")
        assert result.installed is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == ["kubectl", "version", "--client", "--short"]


class TestValidateEnvironment:
    @patch("devops_tools.env_validator.check_tool")
    def test_default_tools(self, mock_check):
        mock_check.return_value = ToolCheck(name="x", installed=True)

        report = validate_environment()
        assert mock_check.call_count == len(REQUIRED_TOOLS)
        assert report.all_passed is True

    @patch("devops_tools.env_validator.check_tool")
    def test_custom_tools(self, mock_check):
        mock_check.return_value = ToolCheck(name="custom", installed=True)
        tools = [
            {"name": "foo", "version_flag": "-v"},
            {"name": "bar"},
        ]

        report = validate_environment(tools)
        assert mock_check.call_count == 2
        assert len(report.checks) == 2

    @patch("devops_tools.env_validator.check_tool")
    def test_mixed_results(self, mock_check):
        mock_check.side_effect = [
            ToolCheck(name="a", installed=True),
            ToolCheck(name="b", installed=False),
        ]
        tools = [{"name": "a"}, {"name": "b"}]

        report = validate_environment(tools)
        assert report.passed_count == 1
        assert report.failed_count == 1


class TestGetMissingTools:
    @patch("devops_tools.env_validator.check_tool")
    def test_no_missing(self, mock_check):
        mock_check.return_value = ToolCheck(name="x", installed=True)
        tools = [{"name": "git"}, {"name": "docker"}]

        missing = get_missing_tools(tools)
        assert missing == []

    @patch("devops_tools.env_validator.check_tool")
    def test_some_missing(self, mock_check):
        mock_check.side_effect = [
            ToolCheck(name="git", installed=True),
            ToolCheck(name="terraform", installed=False),
            ToolCheck(name="kubectl", installed=False),
        ]
        tools = [{"name": "git"}, {"name": "terraform"}, {"name": "kubectl"}]

        missing = get_missing_tools(tools)
        assert missing == ["terraform", "kubectl"]

    @patch("devops_tools.env_validator.check_tool")
    def test_all_missing(self, mock_check):
        mock_check.return_value = ToolCheck(name="x", installed=False)
        tools = [{"name": "a"}, {"name": "b"}]

        missing = get_missing_tools(tools)
        assert len(missing) == 2
