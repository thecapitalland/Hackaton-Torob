"""End-to-end API smoke tests (FastAPI TestClient, LLM off)."""

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


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["catalog_rows"]["products"] > 0
    assert data["llm_mode"] == "off"
    assert data["tz"] == "Asia/Tehran"


def test_session(client):
    response = client.post("/api/session")
    assert response.status_code == 200
    assert response.json()["session_id"].startswith("s_")


def test_full_journey(client):
    session_id = client.post("/api/session").json()["session_id"]

    chat = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "text": "یه هدفون بلوتوثی خوب می‌خوام زیر ۴ میلیون، امروز حضوری نزدیک فردوسی",
        },
    )
    assert chat.status_code == 200
    data = chat.json()
    assert data["session_id"] == session_id
    assert data["slots"]["budget_max"] == 4_000_000
    assert data["slots"]["category"] == "هدفون، هدست و هندزفری"

    # either a clarifying question is pending, or we already have cards
    if data["pending"]:
        assert data["pending"]["type"] == "question"
        assert data["pending"]["chips"][-1] == "مهم نیست"
        resume = client.post(
            "/api/resume", json={"session_id": session_id, "value": "آره، قسطی"}
        )
        assert resume.status_code == 200
        data = resume.json()

    assert data["phase"] == "recommend"
    assert data["cards"], "no product cards returned"
    assert data["cards"][0]["kind"] == "best"
    assert data["specialty_market"]["market_id"] == "jomhouri_hafez"
    assert data["specialty_market"]["shops_in_market"] > 0

    product_id = data["cards"][0]["product_id"]
    stores = client.post(
        "/api/select_product", json={"session_id": session_id, "product_id": product_id}
    ).json()
    assert stores["phase"] == "stores"
    assert stores["shops"], "no shops returned"
    shop = stores["shops"][0]
    assert shop["price"] > 0
    assert shop["open_status"] in {"open", "closed", "unknown"}
    assert "transparency" in shop
    assert 0 <= shop["transparency"]["score"] <= 5

    verify = client.post(
        "/api/verify", json={"session_id": session_id, "shop_ids": [shop["shop_id"]]}
    ).json()
    assert verify["pending"]["type"] == "approval"
    assert verify["pending"]["message"]

    approved = client.post(
        "/api/resume",
        json={
            "session_id": session_id,
            "value": {
                "approved": True,
                "shop_ids": [shop["shop_id"]],
                "message": verify["pending"]["message"],
                "channel": "simulated_sms",
            },
        },
    ).json()
    assert approved["phase"] == "verify"
    assert approved["followups"], "no followups returned"
    followup = approved["followups"][0]
    assert followup["simulated"] is True
    assert followup["delay_ms"] > 0
    assert followup["parsed"] is not None

    trip = client.post(
        "/api/trip", json={"session_id": session_id, "shop_ids": [shop["shop_id"]]}
    ).json()
    assert trip["phase"] == "trip"
    assert trip["trip"]["stops"]
    assert trip["trip"]["checklist"]
    # Update #1: the Neshan deep link is the mobile directions URL
    neshan_url = trip["trip"]["links"]["neshan"]
    assert neshan_url.startswith("https://nshn.ir/?destination=")
    assert trip["trip"]["links"]["balad"].startswith("https://balad.ir/directions/driving?destination=")


def test_reject_path(client):
    session_id = client.post("/api/session").json()["session_id"]
    client.post(
        "/api/chat", json={"session_id": session_id, "text": "هدفون بلوتوثی زیر ۴ میلیون"}
    )
    data = client.post("/api/select_product", json={"session_id": session_id, "product_id": "product_92ac53fa75e18e8e73f20b56"}).json()
    shop_id = data["shops"][0]["shop_id"]
    client.post("/api/verify", json={"session_id": session_id, "shop_ids": [shop_id]})
    rejected = client.post(
        "/api/resume",
        json={"session_id": session_id, "value": {"approved": False, "shop_ids": [], "message": ""}},
    ).json()
    assert rejected["phase"] == "stores"
    assert any("پیامی ارسال نشد" in message["content"] for message in rejected["messages"])


def test_out_of_catalog(client):
    session_id = client.post("/api/session").json()["session_id"]
    data = client.post(
        "/api/chat", json={"session_id": session_id, "text": "زعفران و ادویه فله"}
    ).json()
    assert data["phase"] == "out_of_catalog"
    assert data["mode"] == "out_of_catalog"
    ooc = data["ooc"]
    assert ooc["not_found"] is True
    assert ooc["tips_label"] == "اطلاعات عمومی، نه از داده‌های ترب"
    for tip in ooc["tips"]:
        assert "تومان" not in tip


def test_specialty_market_endpoint(client):
    response = client.get("/api/specialty_market", params={"category": "هدفون، هدست و هندزفری"})
    assert response.status_code == 200
    market = response.json()["market"]
    assert market["market_id"] == "jomhouri_hafez"
    assert market["shops_in_market"] > 0

    laptop = client.get("/api/specialty_market", params={"category": "لپ تاپ و نوت بوک"}).json()
    assert laptop["market"]["market_id"] == "paytakht"
    assert laptop["market"]["data_backed"] is False
    assert laptop["market"]["alt"]["market_id"] == "jomhouri_hafez"
