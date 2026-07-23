"""Import/adapter smoke for Pinecone.

Pinecone is a hosted SaaS with no local container, so there is no round-trip
here. This still guards the failure class the other smokes catch server-side:
a broken or incompatible ``pinecone`` client, or an adapter that no longer
imports against it. We import the client, construct the adapter, and exercise
credential validation — without a live ``connect()`` (which needs real creds).
"""

from __future__ import annotations

import pytest

pytest.importorskip("pinecone")


def test_pinecone_client_imports():
    import pinecone

    assert hasattr(pinecone, "Pinecone")


def test_pinecone_adapter_constructs_and_validates():
    from cyborgdb_migrate.sources.pinecone import PineconeSource

    source = PineconeSource()
    assert source.name() == "Pinecone"

    # Empty api_key must be rejected by the config layer.
    with pytest.raises(ValueError):
        source.configure({"api_key": ""})

    # A non-empty key configures cleanly (no network call until connect()).
    source.configure({"api_key": "smoke-placeholder-key"})
