from __future__ import annotations

import hashlib
import httpx
import json
import os
import re
from datetime import date, datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, Header, Path, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator
from superapp_sdk import GatewaySecurity, PartnerResponse, build_request_signature_payload


SERVICE_CODE = os.getenv("SERVICE_CODE", "EVENT_BOOKING")
OUTBOUND_API_KEY = os.getenv("OUTBOUND_API_KEY", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8501")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPERAPP_APP_ID = os.getenv("SUPERAPP_APP_ID", "")
SUPERAPP_KEY_ID = os.getenv("SUPERAPP_KEY_ID", "")
SUPERAPP_API_KEY = os.getenv("SUPERAPP_API_KEY", "")
SUPERAPP_ENVIRONMENT = os.getenv("SUPERAPP_ENVIRONMENT", "sandbox")
SUPERAPP_WEBHOOK_URL = os.getenv("SUPERAPP_WEBHOOK_URL", "")
SUPERAPP_MINIAPP_ORIGIN = os.getenv("SUPERAPP_MINIAPP_ORIGIN", PUBLIC_BASE_URL.rstrip("/"))
OPERATION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*-[a-z0-9-]{1,126}$")


app = FastAPI(
    title="Event Booking Mini App",
    version="1.0.0",
    description=(
        "Mini-app dat ve su kien tich hop Super App. "
        "Cac endpoint co OpenAPI metadata de Agent co the tim kiem, uoc tinh gia, dat ve va huy ve."
    ),
    servers=[{"url": PUBLIC_BASE_URL.rstrip("/")}],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Any, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content=business_error(
            "Dữ liệu request không hợp lệ",
            "INVALID_REQUEST",
            {"errors": exc.errors()},
        ),
    )


class PartnerEnvelope(BaseModel):
    status: Literal["success"]
    message: str
    operation_id: str | None = None
    data: dict[str, Any] | None = None


class Customer(BaseModel):
    full_name: str | None = Field(None, description="Tên khách hàng từ Super App")
    email: str | None = Field(None, description="Email khách hàng từ Super App")
    username: str | None = Field(None, description="Tên đăng nhập khách hàng từ Super App")

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, value: str | None) -> str | None:
        if value is not None and "@" not in value:
            raise ValueError("Email không hợp lệ")
        return value


class BookingRequest(BaseModel):
    event_id: str = Field(..., description="Mã sự kiện cần đặt vé")
    ticket_type: Literal["standard", "vip", "student"] = Field(
        "standard",
        description="Loại vé. Giá trị hợp lệ: standard | vip | student",
    )
    quantity: int = Field(..., ge=1, le=10, description="Số lượng vé cần đặt")
    attendee_name: str = Field(..., min_length=2, description="Họ tên người tham dự")
    attendee_email: str = Field(..., description="Email nhận vé điện tử")
    attendee_phone: str = Field(..., min_length=8, max_length=20, description="Số điện thoại liên hệ")
    note: str | None = Field(None, max_length=300, description="Ghi chú thêm cho ban tổ chức")
    customer: Customer | None = Field(None, description="Hồ sơ khách hàng do Super App tự đính kèm")

    @field_validator("attendee_email")
    @classmethod
    def validate_attendee_email(cls, value: str) -> str:
        if "@" not in value:
            raise ValueError("Email nhận vé điện tử không hợp lệ")
        return value


class CancelBookingRequest(BaseModel):
    reason: str | None = Field(None, max_length=300, description="Lý do hủy vé")
    customer: Customer | None = Field(None, description="Hồ sơ khách hàng do Super App tự đính kèm")


class UpdateBookingRequest(BaseModel):
    attendee_name: str | None = Field(None, min_length=2, description="Họ tên người tham dự mới")
    attendee_email: str | None = Field(None, description="Email nhận vé điện tử mới")
    attendee_phone: str | None = Field(None, min_length=8, max_length=20, description="Số điện thoại liên hệ mới")
    note: str | None = Field(None, max_length=300, description="Ghi chú mới cho ban tổ chức")
    customer: Customer | None = Field(None, description="Hồ sơ khách hàng do Super App tự đính kèm")

    @field_validator("attendee_email")
    @classmethod
    def validate_optional_attendee_email(cls, value: str | None) -> str | None:
        if value is not None and "@" not in value:
            raise ValueError("Email nhận vé điện tử không hợp lệ")
        return value


class PayRequest(BaseModel):
    payment_method: str | None = Field(
        "SUPERAPP_PAY",
        description="Phương thức thanh toán. Giá trị hợp lệ: SUPERAPP_PAY | MOMO | ZALOPAY | BANK_QR | CARD",
    )
    customer: Customer | None = Field(None, description="Hồ sơ khách hàng do Super App tự đính kèm")



def success(data: dict[str, Any], message: str, operation_id: str | None = None) -> dict[str, Any]:
    return PartnerResponse.success(data=data, message=message, operation_id=operation_id)


def business_error(message: str, code: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return PartnerResponse.error(message=message, code=code, details=data)


def operation_id_for(action: str, resource_id: str) -> str:
    opaque_id = re.sub(r"[^a-z0-9]+", "-", resource_id.lower()).strip("-")
    return f"event-booking-{action}-{opaque_id}"[:128]


def idempotency_fingerprint(scope: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"scope": scope, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def idempotency_response(key: str, fingerprint: str) -> dict[str, Any] | None:
    record = IDEMPOTENCY_RESULTS.get(key)
    if not record:
        return None
    if record["fingerprint"] != fingerprint:
        return business_error(
            "Cùng Idempotency-Key nhưng input khác với lần xử lý trước",
            "IDEMPOTENCY_CONFLICT",
        )
    return record["response"]


def store_idempotency_result(key: str, fingerprint: str, response: dict[str, Any]) -> None:
    IDEMPOTENCY_RESULTS[key] = {"fingerprint": fingerprint, "response": response}


def superapp_metadata(
    *,
    capability: str,
    side_effect: Literal["read", "create", "update", "cancel", "payment"],
    risk_level: Literal["low", "high"],
    requires_confirmation: bool,
    idempotency: Literal["none", "required"],
    **extra: Any,
) -> dict[str, Any]:
    metadata = {
        "x-superapp": {
            "capability": capability,
            "sideEffect": side_effect,
            "riskLevel": risk_level,
            "requiresConfirmation": requires_confirmation,
            "idempotency": idempotency,
        },
        "x-risk-level": risk_level,
        "x-side-effect-type": "read" if side_effect == "read" else "mutation",
        "x-requires-hitl": requires_confirmation,
        "x-idempotency-required": idempotency == "required",
        "x-retry-policy": "safe_retry" if side_effect == "read" else "no_retry",
    }
    metadata.update(extra)
    return metadata


EVENTS: dict[str, dict[str, Any]] = {
    "EVT-HN-AI-2026": {
        "event_id": "EVT-HN-AI-2026",
        "title": "AI Summit Hanoi 2026",
        "category": "conference",
        "city": "Hà Nội",
        "venue": "Trung tâm Hội nghị Quốc gia",
        "start_time": "2026-09-02T09:00:00+07:00",
        "description": "Hội nghị về ứng dụng AI trong sản phẩm, vận hành và giáo dục.",
        "ticket_prices": {"standard": 450000, "vip": 1200000, "student": 250000},
        "remaining_tickets": 120,
    },
    "EVT-HCM-MUSIC-2026": {
        "event_id": "EVT-HCM-MUSIC-2026",
        "title": "Saigon Indie Night",
        "category": "music",
        "city": "TP. Hồ Chí Minh",
        "venue": "Nhà Văn hóa Thanh Niên",
        "start_time": "2026-09-03T19:30:00+07:00",
        "description": "Đêm nhạc indie với các nghệ sĩ trẻ và khu trải nghiệm đồ ăn nhẹ.",
        "ticket_prices": {"standard": 300000, "vip": 800000, "student": 180000},
        "remaining_tickets": 80,
    },
    "EVT-DN-STARTUP-2026": {
        "event_id": "EVT-DN-STARTUP-2026",
        "title": "Da Nang Startup Expo",
        "category": "expo",
        "city": "Đà Nẵng",
        "venue": "Cung Hội nghị Quốc tế Ariyana",
        "start_time": "2026-09-04T08:30:00+07:00",
        "description": "Triển lãm startup, pitching, networking và khu tuyển dụng công nghệ.",
        "ticket_prices": {"standard": 200000, "vip": 650000, "student": 120000},
        "remaining_tickets": 200,
    },
    "EVT-HCM-TECH-2026": {
        "event_id": "EVT-HCM-TECH-2026",
        "title": "Saigon Tech Summit 2026",
        "category": "conference",
        "city": "TP. Hồ Chí Minh",
        "venue": "Gem Center",
        "start_time": "2026-09-05T14:00:00+07:00",
        "description": "Hội thảo công nghệ phần mềm, điện toán đám mây và kết nối đầu tư.",
        "ticket_prices": {"standard": 350000, "vip": 950000, "student": 200000},
        "remaining_tickets": 150,
    },
    "EVT-HN-ART-2026": {
        "event_id": "EVT-HN-ART-2026",
        "title": "Hanoi Contemporary Art Fair",
        "category": "art",
        "city": "Hà Nội",
        "venue": "Bảo tàng Mỹ thuật Việt Nam",
        "start_time": "2026-09-06T18:00:00+07:00",
        "description": "Triển lãm nghệ thuật đương đại, không gian sáng tạo và giao lưu nghệ sĩ.",
        "ticket_prices": {"standard": 150000, "vip": 500000, "student": 100000},
        "remaining_tickets": 90,
    },
}

BOOKINGS: dict[str, dict[str, Any]] = {}
IDEMPOTENCY_RESULTS: dict[str, dict[str, Any]] = {}


def build_superapp_callback_headers(
    body: dict[str, Any],
    *,
    nonce: str,
    timestamp: str,
) -> dict[str, str]:
    """Create headers for a signed Mini App callback to Platform API."""
    path = urlsplit(SUPERAPP_WEBHOOK_URL).path or "/"
    signed_payload = build_request_signature_payload(
        app_id=SUPERAPP_APP_ID,
        key_id=SUPERAPP_KEY_ID,
        method="POST",
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )
    return {
        "x-app-id": SUPERAPP_APP_ID,
        "x-key-id": SUPERAPP_KEY_ID,
        "x-api-key": SUPERAPP_API_KEY,
        "x-miniapp-origin": SUPERAPP_MINIAPP_ORIGIN,
        "x-timestamp": timestamp,
        "x-nonce": nonce,
        "x-signature": GatewaySecurity.generate_signature(SUPERAPP_API_KEY, signed_payload),
    }


async def notify_superapp(body: dict[str, Any]) -> bool:
    """Push an async status update without failing the original Mini App action."""
    if not (SUPERAPP_APP_ID and SUPERAPP_KEY_ID and SUPERAPP_API_KEY and SUPERAPP_WEBHOOK_URL):
        return False
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    nonce = uuid4().hex
    headers = build_superapp_callback_headers(body, nonce=nonce, timestamp=timestamp)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(SUPERAPP_WEBHOOK_URL, json=body, headers=headers)
            response.raise_for_status()
        return True
    except httpx.HTTPError:
        return False


def verify_api_key(x_api_key: str | None) -> dict[str, Any] | None:
    if OUTBOUND_API_KEY and x_api_key != OUTBOUND_API_KEY:
        return business_error("API key không hợp lệ", "UNAUTHORIZED")
    return None


def build_checkout_url(booking_id: str) -> str:
    return f"{PUBLIC_BASE_URL.rstrip('/')}/checkout/{booking_id}"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home() -> str:
    return r"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Event Booking Mini App</title>
  <style>
    :root { font-family: Inter, Arial, sans-serif; color: #172033; background: #f7f8fb; }
    * { box-sizing: border-box; }
    body { margin: 0; }
    header { background: linear-gradient(120deg, #1769e0, #0f4cb3); color: white; padding: 24px 20px; }
    header div, main { max-width: 1040px; margin: 0 auto; }
    h1 { margin: 0 0 4px; font-size: 26px; }
    .muted { color: #66748a; }
    main { padding: 20px; display: grid; gap: 18px; }
    .panel, .card { background: #ffffff; border: 1px solid #e3e7ef; border-radius: 10px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }
    .tag { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 700; background: #e3e7ef; color: #33415c; }
    .tag.warning { background: #fff8e6; color: #b7791f; border: 1px solid #f6e05e; }
    .tag.success { background: #e6fffa; color: #234e52; border: 1px solid #81e6d9; }
    .tag.danger { background: #ffe3e3; color: #9b1c1c; border: 1px solid #feb2b2; }
    form { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; align-items: end; }
    label { display: grid; gap: 6px; font-size: 13px; font-weight: 600; color: #33415c; }
    input, select, button { height: 40px; border-radius: 6px; border: 1px solid #cfd6e4; padding: 0 10px; font: inherit; }
    button { background: #1769e0; color: white; border: 0; cursor: pointer; font-weight: 700; border-radius: 6px; }
    button.secondary { background: #47637d; }
    button.danger { background: #c23b3b; }
    .price { font-weight: 700; color: #0f7b56; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    .pay-banner { background: #fff8e6; border: 1px solid #f6e05e; padding: 14px; border-radius: 8px; margin: 12px 0; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .pay-banner.success { background: #e6fffa; border-color: #319795; }
    pre { white-space: pre-wrap; background: #101828; color: #f7f8fb; border-radius: 8px; padding: 14px; overflow: auto; max-height: 300px; }
    .search-box { display: flex; gap: 10px; margin-bottom: 12px; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Event Booking Mini App</h1>
      <span>Hệ thống đặt vé sự kiện, quản lý đơn vé và thanh toán tích hợp Super App</span>
    </div>
  </header>
  <main>
    <section class="panel">
      <h2>1. Danh sách Sự kiện (Bắt đầu từ 02/09/2026)</h2>
      <div id="events" class="grid"></div>
    </section>

    <section class="panel">
      <h2>2. Đặt vé nhanh</h2>
      <form id="bookingForm">
        <label>Sự kiện
          <select name="event_id" id="eventSelect" required></select>
        </label>
        <label>Loại vé
          <select name="ticket_type" id="ticketTypeSelect"><option value="standard">Standard</option><option value="vip">VIP</option><option value="student">Student</option></select>
        </label>
        <label>Số lượng <input name="quantity" type="number" min="1" max="10" required value="1" /></label>
        <label>Họ tên <input name="attendee_name" required value="Nguyễn Văn A" /></label>
        <label>Email <input name="attendee_email" type="email" required value="a@example.com" /></label>
        <label>Điện thoại <input name="attendee_phone" required value="0912345678" /></label>
        <button type="submit">Đặt vé ngay</button>
      </form>
    </section>

    <section class="panel">
      <h2>3. Đơn đặt vé hiện tại & Thanh toán</h2>
      <div id="bookingBox" class="muted">Chưa chọn đơn vé nào. Hãy đặt vé hoặc nhập mã đơn vé bên dưới.</div>
    </section>

    <section class="panel">
      <h2>4. Tra cứu đơn đặt vé</h2>
      <div class="search-box">
        <input id="searchBookingId" placeholder="Nhập mã đơn vé (VD: EVB-...)" style="flex:1;">
        <button type="button" onclick="searchBooking()">Tra cứu</button>
      </div>
    </section>

    <section>
      <h2>Kết quả API Response</h2>
      <pre id="output">Sẵn sàng.</pre>
    </section>
  </main>
  <script>
    const state = { booking: null };
    const output = document.querySelector('#output');
    const eventSelect = document.querySelector('#eventSelect');

    async function api(url, options) {
      const res = await fetch(url, options);
      const body = await res.json();
      const method = (options?.method || 'GET').toUpperCase();
      if (method !== 'GET') output.textContent = JSON.stringify(body, null, 2);
      return body;
    }

    async function loadEvents() {
      const body = await api('/events');
      if (body.status === 'success') {
        const events = body.data.events;
        eventSelect.innerHTML = events.map(e => `<option value="${e.event_id}">${e.title} (${e.city})</option>`).join('');
        document.querySelector('#events').innerHTML = events.map(e => {
          const dateStr = new Date(e.start_time).toLocaleString('vi-VN', { dateStyle: 'medium', timeStyle: 'short' });
          return `
            <article class="card">
              <span class="tag">${e.category}</span>
              <h3>${e.title}</h3>
              <p class="muted">📍 ${e.city} · ${e.venue}</p>
              <p>⏰ <b>${dateStr}</b></p>
              <p>${e.description}</p>
              <p class="price">Giá từ ${e.min_price.toLocaleString('vi-VN')} VNĐ</p>
            </article>
          `;
        }).join('');
      }
    }

    function renderBooking() {
      if (!state.booking) {
        document.querySelector('#bookingBox').innerHTML = 'Chưa chọn đơn vé nào.';
        return;
      }
      const b = state.booking;
      const isUnpaid = b.status === 'PENDING_PAYMENT';
      const isPaid = b.status === 'PAID';

      let statusBadge = `<span class="tag">${b.status}</span>`;
      if (isUnpaid) statusBadge = `<span class="tag warning">Chờ thanh toán</span>`;
      if (isPaid) statusBadge = `<span class="tag success">Đã thanh toán thành công</span>`;
      if (b.status === 'CANCELLED') statusBadge = `<span class="tag danger">Đã hủy đơn vé</span>`;

      let payBanner = '';
      if (isUnpaid) {
        payBanner = `
          <div class="pay-banner">
            <div><b>Chờ thanh toán:</b> Vui lòng thanh toán số tiền <b>${(b.total_amount || 0).toLocaleString('vi-VN')} VNĐ</b> để nhận vé.</div>
            <button onclick="payBooking()">Thanh toán ngay</button>
          </div>
        `;
      } else if (isPaid) {
        payBanner = `
          <div class="pay-banner success">
            <div><b>Đã thanh toán thành công!</b> Phương thức: <b>${b.payment_method || 'SUPERAPP_PAY'}</b></div>
            <a href="/checkout/${b.booking_id}" target="_blank" style="color:#0f4cb3;font-weight:700;">Xem vé điện tử</a>
          </div>
        `;
      }

      document.querySelector('#bookingBox').innerHTML = `
        <div class="card">
          <h3>Đơn vé: ${b.booking_id}</h3>
          <p><b>Trạng thái:</b> ${statusBadge}</p>
          <p><b>Sự kiện:</b> ${b.event_title}</p>
          <p><b>Người tham dự:</b> ${b.attendee_name} (${b.attendee_email} · ${b.attendee_phone})</p>
          <p><b>Loại vé:</b> ${b.ticket_type} x ${b.quantity} vé</p>
          <p><b>Tổng tiền:</b> <span class="price">${(b.total_amount || 0).toLocaleString('vi-VN')} VNĐ</span></p>
          ${payBanner}
          ${b.status !== 'CANCELLED' ? `
            <div class="actions">
              ${isUnpaid ? `<button onclick="payBooking()">Thanh toán ngay</button>` : ''}
              <a href="/checkout/${b.booking_id}" target="_blank"><button class="secondary" type="button">Trang thanh toán Deep Link</button></a>
              <button class="secondary" onclick="updateBookingInfo()">Cập nhật thông tin</button>
              <button class="danger" onclick="cancelBooking()">Hủy đơn vé</button>
            </div>
          ` : ''}
        </div>
      `;
    }

    document.querySelector('#bookingForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = Object.fromEntries(new FormData(e.target).entries());
      payload.quantity = Number(payload.quantity);
      const body = await api('/bookings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify(payload)
      });
      if (body.status === 'success') {
        state.booking = body.data;
        renderBooking();
      }
    });

    async function payBooking() {
      if (!state.booking) return;
      const body = await api(`/bookings/${state.booking.booking_id}/pay`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ payment_method: 'SUPERAPP_PAY' })
      });
      if (body.status === 'success') {
        state.booking = body.data;
        renderBooking();
      }
    }

    async function cancelBooking() {
      if (!state.booking || !confirm('Bạn chắc chắn muốn hủy đơn vé này?')) return;
      const body = await api(`/bookings/${state.booking.booking_id}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ reason: 'Người dùng hủy trên giao diện demo' })
      });
      if (body.status === 'success') {
        state.booking = body.data;
        renderBooking();
      }
    }

    async function updateBookingInfo() {
      if (!state.booking) return;
      const newName = prompt("Họ tên người tham dự mới:", state.booking.attendee_name);
      const newPhone = prompt("Số điện thoại mới:", state.booking.attendee_phone);
      const payload = {};
      if (newName) payload.attendee_name = newName;
      if (newPhone) payload.attendee_phone = newPhone;

      const body = await api(`/bookings/${state.booking.booking_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify(payload)
      });
      if (body.status === 'success') {
        state.booking = body.data;
        renderBooking();
      }
    }

    async function searchBooking() {
      const q = document.querySelector('#searchBookingId').value.trim();
      if (!q) return;
      const body = await api(`/bookings/${encodeURIComponent(q)}`);
      if (body.status === 'success' && body.data) {
        state.booking = body.data;
        renderBooking();
      }
    }

    loadEvents();
  </script>
</body>
</html>
"""


@app.get("/checkout/{booking_id}", response_class=HTMLResponse, include_in_schema=False)
async def checkout_page(booking_id: str) -> str:
    booking = BOOKINGS.get(booking_id)
    if not booking:
        return "<h1>Không tìm thấy đơn vé</h1>"
    amount = f"{booking['total_amount']:,}".replace(",", ".")
    is_paid = booking.get("status") == "PAID"
    is_cancelled = booking.get("status") == "CANCELLED"

    return f"""
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Thanh toán đơn vé - {booking_id}</title>
  <style>
    body {{ font-family: Inter, Arial, sans-serif; margin: 0; background: #f4f6fa; color: #1a202c; padding: 20px; }}
    .box {{ max-width: 600px; margin: 20px auto; background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
    h1 {{ margin-top: 0; color: #1769e0; font-size: 24px; }}
    .info-item {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #edf2f7; }}
    .info-item:last-child {{ border-bottom: none; }}
    .label {{ color: #718096; font-size: 14px; }}
    .value {{ font-weight: 600; font-size: 14px; text-align: right; }}
    .price-tag {{ color: #0f7b56; font-size: 20px; font-weight: 700; }}
    .badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 13px; }}
    .badge-success {{ background: #c6f6d5; color: #22543d; }}
    .badge-warning {{ background: #feebc8; color: #744210; }}
    .badge-danger {{ background: #fed7d7; color: #742a2a; }}
    .methods {{ display: grid; gap: 10px; margin: 16px 0; }}
    .method-option {{ border: 1px solid #cbd5e0; border-radius: 8px; padding: 12px; display: flex; align-items: center; gap: 10px; cursor: pointer; }}
    .method-option input {{ margin: 0; }}
    button {{ width: 100%; padding: 14px; background: #1769e0; color: white; border: 0; border-radius: 8px; font-weight: 700; font-size: 16px; cursor: pointer; margin-top: 16px; }}
    button:disabled {{ background: #a0aec0; cursor: not-allowed; }}
    .alert {{ padding: 12px; border-radius: 8px; margin-top: 14px; font-weight: 600; text-align: center; }}
    .alert-success {{ background: #c6f6d5; color: #22543d; }}
  </style>
</head>
<body>
  <div class="box">
    <h1>Cổng Thanh toán Vé Sự kiện</h1>
    <div style="margin-bottom: 20px;">
      Status: {'<span class="badge badge-success">Đã thanh toán</span>' if is_paid else ('<span class="badge badge-danger">Đã hủy đơn vé</span>' if is_cancelled else '<span class="badge badge-warning">Chờ thanh toán</span>')}
    </div>

    <div class="info-item">
      <span class="label">Mã đơn vé:</span>
      <span class="value"><b>{booking_id}</b></span>
    </div>
    <div class="info-item">
      <span class="label">Sự kiện:</span>
      <span class="value">{booking['event_title']}</span>
    </div>
    <div class="info-item">
      <span class="label">Người tham dự:</span>
      <span class="value">{booking['attendee_name']} ({booking['attendee_phone']})</span>
    </div>
    <div class="info-item">
      <span class="label">Loại vé / Số lượng:</span>
      <span class="value">{booking['ticket_type']} x {booking['quantity']} vé</span>
    </div>
    <div class="info-item">
      <span class="label">Tổng tiền thanh toán:</span>
      <span class="value price-tag">{amount} VNĐ</span>
    </div>

    {'<div class="alert alert-success">Vé đã được thanh toán thành công vào ' + str(booking.get("paid_at", "")) + '</div>' if is_paid else ''}

    {"" if is_paid or is_cancelled else f'''
    <h3 style="margin-top:20px;font-size:16px;">Chọn phương thức thanh toán:</h3>
    <div class="methods">
      <label class="method-option"><input type="radio" name="pay_method" value="SUPERAPP_PAY" checked> Ví SuperApp Pay</label>
      <label class="method-option"><input type="radio" name="pay_method" value="BANK_QR"> Chuyển khoản QR Banking (VietQR)</label>
      <label class="method-option"><input type="radio" name="pay_method" value="MOMO"> Ví MoMo</label>
      <label class="method-option"><input type="radio" name="pay_method" value="CARD"> Thẻ ATM / VISA / Mastercard</label>
    </div>
    <button id="payBtn" onclick="confirmPayment()">Xác nhận thanh toán ngay ({amount} VNĐ)</button>
    '''}
  </div>

  <script>
    async function confirmPayment() {{
      const btn = document.querySelector('#payBtn');
      if (btn) btn.disabled = true;
      const selected = document.querySelector('input[name="pay_method"]:checked')?.value || 'SUPERAPP_PAY';
      const res = await fetch('/bookings/{booking_id}/pay', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() }},
        body: JSON.stringify({{ payment_method: selected }})
      }});
      const data = await res.json();
      if (data.status === 'success') {{
        alert('Thanh toán đơn vé thành công!');
        window.location.reload();
      }} else {{
        alert('Thanh toán thất bại: ' + data.message);
        if (btn) btn.disabled = false;
      }}
    }}
  </script>
</body>
</html>
"""



@app.get(
    "/health",
    operation_id="health_check",
    summary="Kiểm tra trạng thái mini-app đặt vé sự kiện",
    openapi_extra=superapp_metadata(
        capability="event.health.read",
        side_effect="read",
        risk_level="low",
        requires_confirmation=False,
        idempotency="none",
        **{"x-timeout-ms": 3000},
    ),
)
async def health() -> dict[str, Any]:
    return success(
        {
            "service_code": SERVICE_CODE,
            "status": "ok",
            "storage": "supabase_configured" if SUPABASE_URL and (SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE_KEY) else "memory",
            "superapp_environment": SUPERAPP_ENVIRONMENT,
            "superapp_credentials_configured": bool(SUPERAPP_APP_ID and SUPERAPP_KEY_ID and SUPERAPP_API_KEY),
            "time": datetime.now(timezone.utc).isoformat(),
        },
        "Mini-app đang hoạt động",
    )


@app.get(
    "/events",
    operation_id="search_events",
    summary="Tìm sự kiện phù hợp để người dùng xem và chọn vé",
    description="Dùng endpoint này khi người dùng muốn tìm sự kiện theo thành phố, từ khóa, danh mục, ngày hoặc ngân sách.",
    openapi_extra=superapp_metadata(
        capability="event.search",
        side_effect="read",
        risk_level="low",
        requires_confirmation=False,
        idempotency="none",
        **{"x-deep-link-template": f"{PUBLIC_BASE_URL}/"},
    ),
)
async def search_events(
    city: str | None = Query(None, description="Thành phố tổ chức sự kiện (VD: Hà Nội, TP. Hồ Chí Minh, Đà Nẵng)"),
    keyword: str | None = Query(None, description="Từ khóa tên hoặc nội dung sự kiện"),
    category: str | None = Query(None, description="Danh mục sự kiện. Giá trị gợi ý: conference | music | expo | art"),
    start_date: date | None = Query(None, description="Ngày bắt đầu tìm kiếm sự kiện (YYYY-MM-DD)"),
    event_date: date | None = Query(None, description="Ngày diễn ra sự kiện cụ thể (YYYY-MM-DD)"),
    min_price: int | None = Query(None, ge=0, description="Giá vé tối thiểu theo VNĐ"),
    max_price: int | None = Query(None, ge=0, description="Giá vé tối đa theo VNĐ"),
) -> dict[str, Any]:
    results = []
    for event in EVENTS.values():
        event_min_price = min(event["ticket_prices"].values())
        event_max_price = max(event["ticket_prices"].values())
        haystack = f"{event['title']} {event['description']} {event['venue']}".lower()
        ev_date = datetime.fromisoformat(event["start_time"]).date()
        if city and city.lower() not in event["city"].lower():
            continue
        if keyword and keyword.lower() not in haystack:
            continue
        if category and category.lower() != event["category"].lower():
            continue
        if start_date and ev_date < start_date:
            continue
        if event_date and ev_date != event_date:
            continue
        if min_price is not None and event_max_price < min_price:
            continue
        if max_price is not None and event_min_price > max_price:
            continue
        results.append({**event, "min_price": event_min_price, "max_price": event_max_price})
    return success({"events": results, "count": len(results)}, "Tìm sự kiện thành công")


@app.get(
    "/events/{event_id}",
    operation_id="get_event_detail",
    summary="Xem chi tiết một sự kiện trước khi đặt vé",
    description="Dùng endpoint này khi người dùng đã chọn hoặc nhắc tới mã sự kiện và muốn xem chi tiết.",
    openapi_extra=superapp_metadata(
        capability="event.detail.read",
        side_effect="read",
        risk_level="low",
        requires_confirmation=False,
        idempotency="none",
    ),
)
async def get_event_detail(event_id: str = Path(..., description="Mã sự kiện cần xem chi tiết")) -> dict[str, Any]:
    event = EVENTS.get(event_id)
    if not event:
        return business_error("Không tìm thấy sự kiện", "NOT_FOUND", {"event_id": event_id})
    return success({"event": event}, "Lấy chi tiết sự kiện thành công")


@app.get(
    "/tickets/estimate",
    operation_id="estimate_ticket_price",
    summary="Ước tính tổng tiền vé trước khi đặt",
    description="Dùng endpoint này để báo giá vé dự kiến trước khi người dùng xác nhận đặt vé.",
    openapi_extra=superapp_metadata(
        capability="event.ticket.estimate",
        side_effect="read",
        risk_level="low",
        requires_confirmation=False,
        idempotency="none",
    ),
)
async def estimate_ticket_price(
    event_id: str = Query(..., description="Mã sự kiện cần ước tính giá vé"),
    ticket_type: Literal["standard", "vip", "student"] = Query("standard", description="Loại vé. Giá trị hợp lệ: standard | vip | student"),
    quantity: int = Query(..., ge=1, le=10, description="Số lượng vé cần đặt"),
) -> dict[str, Any]:
    event = EVENTS.get(event_id)
    if not event:
        return business_error("Không tìm thấy sự kiện", "NOT_FOUND", {"event_id": event_id})
    unit_price = event["ticket_prices"][ticket_type]
    total_amount = unit_price * quantity
    return success(
        {
            "event_id": event_id,
            "event_title": event["title"],
            "ticket_type": ticket_type,
            "quantity": quantity,
            "unit_price": unit_price,
            "total_amount": total_amount,
            "currency": "VND",
        },
        "Ước tính giá vé thành công",
    )


@app.post(
    "/bookings",
    operation_id="create_event_booking",
    summary="Đặt vé sự kiện sau khi người dùng xác nhận",
    description="Dùng endpoint này khi người dùng đã chọn sự kiện, loại vé, số lượng và muốn đặt vé.",
    openapi_extra=superapp_metadata(
        capability="event.booking.create",
        side_effect="create",
        risk_level="high",
        requires_confirmation=True,
        idempotency="required",
        **{
            "x-action-url-field": "data.checkout_url",
            "x-deep-link-template": f"{PUBLIC_BASE_URL}/checkout/{{booking_id}}",
        },
    ),
)
async def create_booking(
    payload: BookingRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_api_key: str | None = Header(None, alias="x-api-key"),
) -> dict[str, Any]:
    key_error = verify_api_key(x_api_key)
    if key_error:
        return key_error
    if not idempotency_key:
        return business_error("Thiếu Idempotency-Key cho thao tác đặt vé", "INVALID_REQUEST")
    fingerprint = idempotency_fingerprint("create_booking", payload.model_dump(mode="json"))
    previous = idempotency_response(idempotency_key, fingerprint)
    if previous:
        return previous

    event = EVENTS.get(payload.event_id)
    if not event:
        return business_error("Không tìm thấy sự kiện", "NOT_FOUND", {"event_id": payload.event_id})
    if payload.quantity > event["remaining_tickets"]:
        return business_error("Không đủ vé còn lại", "CONFLICT", {"remaining_tickets": event["remaining_tickets"]})

    unit_price = event["ticket_prices"][payload.ticket_type]
    booking_id = f"EVB-{uuid4().hex[:8].upper()}"
    booking = {
        "booking_id": booking_id,
        "order_id": booking_id,
        "event_id": payload.event_id,
        "event_title": event["title"],
        "ticket_type": payload.ticket_type,
        "quantity": payload.quantity,
        "unit_price": unit_price,
        "total_amount": unit_price * payload.quantity,
        "currency": "VND",
        "status": "PENDING_PAYMENT",
        "attendee_name": payload.attendee_name,
        "attendee_email": str(payload.attendee_email),
        "attendee_phone": payload.attendee_phone,
        "checkout_url": build_checkout_url(booking_id),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    BOOKINGS[booking_id] = booking
    op_id = operation_id_for("create", booking_id)
    response = success(
        booking,
        "Đặt vé thành công, vui lòng mở link thanh toán để hoàn tất",
        operation_id=op_id,
    )
    store_idempotency_result(idempotency_key, fingerprint, response)
    await notify_superapp(
        {
            "service_code": SERVICE_CODE,
            "operation_id": op_id,
            "booking_id": booking_id,
            "event_id": payload.event_id,
            "status": booking["status"],
            "message": "Đã tạo đơn đặt vé, đang chờ thanh toán.",
        }
    )
    return response

@app.get(
    "/bookings/{booking_id}",
    operation_id="get_booking_status",
    summary="Kiểm tra trạng thái đơn đặt vé",
    description="Dùng endpoint này khi người dùng hỏi trạng thái thanh toán hoặc thông tin đơn vé đã đặt.",
    openapi_extra=superapp_metadata(
        capability="event.booking.status.read",
        side_effect="read",
        risk_level="low",
        requires_confirmation=False,
        idempotency="none",
    ),
)
async def get_booking_status(booking_id: str = Path(..., description="Mã đơn đặt vé cần kiểm tra")) -> dict[str, Any]:
    booking = BOOKINGS.get(booking_id)
    if not booking:
        return business_error("Không tìm thấy đơn đặt vé", "NOT_FOUND", {"booking_id": booking_id})
    return success({"booking": booking}, "Lấy trạng thái đơn vé thành công")


@app.post(
    "/bookings/{booking_id}/cancel",
    operation_id="cancel_event_booking",
    summary="Hủy đơn đặt vé sau khi người dùng xác nhận",
    description="Dùng endpoint này khi người dùng muốn hủy đơn đặt vé đã tạo.",
    openapi_extra=superapp_metadata(
        capability="event.booking.cancel",
        side_effect="cancel",
        risk_level="high",
        requires_confirmation=True,
        idempotency="required",
    ),
)
async def cancel_booking(
    payload: CancelBookingRequest,
    booking_id: str = Path(..., description="Mã đơn đặt vé cần hủy"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_api_key: str | None = Header(None, alias="x-api-key"),
) -> dict[str, Any]:
    key_error = verify_api_key(x_api_key)
    if key_error:
        return key_error
    idem_key = f"cancel:{idempotency_key}" if idempotency_key else None
    if not idem_key:
        return business_error("Thiếu Idempotency-Key cho thao tác hủy vé", "INVALID_REQUEST")
    fingerprint = idempotency_fingerprint(
        "cancel_booking",
        {"booking_id": booking_id, **payload.model_dump(mode="json")},
    )
    previous = idempotency_response(idem_key, fingerprint)
    if previous:
        return previous

    booking = BOOKINGS.get(booking_id)
    if not booking:
        return business_error("Không tìm thấy đơn đặt vé", "NOT_FOUND", {"booking_id": booking_id})
    
    op_id = operation_id_for("cancel", booking_id)
    if booking["status"] == "CANCELLED":
        response = success(booking, "Đơn vé đã được hủy trước đó", operation_id=op_id)
        store_idempotency_result(idem_key, fingerprint, response)
        return response

    booking["status"] = "CANCELLED"
    booking["cancel_reason"] = payload.reason
    booking["cancelled_at"] = datetime.now(timezone.utc).isoformat()
    EVENTS[booking["event_id"]]["remaining_tickets"] += booking["quantity"]
    response = success(booking, "Hủy đơn đặt vé thành công", operation_id=op_id)
    store_idempotency_result(idem_key, fingerprint, response)
    await notify_superapp(
        {
            "service_code": SERVICE_CODE,
            "operation_id": op_id,
            "booking_id": booking_id,
            "event_id": booking["event_id"],
            "status": booking["status"],
            "message": "Đơn đặt vé đã được hủy.",
        }
    )
    return response


@app.patch(
    "/bookings/{booking_id}",
    operation_id="update_event_booking",
    summary="Thay đổi thông tin đơn đặt vé sau khi người dùng xác nhận",
    description="Dùng endpoint này khi người dùng muốn đổi tên, email, số điện thoại hoặc ghi chú cho đơn vé đã đặt.",
    openapi_extra=superapp_metadata(
        capability="event.booking.update",
        side_effect="update",
        risk_level="high",
        requires_confirmation=True,
        idempotency="required",
    ),
)
async def update_booking(
    payload: UpdateBookingRequest,
    booking_id: str = Path(..., description="Mã đơn đặt vé cần cập nhật"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_api_key: str | None = Header(None, alias="x-api-key"),
) -> dict[str, Any]:
    key_error = verify_api_key(x_api_key)
    if key_error:
        return key_error
    idem_key = f"update:{idempotency_key}" if idempotency_key else None
    if not idem_key:
        return business_error("Thiếu Idempotency-Key cho thao tác thay đổi thông tin vé", "INVALID_REQUEST")
    fingerprint = idempotency_fingerprint(
        "update_booking",
        {"booking_id": booking_id, **payload.model_dump(mode="json", exclude_none=True)},
    )
    previous = idempotency_response(idem_key, fingerprint)
    if previous:
        return previous

    booking = BOOKINGS.get(booking_id)
    if not booking:
        return business_error("Không tìm thấy đơn đặt vé", "NOT_FOUND", {"booking_id": booking_id})
    if booking["status"] == "CANCELLED":
        return business_error("Không thể thay đổi thông tin đơn vé đã bị hủy", "CONFLICT", {"status": "CANCELLED"})

    if payload.attendee_name is not None:
        booking["attendee_name"] = payload.attendee_name
    if payload.attendee_email is not None:
        booking["attendee_email"] = str(payload.attendee_email)
    if payload.attendee_phone is not None:
        booking["attendee_phone"] = payload.attendee_phone
    if payload.note is not None:
        booking["note"] = payload.note

    op_id = operation_id_for("update", booking_id)
    response = success(booking, "Cập nhật thông tin đơn vé thành công", operation_id=op_id)
    store_idempotency_result(idem_key, fingerprint, response)
    await notify_superapp(
        {
            "service_code": SERVICE_CODE,
            "operation_id": op_id,
            "booking_id": booking_id,
            "event_id": booking["event_id"],
            "status": booking["status"],
            "message": "Đã cập nhật thông tin đơn đặt vé.",
        }
    )
    return response


@app.post(
    "/bookings/{booking_id}/pay",
    operation_id="pay_event_booking",
    summary="Xác nhận thanh toán cho đơn đặt vé",
    description="Dùng endpoint này khi người dùng ấn nút thanh toán hoặc khi nhận callback/thông báo thanh toán thành công.",
    openapi_extra=superapp_metadata(
        capability="event.booking.pay",
        side_effect="payment",
        risk_level="high",
        requires_confirmation=True,
        idempotency="required",
    ),
)
async def pay_booking(
    payload: PayRequest,
    booking_id: str = Path(..., description="Mã đơn đặt vé cần thanh toán"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_api_key: str | None = Header(None, alias="x-api-key"),
) -> dict[str, Any]:
    key_error = verify_api_key(x_api_key)
    if key_error:
        return key_error
    idem_key = f"pay:{idempotency_key}" if idempotency_key else None
    if not idem_key:
        return business_error("Thiếu Idempotency-Key cho thao tác thanh toán vé", "INVALID_REQUEST")
    fingerprint = idempotency_fingerprint(
        "pay_booking",
        {"booking_id": booking_id, **payload.model_dump(mode="json", exclude_none=True)},
    )
    previous = idempotency_response(idem_key, fingerprint)
    if previous:
        return previous

    booking = BOOKINGS.get(booking_id)
    if not booking:
        return business_error("Không tìm thấy đơn đặt vé", "NOT_FOUND", {"booking_id": booking_id})
    if booking["status"] == "CANCELLED":
        return business_error("Đơn vé đã bị hủy, không thể thanh toán", "CONFLICT", {"status": "CANCELLED"})

    booking["status"] = "PAID"
    booking["payment_method"] = payload.payment_method or "SUPERAPP_PAY"
    booking["paid_at"] = datetime.now(timezone.utc).isoformat()

    op_id = operation_id_for("pay", booking_id)
    response = success(booking, "Thanh toán đơn vé thành công", operation_id=op_id)
    store_idempotency_result(idem_key, fingerprint, response)
    await notify_superapp(
        {
            "service_code": SERVICE_CODE,
            "operation_id": op_id,
            "booking_id": booking_id,
            "event_id": booking["event_id"],
            "status": "PAID",
            "message": "Đã hoàn tất thanh toán đơn đặt vé.",
        }
    )
    return response

