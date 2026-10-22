import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import store


def test_vault_entries_are_scoped_to_owner(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(store, "_db", None)

    store.put_vault("user-a", "same-id", "ciphertext-a")
    store.put_vault("user-b", "same-id", "ciphertext-b")

    assert store.get_vault("user-a", "same-id") == "ciphertext-a"
    assert store.get_vault("user-b", "same-id") == "ciphertext-b"
    assert store.get_vault("user-c", "same-id") is None

    store._db.close()
    monkeypatch.setattr(store, "_db", None)


def test_rag_documents_are_scoped_to_owner(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(store, "_db", None)

    store.index_document("user-a", "private.txt", "violet hummingbird reference")
    store.index_document("user-b", "other.txt", "violet hummingbird reference")

    assert [doc["name"] for doc in store.rag_search("user-a", "hummingbird")] == ["private.txt"]
    assert [doc["name"] for doc in store.rag_search("user-b", "hummingbird")] == ["other.txt"]

    store._db.close()
    monkeypatch.setattr(store, "_db", None)


def test_existing_database_schema_migrates_owner_columns(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "legacy.db")
    monkeypatch.setattr(store, "_db", None)
    legacy = sqlite3.connect(store.DB_PATH)
    legacy.executescript(
        "CREATE TABLE vault (id TEXT PRIMARY KEY, ciphertext TEXT NOT NULL, updated REAL NOT NULL);"
        "CREATE TABLE docs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, text TEXT NOT NULL, created REAL NOT NULL);"
    )
    legacy.close()

    db = store._connect()
    vault_columns = {row["name"] for row in db.execute("PRAGMA table_info(vault)")}
    doc_columns = {row["name"] for row in db.execute("PRAGMA table_info(docs)")}
    assert "owner" in vault_columns
    assert "owner" in doc_columns

    db.close()
    monkeypatch.setattr(store, "_db", None)
