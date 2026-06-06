"""Tests for devops_tools.setup_helper module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from devops_tools.setup_helper import (
    ProjectConfig,
    get_system_info,
    generate_dockerfile,
    generate_docker_compose,
    generate_gitignore,
    create_project_structure,
    check_port_available,
    get_env_var,
)


class TestProjectConfig:
    def test_valid_config(self):
        config = ProjectConfig(
            name="my-app",
            language="python",
            tools=["docker", "terraform"],
            ports=[8080, 5432],
        )
        errors = config.validate()
        assert errors == []

    def test_empty_name(self):
        config = ProjectConfig(name="", language="python")
        errors = config.validate()
        assert any("cannot be empty" in e for e in errors)

    def test_invalid_name_characters(self):
        config = ProjectConfig(name="my app!", language="python")
        errors = config.validate()
        assert any("invalid characters" in e for e in errors)

    def test_valid_name_with_dashes_underscores(self):
        config = ProjectConfig(name="my-app_v2", language="python")
        errors = config.validate()
        assert errors == []

    def test_unsupported_language(self):
        config = ProjectConfig(name="app", language="cobol")
        errors = config.validate()
        assert any("Unsupported language" in e for e in errors)

    def test_all_supported_languages(self):
        for lang in ["python", "javascript", "typescript", "go", "java", "rust"]:
            config = ProjectConfig(name="app", language=lang)
            errors = config.validate()
            assert not any("Unsupported language" in e for e in errors)

    def test_invalid_port_zero(self):
        config = ProjectConfig(name="app", language="python", ports=[0])
        errors = config.validate()
        assert any("Invalid port" in e for e in errors)

    def test_invalid_port_too_high(self):
        config = ProjectConfig(name="app", language="python", ports=[70000])
        errors = config.validate()
        assert any("Invalid port" in e for e in errors)

    def test_valid_port_range(self):
        config = ProjectConfig(name="app", language="python", ports=[1, 65535, 8080])
        errors = config.validate()
        assert not any("Invalid port" in e for e in errors)

    def test_multiple_errors(self):
        config = ProjectConfig(
            name="", language="unknown", ports=[0, 99999]
        )
        errors = config.validate()
        assert len(errors) >= 3


class TestGetSystemInfo:
    def test_returns_dict(self):
        info = get_system_info()
        assert isinstance(info, dict)

    def test_required_keys(self):
        info = get_system_info()
        expected_keys = {"os", "os_version", "architecture", "python_version", "hostname"}
        assert expected_keys == set(info.keys())

    def test_values_are_strings(self):
        info = get_system_info()
        for value in info.values():
            assert isinstance(value, str)


class TestGenerateDockerfile:
    def test_python_project(self):
        config = ProjectConfig(name="api", language="python", ports=[8000])
        dockerfile = generate_dockerfile(config)
        assert "python:3.11-slim" in dockerfile
        assert "WORKDIR /app" in dockerfile
        assert "COPY . ." in dockerfile
        assert "EXPOSE 8000" in dockerfile

    def test_javascript_project(self):
        config = ProjectConfig(name="web", language="javascript")
        dockerfile = generate_dockerfile(config)
        assert "node:20-slim" in dockerfile

    def test_go_project(self):
        config = ProjectConfig(name="svc", language="go")
        dockerfile = generate_dockerfile(config)
        assert "golang:1.21-alpine" in dockerfile

    def test_env_vars_in_dockerfile(self):
        config = ProjectConfig(
            name="app",
            language="python",
            env_vars={"APP_ENV": "production", "PORT": "8080"},
        )
        dockerfile = generate_dockerfile(config)
        assert "ENV APP_ENV=production" in dockerfile
        assert "ENV PORT=8080" in dockerfile

    def test_multiple_ports(self):
        config = ProjectConfig(
            name="app", language="python", ports=[8080, 8443, 9090]
        )
        dockerfile = generate_dockerfile(config)
        assert "EXPOSE 8080" in dockerfile
        assert "EXPOSE 8443" in dockerfile
        assert "EXPOSE 9090" in dockerfile

    def test_unknown_language_uses_ubuntu(self):
        config = ProjectConfig(name="app", language="unknown")
        dockerfile = generate_dockerfile(config)
        assert "ubuntu:22.04" in dockerfile

    def test_no_ports_no_expose(self):
        config = ProjectConfig(name="app", language="python", ports=[])
        dockerfile = generate_dockerfile(config)
        assert "EXPOSE" not in dockerfile


class TestGenerateDockerCompose:
    def test_single_service(self):
        configs = [
            ProjectConfig(name="api", language="python", ports=[8000])
        ]
        compose = generate_docker_compose(configs)
        assert "version: '3.8'" in compose
        assert "services:" in compose
        assert "  api:" in compose
        assert "\"8000:8000\"" in compose

    def test_multiple_services(self):
        configs = [
            ProjectConfig(name="api", language="python", ports=[8000]),
            ProjectConfig(name="web", language="javascript", ports=[3000]),
        ]
        compose = generate_docker_compose(configs)
        assert "  api:" in compose
        assert "  web:" in compose
        assert "\"8000:8000\"" in compose
        assert "\"3000:3000\"" in compose

    def test_service_with_env_vars(self):
        configs = [
            ProjectConfig(
                name="db",
                language="python",
                env_vars={"DB_HOST": "localhost", "DB_PORT": "5432"},
            )
        ]
        compose = generate_docker_compose(configs)
        assert "environment:" in compose
        assert "DB_HOST=localhost" in compose
        assert "DB_PORT=5432" in compose

    def test_service_no_ports_no_env(self):
        configs = [ProjectConfig(name="worker", language="python")]
        compose = generate_docker_compose(configs)
        assert "  worker:" in compose
        assert "ports:" not in compose
        assert "environment:" not in compose


class TestGenerateGitignore:
    def test_python_gitignore(self):
        content = generate_gitignore("python")
        assert "__pycache__/" in content
        assert ".pytest_cache/" in content
        assert ".venv/" in content
        assert ".DS_Store" in content

    def test_javascript_gitignore(self):
        content = generate_gitignore("javascript")
        assert "node_modules/" in content
        assert "coverage/" in content

    def test_go_gitignore(self):
        content = generate_gitignore("go")
        assert "bin/" in content
        assert "vendor/" in content

    def test_unknown_language_common_only(self):
        content = generate_gitignore("unknown")
        assert ".DS_Store" in content
        assert ".env" in content
        assert "__pycache__/" not in content

    def test_common_entries_present(self):
        for lang in ["python", "javascript", "go", "java", "rust"]:
            content = generate_gitignore(lang)
            assert ".idea/" in content
            assert ".env" in content


class TestCreateProjectStructure:
    def test_creates_structure(self, tmp_path):
        config = ProjectConfig(name="test-proj", language="python")
        created = create_project_structure(tmp_path, config)

        project_dir = tmp_path / "test-proj"
        assert project_dir.exists()
        assert (project_dir / "src").exists()
        assert (project_dir / "tests").exists()
        assert (project_dir / "docs").exists()
        assert (project_dir / ".gitignore").exists()
        assert (project_dir / "Dockerfile").exists()
        assert len(created) > 0

    def test_gitignore_content(self, tmp_path):
        config = ProjectConfig(name="py-app", language="python")
        create_project_structure(tmp_path, config)

        gitignore = (tmp_path / "py-app" / ".gitignore").read_text()
        assert "__pycache__/" in gitignore

    def test_dockerfile_content(self, tmp_path):
        config = ProjectConfig(
            name="node-app", language="javascript", ports=[3000]
        )
        create_project_structure(tmp_path, config)

        dockerfile = (tmp_path / "node-app" / "Dockerfile").read_text()
        assert "node:20-slim" in dockerfile
        assert "EXPOSE 3000" in dockerfile

    def test_invalid_config_raises(self, tmp_path):
        config = ProjectConfig(name="", language="python")
        with pytest.raises(ValueError, match="Invalid config"):
            create_project_structure(tmp_path, config)

    def test_idempotent(self, tmp_path):
        config = ProjectConfig(name="app", language="python")
        create_project_structure(tmp_path, config)
        create_project_structure(tmp_path, config)
        assert (tmp_path / "app" / "src").exists()


class TestCheckPortAvailable:
    @patch("socket.socket")
    def test_port_available(self, mock_socket_cls):
        mock_sock = mock_socket_cls.return_value.__enter__.return_value
        mock_sock.connect_ex.return_value = 1  # Connection refused = port free

        assert check_port_available(8080) is True

    @patch("socket.socket")
    def test_port_in_use(self, mock_socket_cls):
        mock_sock = mock_socket_cls.return_value.__enter__.return_value
        mock_sock.connect_ex.return_value = 0  # Connection success = port in use

        assert check_port_available(8080) is False

    def test_invalid_port_zero(self):
        with pytest.raises(ValueError, match="Invalid port"):
            check_port_available(0)

    def test_invalid_port_negative(self):
        with pytest.raises(ValueError, match="Invalid port"):
            check_port_available(-1)

    def test_invalid_port_too_high(self):
        with pytest.raises(ValueError, match="Invalid port"):
            check_port_available(65536)


class TestGetEnvVar:
    def test_existing_var(self):
        with patch.dict(os.environ, {"MY_VAR": "hello"}):
            assert get_env_var("MY_VAR") == "hello"

    def test_missing_var_default(self):
        result = get_env_var("DEFINITELY_NOT_SET_XYZ123", "fallback")
        assert result == "fallback"

    def test_missing_var_empty_default(self):
        result = get_env_var("DEFINITELY_NOT_SET_XYZ123")
        assert result == ""
