"""Environment validator module.

Checks whether required DevOps tools are installed and accessible
in the current environment.
"""

import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class ToolCheck:
    """Result of checking a single tool."""

    name: str
    installed: bool
    version: str = ""
    path: str = ""


@dataclass
class ValidationReport:
    """Aggregate report of all tool checks."""

    checks: list[ToolCheck] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(check.installed for check in self.checks)

    @property
    def passed_count(self) -> int:
        return sum(1 for check in self.checks if check.installed)

    @property
    def failed_count(self) -> int:
        return sum(1 for check in self.checks if not check.installed)

    def summary(self) -> str:
        total = len(self.checks)
        passed = self.passed_count
        return f"{passed}/{total} tools available"


REQUIRED_TOOLS = [
    {"name": "git", "version_flag": "--version"},
    {"name": "docker", "version_flag": "--version"},
    {"name": "terraform", "version_flag": "--version"},
    {"name": "aws", "version_flag": "--version"},
    {"name": "kubectl", "version_flag": "version --client --short"},
    {"name": "python3", "version_flag": "--version"},
]


def check_tool(name: str, version_flag: str = "--version") -> ToolCheck:
    """Check if a tool is installed and get its version."""
    path = shutil.which(name)
    if path is None:
        return ToolCheck(name=name, installed=False)

    try:
        args = [name] + version_flag.split()
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = result.stdout.strip() or result.stderr.strip()
        return ToolCheck(name=name, installed=True, version=version, path=path)
    except (subprocess.TimeoutExpired, OSError):
        return ToolCheck(name=name, installed=True, version="unknown", path=path)


def validate_environment(tools: list[dict] | None = None) -> ValidationReport:
    """Validate that all required tools are installed.

    Args:
        tools: List of tool dicts with 'name' and optional 'version_flag'.
               Defaults to REQUIRED_TOOLS.

    Returns:
        ValidationReport with results for each tool.
    """
    if tools is None:
        tools = REQUIRED_TOOLS

    report = ValidationReport()
    for tool in tools:
        name = tool["name"]
        version_flag = tool.get("version_flag", "--version")
        check = check_tool(name, version_flag)
        report.checks.append(check)

    return report


def get_missing_tools(tools: list[dict] | None = None) -> list[str]:
    """Return names of tools that are not installed."""
    report = validate_environment(tools)
    return [check.name for check in report.checks if not check.installed]
