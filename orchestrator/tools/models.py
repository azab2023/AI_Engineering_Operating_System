"""
orchestrator.tools.models
============================

Data models for Phase-09 (Tool Execution Framework).

Design notes:
    - Plain, frozen dataclasses only, matching the convention already
      established in ``orchestrator.models`` (Phase-04),
      ``orchestrator.execution.models`` (Phase-06),
      ``orchestrator.providers.models`` (Phase-07), and
      ``orchestrator.prompts.models`` (Phase-08) -- no pydantic / ORM /
      external validation libraries.
    - ``ToolDefinition`` is the validated, in-memory representation of
      one entry in ``config/tools.yaml``, produced by ``ToolRegistry``
      (see ``tool_registry.py``).
    - ``ToolResult`` is the successful-outcome analogue of
      ``orchestrator.providers.models.ProviderResponse`` (Phase-07):
      a ``Tool.execute()`` call either returns a ``ToolResult`` or
      raises ``ToolExecutionError`` -- there is no "ran but failed"
      return value to represent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_VALID_ARGUMENT_TYPES = frozenset({"string", "number", "boolean"})


@dataclass(frozen=True)
class ToolParameter:
    """One argument a tool's ``execute()`` call may accept.

    Attributes:
        name: the argument's key, as passed in the ``arguments`` mapping
            given to ``ToolExecutor.execute()``.
        type: one of ``"string"`` | ``"number"`` | ``"boolean"``.
        required: whether a call must supply this argument.
        description: human-readable purpose, for documentation only.
    """

    name: str
    type: str
    required: bool
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("ToolParameter.name must be a non-empty string")
        if self.type not in _VALID_ARGUMENT_TYPES:
            raise ValueError(
                f"ToolParameter {self.name!r}: type must be one of "
                f"{sorted(_VALID_ARGUMENT_TYPES)}, got {self.type!r}"
            )


@dataclass(frozen=True)
class ToolDefinition:
    """A validated tool entry, loaded from ``config/tools.yaml`` by
    ``ToolRegistry``.

    Attributes:
        tool_name: unique identifier (the entry's top-level YAML key).
        tool_type: which ``Tool`` implementation to use (resolved by
            ``ToolFactory``). Free-form by design -- adding a new
            built-in tool never requires changing this dataclass or
            ``ToolRegistry``, only ``ToolFactory``'s registration dict.
            See ADR-0007 decision 4.
        enabled: whether this tool entry may be used. A disabled entry
            is a configuration error at lookup time, not a transient
            failure.
        description: human-readable purpose, for documentation only.
        parameters: the full set of arguments this tool's ``execute()``
            may accept. ``ToolExecutor`` rejects both a missing
            ``required`` argument and an undeclared one -- see
            ``MissingRequiredArgumentError`` / ``UnknownArgumentError``.
    """

    tool_name: str
    tool_type: str
    enabled: bool
    description: str
    parameters: tuple[ToolParameter, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.tool_name or not self.tool_name.strip():
            raise ValueError("ToolDefinition.tool_name must be a non-empty string")
        if not self.tool_type or not self.tool_type.strip():
            raise ValueError("ToolDefinition.tool_type must be a non-empty string")
        if not self.description or not self.description.strip():
            raise ValueError("ToolDefinition.description must be a non-empty string")

    def required_argument_names(self) -> frozenset[str]:
        return frozenset(p.name for p in self.parameters if p.required)

    def declared_argument_names(self) -> frozenset[str]:
        return frozenset(p.name for p in self.parameters)

    def parameter(self, name: str) -> ToolParameter:
        for candidate in self.parameters:
            if candidate.name == name:
                return candidate
        raise KeyError(name)


@dataclass(frozen=True)
class ToolResult:
    """The successful outcome of one ``Tool.execute()`` call."""

    tool_name: str
    output: str
    duration_seconds: float

    def __post_init__(self) -> None:
        if not self.tool_name or not self.tool_name.strip():
            raise ValueError("ToolResult.tool_name must be a non-empty string")
        if self.duration_seconds < 0:
            raise ValueError("ToolResult.duration_seconds must be >= 0")
