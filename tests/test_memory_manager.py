"""Unit tests for orchestrator.memory.memory_manager.MemoryManager."""

from __future__ import annotations

import pytest

from orchestrator.exceptions import MemoryEntryNotFoundError
from orchestrator.memory.in_memory_store import InMemoryStore
from orchestrator.memory.memory_manager import MemoryManager
from orchestrator.memory.sqlite_memory_store import SQLiteMemoryStore


def test_default_store_is_working_memory():
    manager = MemoryManager()

    entry = manager.remember("k", "v")

    assert entry.value == "v"
    assert manager.recall("k") is entry


def test_remember_creates_new_entry():
    manager = MemoryManager(InMemoryStore())

    entry = manager.remember("k", "v", metadata={"source": "test"})

    assert entry.key == "k"
    assert entry.value == "v"
    assert entry.metadata == {"source": "test"}
    assert entry.created_at.tzinfo is not None


def test_remember_updates_existing_entry_preserving_id_and_created_at():
    manager = MemoryManager(InMemoryStore())
    first = manager.remember("k", "v1")

    second = manager.remember("k", "v2")

    assert second.id == first.id
    assert second.created_at == first.created_at
    assert second.value == "v2"
    assert manager.recall("k").value == "v2"


def test_recall_missing_raises():
    manager = MemoryManager(InMemoryStore())

    with pytest.raises(MemoryEntryNotFoundError):
        manager.recall("missing")


def test_forget_removes_entry():
    manager = MemoryManager(InMemoryStore())
    manager.remember("k", "v")

    manager.forget("k")

    with pytest.raises(MemoryEntryNotFoundError):
        manager.recall("k")


def test_forget_missing_raises():
    manager = MemoryManager(InMemoryStore())

    with pytest.raises(MemoryEntryNotFoundError):
        manager.forget("missing")


def test_list_all_and_filtered_by_scope():
    manager = MemoryManager(InMemoryStore())
    manager.remember("a", "1", scope="scope-a")
    manager.remember("b", "2", scope="scope-b")

    assert len(manager.list()) == 2
    scoped = manager.list(scope="scope-a")
    assert len(scoped) == 1
    assert scoped[0].key == "a"


def test_scopes_are_independent():
    manager = MemoryManager(InMemoryStore())
    manager.remember("k", "v1", scope="scope-a")
    manager.remember("k", "v2", scope="scope-b")

    assert manager.recall("k", scope="scope-a").value == "v1"
    assert manager.recall("k", scope="scope-b").value == "v2"


def test_persistent_memory_via_sqlite_store():
    store = SQLiteMemoryStore(db_path=":memory:")
    try:
        manager = MemoryManager(store)
        manager.remember("k", "v")

        assert manager.recall("k").value == "v"
    finally:
        store.close()
