"""Canonical HMAC signing compatible with the Super App Platform API."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any


def build_request_signature_payload(
    *,
    app_id: str,
    key_id: str,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    body: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    body_json = json.dumps(body or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return {
        "app_id": app_id,
        "key_id": key_id,
        "method": method.upper(),
        "path": path,
        "timestamp": timestamp,
        "nonce": nonce,
        "body_sha256": hashlib.sha256(body_json.encode("utf-8")).hexdigest(),
    }


class GatewaySecurity:
    @staticmethod
    def generate_signature(secret_key: str, payload: Mapping[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hmac.new(secret_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()

    @classmethod
    def verify_signature(cls, secret_key: str, payload: Mapping[str, Any], expected_signature: str) -> bool:
        return hmac.compare_digest(cls.generate_signature(secret_key, payload), expected_signature)
