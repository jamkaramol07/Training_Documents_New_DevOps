"""Setup helper module.

Provides utilities for generating setup scripts, managing
environment configurations, and creating project scaffolding
for DevOps training labs.
"""

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectConfig:
    """Configuration for a training lab project."""

    name: str
    language: str
    tools: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    env_vars: dict[str, str] = field(default_factory=dict)

    def validate(self) -> list[str]:
        """Validate project configuration."""
        errors = []
        if not self.name:
            errors.append("Project name cannot be empty")
        if not self.name.replace("-", "").replace("_", "").isalnum():
            errors.append(
                f"Project name '{self.name}' contains invalid characters"
            )

        supported_languages = {
            "python", "javascript", "typescript", "go", "java", "rust",
        }
        if self.language not in supported_languages:
            errors.append(
                f"Unsupported language '{self.language}'. "
                f"Supported: {sorted(supported_languages)}"
            )

        for port in self.ports:
            if not (1 <= port <= 65535):
                errors.append(f"Invalid port number: {port}")

        return errors


def get_system_info() -> dict[str, str]:
    """Gather current system information."""
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
    }


def generate_dockerfile(config: ProjectConfig) -> str:
    """Generate a Dockerfile for a training lab project.

    Args:
        config: Project configuration.

    Returns:
        Dockerfile content as string.
    """
    base_images = {
        "python": "python:3.11-slim",
        "javascript": "node:20-slim",
        "typescript": "node:20-slim",
        "go": "golang:1.21-alpine",
        "java": "eclipse-temurin:21-jdk-alpine",
        "rust": "rust:1.74-slim",
    }

    base_image = base_images.get(config.language, "ubuntu:22.04")

    lines = [
        f"FROM {base_image}",
        "",
        "WORKDIR /app",
        "",
    ]

    for key, value in config.env_vars.items():
        lines.append(f"ENV {key}={value}")

    if config.env_vars:
        lines.append("")

    lines.append("COPY . .")
    lines.append("")

    for port in config.ports:
        lines.append(f"EXPOSE {port}")

    if config.ports:
        lines.append("")

    return "\n".join(lines)


def generate_docker_compose(configs: list[ProjectConfig]) -> str:
    """Generate docker-compose.yml content for multiple services.

    Args:
        configs: List of project configurations.

    Returns:
        Docker Compose YAML content as string.
    """
    lines = ["version: '3.8'", "", "services:"]

    for config in configs:
        lines.append(f"  {config.name}:")
        lines.append(f"    build: ./{config.name}")

        if config.ports:
            lines.append("    ports:")
            for port in config.ports:
                lines.append(f"      - \"{port}:{port}\"")

        if config.env_vars:
            lines.append("    environment:")
            for key, value in config.env_vars.items():
                lines.append(f"      - {key}={value}")

        lines.append("")

    return "\n".join(lines)


def generate_gitignore(language: str) -> str:
    """Generate a .gitignore appropriate for the given language.

    Args:
        language: Programming language name.

    Returns:
        .gitignore content.
    """
    common = [
        "# IDE",
        ".idea/",
        ".vscode/",
        "*.swp",
        "*.swo",
        "",
        "# OS",
        ".DS_Store",
        "Thumbs.db",
        "",
        "# Environment",
        ".env",
        ".env.local",
        "",
    ]

    language_specific: dict[str, list[str]] = {
        "python": [
            "# Python",
            "__pycache__/",
            "*.py[cod]",
            "*$py.class",
            "*.egg-info/",
            "dist/",
            "build/",
            ".venv/",
            "venv/",
            ".pytest_cache/",
            ".coverage",
            "htmlcov/",
        ],
        "javascript": [
            "# JavaScript/Node",
            "node_modules/",
            "dist/",
            "build/",
            "coverage/",
            "*.log",
        ],
        "typescript": [
            "# TypeScript/Node",
            "node_modules/",
            "dist/",
            "build/",
            "coverage/",
            "*.log",
            "*.js.map",
        ],
        "go": [
            "# Go",
            "bin/",
            "vendor/",
            "*.exe",
            "*.test",
        ],
        "java": [
            "# Java",
            "target/",
            "*.class",
            "*.jar",
            "*.war",
            ".gradle/",
        ],
        "rust": [
            "# Rust",
            "target/",
            "Cargo.lock",
        ],
    }

    specific = language_specific.get(language, [])
    return "\n".join(common + specific) + "\n"


def create_project_structure(
    base_path: Path, config: ProjectConfig
) -> list[str]:
    """Create directory structure for a project.

    Args:
        base_path: Base directory to create project in.
        config: Project configuration.

    Returns:
        List of created paths (relative to base_path).

    Raises:
        ValueError: If config validation fails.
    """
    errors = config.validate()
    if errors:
        raise ValueError(f"Invalid config: {'; '.join(errors)}")

    project_dir = base_path / config.name
    created: list[str] = []

    dirs_to_create = [
        project_dir,
        project_dir / "src",
        project_dir / "tests",
        project_dir / "docs",
    ]

    for directory in dirs_to_create:
        directory.mkdir(parents=True, exist_ok=True)
        created.append(str(directory.relative_to(base_path)))

    gitignore_path = project_dir / ".gitignore"
    gitignore_path.write_text(generate_gitignore(config.language))
    created.append(str(gitignore_path.relative_to(base_path)))

    dockerfile_path = project_dir / "Dockerfile"
    dockerfile_path.write_text(generate_dockerfile(config))
    created.append(str(dockerfile_path.relative_to(base_path)))

    return created


def check_port_available(port: int) -> bool:
    """Check if a TCP port is available on localhost.

    Args:
        port: Port number to check.

    Returns:
        True if available, False if in use.
    """
    import socket

    if not (1 <= port <= 65535):
        raise ValueError(f"Invalid port number: {port}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", port))
        return result != 0


def get_env_var(name: str, default: str = "") -> str:
    """Get environment variable with default fallback.

    Args:
        name: Environment variable name.
        default: Default value if not set.

    Returns:
        Variable value or default.
    """
    return os.environ.get(name, default)
