"""Unit tests for orchestrator.memory.in_memory_store.InMemoryStore
(Working Memory)."""

from __future__ import annotations

import pytest

from orchestrator.exceptions import MemoryEntryAlreadyExistsError, MemoryEntryNotFoundError
from orchestrator.memory.in_memory_store import InMemoryStore
from orchestrator.memory.models import MemoryEntry


def test_add_then_get_round_trips():
    store = InMemoryStore()
    entry = MemoryEntry(key="k", value="v")

    store.add(entry)

    assert store.get("k") is entry


def test_add_duplicate_key_scope_raises():
    store = InMemoryStore()
    store.add(MemoryEntry(key="k", value="v"))

    with pytest.raises(MemoryEntryAlreadyExistsError):
        store.add(MemoryEntry(key="k", value="v2"))


def test_add_same_key_different_scope_does_not_raise():
    store = InMemoryStore()
    store.add(MemoryEntry(key="k", value="v", scope="scope-a"))
    store.add(MemoryEntry(key="k", value="v", scope="scope-b"))

    assert store.get("k", scope="scope-a").value == "v"
    assert store.get("k", scope="scope-b").value == "v"


def test_get_missing_raises():
    store = InMemoryStore()

    with pytest.raises(MemoryEntryNotFoundError):
        store.get("missing")


def test_update_existing_entry():
    store = InMemoryStore()
    entry = MemoryEntry(key="k", value="v")
    store.add(entry)

    updated = MemoryEntry(id=entry.id, key="k", value="v2")
    store.update(updated)

    assert store.get("k").value == "v2"


def test_update_missing_raises():
    store = InMemoryStore()

    with pytest.raises(MemoryEntryNotFoundError):
        store.update(MemoryEntry(key="missing", value="v"))


def test_delete_removes_entry():
    store = InMemoryStore()
    store.add(MemoryEntry(key="k", value="v"))

    store.delete("k")

    with pytest.raises(MemoryEntryNotFoundError):
        store.get("k")


def test_delete_missing_raises():
    store = InMemoryStore()

    with pytest.raises(MemoryEntryNotFoundError):
        store.delete("missing")


def test_list_all_and_filtered_by_scope():
    store = InMemoryStore()
    store.add(MemoryEntry(key="a", value="1", scope="scope-a"))
    store.add(MemoryEntry(key="b", value="2", scope="scope-b"))

    assert len(store.list()) == 2
    scoped = store.list(scope="scope-a")
    assert len(scoped) == 1
    assert scoped[0].key == "a"
