import pytest
from fastapi.testclient import TestClient

from main import app, success


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


def test_search_events_by_price_range():
    response = client.get("/events", params={"min_price": 300000, "max_price": 500000})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    for event in body["data"]["events"]:
        assert event["min_price"] <= 500000
        assert event["max_price"] >= 300000


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
    assert first.json()["operation_id"].startswith("event-booking-create-")
    assert first.json()["data"]["booking_id"] == second.json()["data"]["booking_id"]
    assert first.json()["data"]["checkout_url"].endswith(first.json()["data"]["booking_id"])


def test_idempotency_conflict_for_different_payload():
    first_payload = {
        "event_id": "EVT-HN-AI-2026",
        "ticket_type": "standard",
        "quantity": 1,
        "attendee_name": "Nguyen Van A",
        "attendee_email": "a@example.com",
        "attendee_phone": "0912345678",
    }
    second_payload = {**first_payload, "quantity": 2}
    headers = {"Idempotency-Key": "test-create-booking-conflict"}

    first = client.post("/bookings", json=first_payload, headers=headers)
    second = client.post("/bookings", json=second_payload, headers=headers)

    assert first.json()["status"] == "success"
    assert second.json()["status"] == "failure"
    assert second.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_invalid_operation_id_is_rejected_before_response():
    with pytest.raises(ValueError):
        success({}, "invalid", operation_id="Booking_EVB-1")


def test_validation_error_uses_partner_failure_envelope():
    response = client.post(
        "/bookings",
        json={"event_id": "EVT-HN-AI-2026"},
        headers={"Idempotency-Key": "test-invalid-body"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "failure"
    assert body["error"]["code"] == "INVALID_REQUEST"


def test_openapi_has_agent_metadata():
    spec = client.get("/openapi.json").json()
    operation = spec["paths"]["/bookings"]["post"]
    assert operation["operationId"] == "create_event_booking"
    assert operation["x-idempotency-required"] is True
    assert operation["x-action-url-field"] == "data.checkout_url"
    assert operation["x-superapp"] == {
        "capability": "event.booking.create",
        "sideEffect": "create",
        "riskLevel": "high",
        "requiresConfirmation": True,
        "idempotency": "required",
    }


def test_cancel_booking_has_top_level_booking_id():
    payload = {
        "event_id": "EVT-HN-AI-2026",
        "ticket_type": "standard",
        "quantity": 1,
        "attendee_name": "Nguyen Van B",
        "attendee_email": "b@example.com",
        "attendee_phone": "0912345678",
    }
    create_res = client.post("/bookings", json=payload, headers={"Idempotency-Key": "test-create-for-cancel"})
    booking_id = create_res.json()["data"]["booking_id"]

    cancel_res = client.post(
        f"/bookings/{booking_id}/cancel",
        json={"reason": "Ban viec đột xuất"},
        headers={"Idempotency-Key": "test-cancel-booking"},
    )
    body = cancel_res.json()
    assert cancel_res.status_code == 200
    assert body["status"] == "success"
    assert body["operation_id"].startswith("event-booking-cancel-")
    assert body["data"]["booking_id"] == booking_id
    assert body["data"]["status"] == "CANCELLED"


def test_update_booking_success():
    payload = {
        "event_id": "EVT-HN-AI-2026",
        "ticket_type": "standard",
        "quantity": 1,
        "attendee_name": "Nguyen Van C",
        "attendee_email": "c@example.com",
        "attendee_phone": "0912345678",
    }
    create_res = client.post("/bookings", json=payload, headers={"Idempotency-Key": "test-create-for-update"})
    booking_id = create_res.json()["data"]["booking_id"]

    update_res = client.patch(
        f"/bookings/{booking_id}",
        json={"attendee_name": "Nguyen Van C Updated", "attendee_phone": "0988888888"},
        headers={"Idempotency-Key": "test-update-booking"},
    )
    body = update_res.json()
    assert update_res.status_code == 200
    assert body["status"] == "success"
    assert body["operation_id"].startswith("event-booking-update-")
    assert body["data"]["booking_id"] == booking_id
    assert body["data"]["attendee_name"] == "Nguyen Van C Updated"
    assert body["data"]["attendee_phone"] == "0988888888"


def test_search_events_by_specific_date():
    response = client.get("/events", params={"event_date": "2026-09-02"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["count"] == 1
    assert body["data"]["events"][0]["event_id"] == "EVT-HN-AI-2026"


def test_pay_booking_success():
    payload = {
        "event_id": "EVT-HN-AI-2026",
        "ticket_type": "standard",
        "quantity": 1,
        "attendee_name": "Nguyen Van Pay",
        "attendee_email": "pay@example.com",
        "attendee_phone": "0912345678",
    }
    create_res = client.post("/bookings", json=payload, headers={"Idempotency-Key": "test-create-for-pay"})
    booking_id = create_res.json()["data"]["booking_id"]
    assert create_res.json()["data"]["status"] == "PENDING_PAYMENT"

    pay_res = client.post(
        f"/bookings/{booking_id}/pay",
        json={"payment_method": "SUPERAPP_PAY"},
        headers={"Idempotency-Key": "test-pay-booking"},
    )
    body = pay_res.json()
    assert pay_res.status_code == 200
    assert body["status"] == "success"
    assert body["operation_id"].startswith("event-booking-pay-")
    assert body["data"]["booking_id"] == booking_id
    assert body["data"]["status"] == "PAID"
    assert body["data"]["payment_method"] == "SUPERAPP_PAY"
    assert "paid_at" in body["data"]


def test_pay_cancelled_booking_fails():
    payload = {
        "event_id": "EVT-HN-AI-2026",
        "ticket_type": "standard",
        "quantity": 1,
        "attendee_name": "Nguyen Van CancelPay",
        "attendee_email": "cancelpay@example.com",
        "attendee_phone": "0912345678",
    }
    create_res = client.post("/bookings", json=payload, headers={"Idempotency-Key": "test-create-cancel-pay"})
    booking_id = create_res.json()["data"]["booking_id"]

    client.post(
        f"/bookings/{booking_id}/cancel",
        json={"reason": "Hủy đơn"},
        headers={"Idempotency-Key": "test-cancel-before-pay"},
    )

    pay_res = client.post(
        f"/bookings/{booking_id}/pay",
        json={"payment_method": "SUPERAPP_PAY"},
        headers={"Idempotency-Key": "test-pay-cancelled"},
    )
    body = pay_res.json()
    assert pay_res.status_code == 200
    assert body["status"] == "failure"
    assert body["error"]["code"] == "CONFLICT"


