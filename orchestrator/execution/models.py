"""
orchestrator.execution.models
================================

Data models for Phase-06 (Agent Execution Engine).

Design notes:
    - Plain dataclasses only, matching the Phase-04 ``orchestrator.models``
      convention (no pydantic / external validation libraries).
    - ``ExecutionResult`` is the CLI-invocation outcome, distinct from
      ``AgentExecution`` (orchestrator.models): a single ``AgentExecution``
      may accumulate several ``ExecutionResult``s across retries before
      the engine records a final outcome via ``Orchestrator``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentCommand:
    """A validated CLI invocation command for one agent, loaded from
    ``config/agent_commands.yaml`` by ``AgentCommandRegistry``."""

    command: tuple[str, ...]
    timeout_seconds: float


@dataclass(frozen=True)
class ExecutionResult:
    """The outcome of a single agent CLI invocation attempt."""

    output: str
    exit_code: int
    duration_seconds: float

    def succeeded(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential-backoff retry policy for agent invocations.

    Attempt 1 always runs immediately. Attempts 2..max_attempts are
    delayed by ``initial_backoff_seconds * backoff_multiplier ** (n - 2)``
    seconds, where n is the attempt number about to be made.
    """

    max_attempts: int = 3
    initial_backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("RetryPolicy.max_attempts must be >= 1")
        if self.initial_backoff_seconds < 0:
            raise ValueError("RetryPolicy.initial_backoff_seconds must be >= 0")
        if self.backoff_multiplier < 1:
            raise ValueError("RetryPolicy.backoff_multiplier must be >= 1")

    def backoff_seconds(self, attempt_number: int) -> float:
        """Seconds to wait before making ``attempt_number`` (2-indexed onward).

        ``attempt_number`` is the attempt about to be made, so the delay
        before attempt 2 uses exponent 0, before attempt 3 uses exponent 1,
        and so on.
        """
        if attempt_number < 2:
            return 0.0
        return self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt_number - 2))
