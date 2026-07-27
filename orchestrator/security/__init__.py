"""
orchestrator.security
========================

Phase-12 (Security & Permissions, ADR-0010): path sandboxing and
per-agent read/write authorization for tools run through
``orchestrator.tools.tool_executor.ToolExecutor``.

Mirrors the ``orchestrator.tools`` / ``orchestrator.providers`` /
``orchestrator.workflow`` package shape: ``models.py`` (plain frozen
dataclasses), ``permission_registry.py`` (config loading/validation
only), and ``authorizer.py`` (the reusable, centralized enforcement
entry point ``ToolExecutor`` calls).
"""

from __future__ import annotations
