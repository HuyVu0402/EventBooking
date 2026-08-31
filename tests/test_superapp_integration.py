from __future__ import annotations

import pytest

import main
from superapp_sdk import GatewaySecurity, build_request_signature_payload


def test_callback_headers_use_env_credential_and_canonical_signature(monkeypatch):
    monkeypatch.setattr(main, "SUPERAPP_APP_ID", "app_event_booking_test")
    monkeypatch.setattr(main, "SUPERAPP_KEY_ID", "key_event_booking_test")
    monkeypatch.setattr(main, "SUPERAPP_API_KEY", "sa_sandbox_test-secret")
    monkeypatch.setattr(main, "SUPERAPP_WEBHOOK_URL", "http://platform.test/api/v1/webhooks/event-status")

    body = {
        "service_code": "EVENT_BOOKING",
        "operation_id": "event-booking-create-evb-1",
        "booking_id": "EVB-1",
        "event_id": "EVT-HN-AI-2026",
        "status": "PENDING_PAYMENT",
    }
    headers = main.build_superapp_callback_headers(body, nonce="nonce-1", timestamp="1700000000")
    signed_payload = build_request_signature_payload(
        app_id="app_event_booking_test",
        key_id="key_event_booking_test",
        method="POST",
        path="/api/v1/webhooks/event-status",
        timestamp="1700000000",
        nonce="nonce-1",
        body=body,
    )

    assert headers["x-app-id"] == "app_event_booking_test"
    assert headers["x-key-id"] == "key_event_booking_test"
    assert headers["x-api-key"] == "sa_sandbox_test-secret"
    assert GatewaySecurity.verify_signature("sa_sandbox_test-secret", signed_payload, headers["x-signature"])


@pytest.mark.asyncio
async def test_notify_superapp_skips_when_credentials_are_missing(monkeypatch):
    monkeypatch.setattr(main, "SUPERAPP_APP_ID", "")
    monkeypatch.setattr(main, "SUPERAPP_KEY_ID", "")
    monkeypatch.setattr(main, "SUPERAPP_API_KEY", "")

    called = False

    async def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(main.httpx, "AsyncClient", fail_if_called)
    assert await main.notify_superapp({"booking_id": "EVB-1", "status": "PENDING_PAYMENT"}) is False
    assert called is False


@pytest.mark.asyncio
async def test_notify_superapp_posts_signed_callback(monkeypatch):
    monkeypatch.setattr(main, "SUPERAPP_APP_ID", "app_event_booking_test")
    monkeypatch.setattr(main, "SUPERAPP_KEY_ID", "key_event_booking_test")
    monkeypatch.setattr(main, "SUPERAPP_API_KEY", "sa_sandbox_test-secret")
    monkeypatch.setattr(main, "SUPERAPP_WEBHOOK_URL", "http://platform.test/api/v1/webhooks/event-status")
    monkeypatch.setattr(main, "SUPERAPP_MINIAPP_ORIGIN", "https://eventbooking-i19e.onrender.com")

    captured = {}

    class Response:
        def raise_for_status(self):
            return None

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json, headers):
            captured.update({"url": url, "body": json, "headers": headers})
            return Response()

    monkeypatch.setattr(main.httpx, "AsyncClient", lambda **kwargs: Client())
    cb_body = {
        "service_code": "EVENT_BOOKING",
        "operation_id": "event-booking-create-evb-1",
        "booking_id": "EVB-1",
        "event_id": "EVT-HN-AI-2026",
        "status": "CONFIRMED",
    }
    assert await main.notify_superapp(cb_body) is True
    assert captured["url"] == "http://platform.test/api/v1/webhooks/event-status"
    assert captured["headers"]["x-miniapp-origin"] == "https://eventbooking-i19e.onrender.com"
    assert captured["body"]["operation_id"] == "event-booking-create-evb-1"
    assert captured["body"]["event_id"] == "EVT-HN-AI-2026"


def test_webhook_url_is_configuration_only(monkeypatch):
    monkeypatch.setattr(main, "SUPERAPP_WEBHOOK_URL", "")
    assert main.SUPERAPP_WEBHOOK_URL == ""
