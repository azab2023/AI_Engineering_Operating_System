"""
orchestrator.cli
==================

Phase-15 (ADR-0013) minimal command-line entry point for AEOS.

Scope note: this module introduces NO new orchestration, execution,
workflow, provider, tool, or plugin logic. Every command below is a
thin pass-through to a facade that already exists
(``orchestrator.registry.AgentRegistry`` / ``orchestrator.core.Orchestrator``).
See ADR-0013 for the full rationale and the alternatives considered.

Registered as the ``aeos`` console script via ``[project.scripts]`` in
``pyproject.toml`` (``orchestrator.cli:main``).
"""

from __future__ import annotations

import argparse
import sys
from importlib import metadata

from orchestrator.exceptions import AgentRegistryError
from orchestrator.registry import AgentRegistry

# Falls back to this only if the package isn't installed with metadata
# available (e.g. running from a source checkout without `pip install -e .`).
# Kept in sync with pyproject.toml's [project].version -- see ADR-0013,
# Consequences (Negative), for why this is not the single source of truth.
_FALLBACK_VERSION = "1.5.0"

_COMMANDS: dict[str, str] = {
    "version": "Print the installed AEOS version.",
    "list-agents": "Load config/agent_registry.yaml and list registered agents.",
    "help": "Show this help message.",
}


def get_version() -> str:
    """Return the installed AEOS version.

    Reads from installed package metadata (single source of truth:
    pyproject.toml's [project].version) so this module never needs
    editing when the version changes.
    """
    try:
        return metadata.version("aeos")
    except metadata.PackageNotFoundError:
        return _FALLBACK_VERSION


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aeos",
        description="AEOS (AI Engineering Operating System) command-line interface.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show the AEOS version and exit.",
    )
    subparsers = parser.add_subparsers(dest="command")
    for name, description in _COMMANDS.items():
        subparsers.add_parser(name, help=description)
    return parser


def _print_commands() -> None:
    print("Available commands:")
    for name, description in _COMMANDS.items():
        print(f"  {name:<12} {description}")


def _list_agents() -> int:
    """Load the existing AgentRegistry and print every registered agent.

    Reuses ``AgentRegistry`` (Phase-04) exactly as-is against its default
    config path (``config/agent_registry.yaml``); introduces no new
    orchestration logic. Prints one line per agent: name, status, priority.
    """
    try:
        registry = AgentRegistry()
    except AgentRegistryError as exc:
        print(f"Failed to load agent registry: {exc}", file=sys.stderr)
        return 1

    agents = registry.list_agents()
    if not agents:
        print("No agents registered.")
        return 0

    print(f"Registered agents ({len(agents)}):")
    for agent in agents:
        print(f"  {agent.name:<20} status={agent.status.value:<10} priority={agent.priority.value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code (does not call sys.exit())."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(get_version())
        return 0

    command = args.command or "help"

    if command == "version":
        print(get_version())
        return 0

    if command == "list-agents":
        return _list_agents()

    if command == "help":
        parser.print_help()
        print()
        _print_commands()
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
