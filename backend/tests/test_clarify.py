"""Clarify loop: the answer of POST /api/resume must fill the asked slot."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CHECKPOINT_PATH", "./data/test_checkpoints.db")

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _session(client: TestClient) -> str:
    return client.post("/api/session").json()["session_id"]


def test_location_chip_fills_the_location_slot(client):
    session_id = _session(client)
    data = client.post(
        "/api/chat",
        json={"session_id": session_id, "text": "گوشی سامسونگ تا ۶۰ میلیون"},
    ).json()
    assert data["pending"] is not None
    assert data["pending"]["id"] == "q_location"
    assert data["slots"]["budget_max"] == 60_000_000

    resumed = client.post(
        "/api/resume", json={"session_id": session_id, "value": "جمهوری"}
    ).json()

    assert resumed["pending"] is None, resumed["pending"]
    location = resumed["slots"]["location"]
    assert location is not None
    assert "جمهوری" in location["label"]
    assert location["lat"] > 35 and location["lon"] > 51
    assert resumed["cards"], "answering the location question should lead to cards"


def test_skip_answer_marks_the_slot_and_never_asks_again(client):
    session_id = _session(client)
    data = client.post(
        "/api/chat",
        json={"session_id": session_id, "text": "گوشی سامسونگ تا ۶۰ میلیون"},
    ).json()
    assert data["pending"]["id"] == "q_location"

    resumed = client.post(
        "/api/resume", json={"session_id": session_id, "value": "مهم نیست"}
    ).json()

    assert resumed["slots"].get("location_skipped") is True
    assert resumed["pending"] is None, "the skipped slot must not be asked again"
    assert resumed["cards"], "skipping location should still produce cards"


def test_budget_answer_is_mapped_before_understand(client):
    session_id = _session(client)
    data = client.post(
        "/api/chat", json={"session_id": session_id, "text": "گوشی سامسونگ"}
    ).json()
    assert data["pending"]["id"] == "q_budget"

    after_budget = client.post(
        "/api/resume", json={"session_id": session_id, "value": "تا ۶۰ میلیون"}
    ).json()
    assert after_budget["slots"]["budget_max"] == 60_000_000
    assert after_budget["pending"] is not None
    assert after_budget["pending"]["id"] == "q_location"

    final = client.post(
        "/api/resume", json={"session_id": session_id, "value": "مهم نیست"}
    ).json()
    assert final["pending"] is None
    assert final["slots"].get("location_skipped") is True
    assert final["cards"]
