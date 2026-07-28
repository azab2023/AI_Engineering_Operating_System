"""Unit tests for orchestrator.cli (Phase-15, ADR-0013)."""

from __future__ import annotations

from importlib import metadata

import pytest

from orchestrator import cli


def test_get_version_matches_installed_package_metadata():
    # When the package is installed (e.g. `pip install -e .` in this
    # environment), get_version() must reflect the real metadata rather
    # than silently falling back.
    try:
        expected = metadata.version("aeos")
    except metadata.PackageNotFoundError:
        expected = cli._FALLBACK_VERSION
    assert cli.get_version() == expected


def test_version_flag_prints_version(capsys):
    exit_code = cli.main(["--version"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == cli.get_version()


def test_version_subcommand_prints_version(capsys):
    exit_code = cli.main(["version"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == cli.get_version()


def test_no_args_shows_help_and_commands(capsys):
    exit_code = cli.main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Available commands:" in captured.out
    assert "version" in captured.out
    assert "list-agents" in captured.out
    assert "help" in captured.out


def test_help_subcommand_shows_help_and_commands(capsys):
    exit_code = cli.main(["help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Available commands:" in captured.out


def test_list_agents_loads_real_registry(capsys):
    # Exercises the "optionally load the existing orchestrator"
    # requirement against the real, shipped config/agent_registry.yaml --
    # no new orchestration logic, just AgentRegistry() + Orchestrator().
    exit_code = cli.main(["list-agents"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Registered agents" in captured.out
    for expected_name in ("claude_code", "codex", "aider", "gemini"):
        assert expected_name in captured.out


def test_list_agents_reports_registry_error(monkeypatch, capsys):
    from orchestrator.exceptions import AgentRegistryError

    def _boom(*args, **kwargs):
        raise AgentRegistryError("registry file not found")

    monkeypatch.setattr(cli, "AgentRegistry", _boom)
    exit_code = cli._list_agents()
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Failed to load agent registry" in captured.err


def test_unknown_command_falls_through_to_help(monkeypatch, capsys):
    # argparse subparsers reject truly unknown commands before main() ever
    # sees them; this confirms that behavior rather than relying on our
    # own fallback branch, which is otherwise unreachable via the CLI.
    with pytest.raises(SystemExit):
        cli.main(["not-a-real-command"])
    captured = capsys.readouterr()
    assert "invalid choice" in captured.err
