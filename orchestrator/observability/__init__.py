"""
orchestrator.observability
==============================

Phase-13 (ADR-0011) internal monitoring and observability: structured
events, counters, and timers, recorded in-memory and queried through
``ObservabilityManager``.

Mirrors ``orchestrator.security``/``orchestrator.memory``: a
self-contained, additive package. Nothing here changes the default
behavior of any pre-Phase-13 caller -- every integrated component's
new ``observer`` parameter defaults to ``None``.
"""
