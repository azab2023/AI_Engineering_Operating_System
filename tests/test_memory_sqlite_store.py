"""Unit tests for orchestrator.memory.sqlite_memory_store.SQLiteMemoryStore
(Persistent Memory).

Covers the MemoryStore contract (add/get/update/delete/list,
MemoryEntryAlreadyExistsError / MemoryEntryNotFoundError), persistence
across a real reconnect (the actual point of Persistent Memory), and
MemorySerializationError on corrupt stored data.
"""

from __future__ import annotations

import sqlite3

import pytest

from orchestrator.exceptions import (
    MemoryEntryAlreadyExistsError,
    MemoryEntryNotFoundError,
    MemorySerializationError,
)
from orchestrator.memory.models import MemoryEntry
from orchestrator.memory.schema import initialize_memory_schema
from orchestrator.memory.sqlite_memory_store import SQLiteMemoryStore


@pytest.fixture()
def store():
    memory_store = SQLiteMemoryStore(db_path=":memory:")
    yield memory_store
    memory_store.close()


def test_add_then_get_round_trips(store: SQLiteMemoryStore):
    entry = MemoryEntry(key="k", value="v", metadata={"source": "test"})

    store.add(entry)
    fetched = store.get("k")

    assert fetched.id == entry.id
    assert fetched.key == "k"
    assert fetched.value == "v"
    assert fetched.scope == "default"
    assert fetched.metadata == {"source": "test"}


def test_add_duplicate_key_scope_raises(store: SQLiteMemoryStore):
    store.add(MemoryEntry(key="k", value="v"))

    with pytest.raises(MemoryEntryAlreadyExistsError):
        store.add(MemoryEntry(key="k", value="v2"))


def test_add_same_key_different_scope_does_not_raise(store: SQLiteMemoryStore):
    store.add(MemoryEntry(key="k", value="v", scope="scope-a"))
    store.add(MemoryEntry(key="k", value="v", scope="scope-b"))

    assert store.get("k", scope="scope-a").value == "v"
    assert store.get("k", scope="scope-b").value == "v"


def test_get_missing_raises(store: SQLiteMemoryStore):
    with pytest.raises(MemoryEntryNotFoundError):
        store.get("missing")


def test_update_existing_entry(store: SQLiteMemoryStore):
    entry = MemoryEntry(key="k", value="v")
    store.add(entry)

    updated = MemoryEntry(id=entry.id, key="k", value="v2")
    store.update(updated)

    assert store.get("k").value == "v2"


def test_update_missing_raises(store: SQLiteMemoryStore):
    with pytest.raises(MemoryEntryNotFoundError):
        store.update(MemoryEntry(key="missing", value="v"))


def test_delete_removes_entry(store: SQLiteMemoryStore):
    store.add(MemoryEntry(key="k", value="v"))

    store.delete("k")

    with pytest.raises(MemoryEntryNotFoundError):
        store.get("k")


def test_delete_missing_raises(store: SQLiteMemoryStore):
    with pytest.raises(MemoryEntryNotFoundError):
        store.delete("missing")


def test_list_all_and_filtered_by_scope(store: SQLiteMemoryStore):
    store.add(MemoryEntry(key="a", value="1", scope="scope-a"))
    store.add(MemoryEntry(key="b", value="2", scope="scope-b"))

    assert len(store.list()) == 2
    scoped = store.list(scope="scope-a")
    assert len(scoped) == 1
    assert scoped[0].key == "a"


def test_persists_across_reconnect(tmp_path):
    db_path = tmp_path / "memory_test.db"

    store1 = SQLiteMemoryStore(db_path=db_path)
    store1.add(MemoryEntry(key="k", value="v"))
    store1.close()

    store2 = SQLiteMemoryStore(db_path=db_path)
    try:
        fetched = store2.get("k")
        assert fetched.value == "v"
    finally:
        store2.close()


def test_corrupt_metadata_raises_serialization_error():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
    )
    initialize_memory_schema(conn)
    conn.execute(
        """
        INSERT INTO memory_entries (id, key, scope, value, metadata, created_at, updated_at)
        VALUES ('id-1', 'k', 'default', 'v', 'not-json',
                '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00');
        """
    )
    conn.commit()

    from orchestrator.memory.serializers import row_to_memory_entry

    row = conn.execute("SELECT * FROM memory_entries WHERE key = 'k'").fetchone()
    with pytest.raises(MemorySerializationError):
        row_to_memory_entry(row)
    conn.close()


def test_initialize_memory_schema_is_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
    )

    initialize_memory_schema(conn)
    initialize_memory_schema(conn)  # must not raise on a second call

    cursor = conn.execute("SELECT value FROM schema_meta WHERE key = 'memory_schema_version'")
    assert cursor.fetchone()["value"] == "1"
