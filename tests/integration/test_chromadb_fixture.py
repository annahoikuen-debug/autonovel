"""Test to check if chromadb fixture works."""
from __future__ import annotations



def test_chromadb_fixture(chromadb_container):
    """Just check that we get the chromadb fixture."""
    print("Type of chromadb_container:", type(chromadb_container))
    print("ChromaDB container:", chromadb_container)
