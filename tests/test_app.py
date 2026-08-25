from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["service_code"] == "EVENT_BOOKING"


def test_search_events():
    response = client.get("/events", params={"city": "Hà Nội"})
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["count"] >= 1
    assert body["data"]["events"][0]["event_id"] == "EVT-HN-AI-2026"


def test_create_booking_is_idempotent():
    payload = {
        "event_id": "EVT-HN-AI-2026",
        "ticket_type": "standard",
        "quantity": 1,
        "attendee_name": "Nguyen Van A",
        "attendee_email": "a@example.com",
        "attendee_phone": "0912345678",
    }
    headers = {"Idempotency-Key": "test-create-booking"}
    first = client.post("/bookings", json=payload, headers=headers)
    second = client.post("/bookings", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["booking_id"] == second.json()["data"]["booking_id"]
    assert first.json()["data"]["checkout_url"].endswith(first.json()["data"]["booking_id"])


def test_openapi_has_agent_metadata():
    spec = client.get("/openapi.json").json()
    operation = spec["paths"]["/bookings"]["post"]
    assert operation["operationId"] == "create_event_booking"
    assert operation["x-idempotency-required"] is True
    assert operation["x-action-url-field"] == "data.checkout_url"
