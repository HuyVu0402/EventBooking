"""Standard Partner Response envelope helpers for Super App integration."""

from __future__ import annotations

import re
from typing import Any

OPERATION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*-[a-z0-9-]{1,126}$")


class PartnerResponse:
    @classmethod
    def success(
        cls,
        data: dict[str, Any] | None = None,
        message: str = "",
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        """Build a standard success response envelope.

        If operation_id is provided, it must conform to the Super App SDK format:
        <domain>-<opaque-id> (e.g. event-booking-123).
        """
        if operation_id and not OPERATION_ID_PATTERN.fullmatch(operation_id):
            raise ValueError(f"operation_id không đúng chuẩn Super App SDK: {operation_id}")

        response: dict[str, Any] = {"status": "success", "message": message}
        if operation_id is not None:
            response["operation_id"] = operation_id
        if data is not None:
            response["data"] = data
        return response

    @classmethod
    def error(
        cls,
        message: str,
        code: str = "PARTNER_ERROR",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a standard error response envelope."""
        return {
            "status": "failure",
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            },
        }
