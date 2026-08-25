from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, Header, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator


SERVICE_CODE = os.getenv("SERVICE_CODE", "EVENT_BOOKING")
OUTBOUND_API_KEY = os.getenv("OUTBOUND_API_KEY", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8101")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


app = FastAPI(
    title="Event Booking Mini App",
    version="1.0.0",
    description=(
        "Mini-app dat ve su kien tich hop Super App. "
        "Cac endpoint co OpenAPI metadata de Agent co the tim kiem, uoc tinh gia, dat ve va huy ve."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PartnerEnvelope(BaseModel):
    status: Literal["success", "error"]
    message: str
    data: dict[str, Any] | None = None
    code: str | None = None


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


def success(data: dict[str, Any], message: str) -> dict[str, Any]:
    return PartnerEnvelope(status="success", message=message, data=data).model_dump(exclude_none=True)


def business_error(message: str, code: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return PartnerEnvelope(status="error", message=message, code=code, data=data).model_dump(exclude_none=True)


EVENTS: dict[str, dict[str, Any]] = {
    "EVT-HN-AI-2026": {
        "event_id": "EVT-HN-AI-2026",
        "title": "AI Summit Hanoi 2026",
        "category": "conference",
        "city": "Hà Nội",
        "venue": "Trung tâm Hội nghị Quốc gia",
        "start_time": "2026-09-18T09:00:00+07:00",
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
        "start_time": "2026-10-03T19:30:00+07:00",
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
        "start_time": "2026-11-12T08:30:00+07:00",
        "description": "Triển lãm startup, pitching, networking và khu tuyển dụng công nghệ.",
        "ticket_prices": {"standard": 200000, "vip": 650000, "student": 120000},
        "remaining_tickets": 200,
    },
}

BOOKINGS: dict[str, dict[str, Any]] = {}
IDEMPOTENCY_RESULTS: dict[str, dict[str, Any]] = {}


def verify_api_key(x_api_key: str | None) -> dict[str, Any] | None:
    if OUTBOUND_API_KEY and x_api_key != OUTBOUND_API_KEY:
        return business_error("API key không hợp lệ", "INVALID_API_KEY")
    return None


def build_checkout_url(booking_id: str) -> str:
    return f"{PUBLIC_BASE_URL.rstrip('/')}/checkout/{booking_id}"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home() -> str:
    return """
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Event Booking</title>
  <style>
    :root { color-scheme: light; font-family: Inter, Arial, sans-serif; }
    body { margin: 0; background: #f7f8fb; color: #172033; }
    header { padding: 28px 24px; background: #ffffff; border-bottom: 1px solid #e3e7ef; }
    main { max-width: 1040px; margin: 0 auto; padding: 24px; display: grid; gap: 18px; }
    h1 { margin: 0 0 6px; font-size: 28px; }
    h2 { margin: 0 0 12px; font-size: 18px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }
    .card, form { background: #fff; border: 1px solid #e3e7ef; border-radius: 8px; padding: 16px; }
    label { display: grid; gap: 6px; font-size: 13px; font-weight: 600; color: #33415c; }
    input, select, button { height: 40px; border-radius: 6px; border: 1px solid #cfd6e4; padding: 0 10px; font: inherit; }
    button { background: #1769e0; color: white; border-color: #1769e0; cursor: pointer; font-weight: 700; }
    form { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; align-items: end; }
    .muted { color: #66748a; }
    .price { font-weight: 700; color: #0f7b56; }
    pre { white-space: pre-wrap; background: #101828; color: #f7f8fb; border-radius: 8px; padding: 14px; overflow: auto; }
  </style>
</head>
<body>
  <header>
    <h1>Event Booking</h1>
    <div class="muted">Mini-app đặt vé sự kiện cho Super App</div>
  </header>
  <main>
    <section>
      <h2>Sự kiện</h2>
      <div id="events" class="grid"></div>
    </section>
    <section>
      <h2>Đặt vé nhanh</h2>
      <form id="bookingForm">
        <label>Mã sự kiện <input name="event_id" required value="EVT-HN-AI-2026" /></label>
        <label>Loại vé
          <select name="ticket_type"><option value="standard">standard</option><option value="vip">vip</option><option value="student">student</option></select>
        </label>
        <label>Số lượng <input name="quantity" type="number" min="1" max="10" required value="1" /></label>
        <label>Họ tên <input name="attendee_name" required value="Nguyen Van A" /></label>
        <label>Email <input name="attendee_email" type="email" required value="a@example.com" /></label>
        <label>Điện thoại <input name="attendee_phone" required value="0912345678" /></label>
        <button type="submit">Đặt vé</button>
      </form>
    </section>
    <section>
      <h2>Kết quả</h2>
      <pre id="output">Chưa có thao tác.</pre>
    </section>
  </main>
  <script>
    const output = document.querySelector('#output');
    async function loadEvents() {
      const res = await fetch('/events');
      const body = await res.json();
      document.querySelector('#events').innerHTML = body.data.events.map(event => `
        <article class="card">
          <h3>${event.title}</h3>
          <p class="muted">${event.city} · ${event.venue}</p>
          <p>${event.description}</p>
          <p class="price">Từ ${event.min_price.toLocaleString('vi-VN')} VND</p>
        </article>
      `).join('');
    }
    document.querySelector('#bookingForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const payload = Object.fromEntries(new FormData(event.target).entries());
      payload.quantity = Number(payload.quantity);
      const res = await fetch('/bookings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID()},
        body: JSON.stringify(payload)
      });
      output.textContent = JSON.stringify(await res.json(), null, 2);
    });
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
    return f"""
<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>Thanh toán vé</title>
<style>body{{font-family:Arial,sans-serif;margin:40px;max-width:720px}}.box{{border:1px solid #ddd;border-radius:8px;padding:20px}}button{{padding:12px 18px;background:#1769e0;color:#fff;border:0;border-radius:6px}}</style>
</head><body><div class="box"><h1>Thanh toán vé</h1><p>Mã đơn: <b>{booking_id}</b></p><p>Sự kiện: {booking['event_title']}</p><p>Tổng tiền: <b>{amount} VND</b></p><button>Thanh toán demo</button></div></body></html>
"""


@app.get(
    "/health",
    operation_id="health_check",
    summary="Kiểm tra trạng thái mini-app đặt vé sự kiện",
    openapi_extra={"x-risk-level": "low", "x-side-effect-type": "read", "x-timeout-ms": 3000},
)
async def health() -> dict[str, Any]:
    return success(
        {
            "service_code": SERVICE_CODE,
            "status": "ok",
            "storage": "supabase_configured" if SUPABASE_URL and (SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE_KEY) else "memory",
            "time": datetime.now(timezone.utc).isoformat(),
        },
        "Mini-app đang hoạt động",
    )


@app.get(
    "/events",
    operation_id="search_events",
    summary="Tìm sự kiện phù hợp để người dùng xem và chọn vé",
    description="Dùng endpoint này khi người dùng muốn tìm sự kiện theo thành phố, từ khóa, danh mục, ngày hoặc ngân sách.",
    openapi_extra={
        "x-risk-level": "low",
        "x-side-effect-type": "read",
        "x-retry-policy": "safe_retry",
        "x-deep-link-template": f"{PUBLIC_BASE_URL}/",
    },
)
async def search_events(
    city: str | None = Query(None, description="Thành phố tổ chức sự kiện (VD: Hà Nội, TP. Hồ Chí Minh, Đà Nẵng)"),
    keyword: str | None = Query(None, description="Từ khóa tên hoặc nội dung sự kiện"),
    category: str | None = Query(None, description="Danh mục sự kiện. Giá trị gợi ý: conference | music | expo"),
    start_date: date | None = Query(None, description="Ngày bắt đầu tìm kiếm sự kiện"),
    max_price: int | None = Query(None, ge=0, description="Giá vé tối đa theo VNĐ"),
) -> dict[str, Any]:
    results = []
    for event in EVENTS.values():
        min_price = min(event["ticket_prices"].values())
        haystack = f"{event['title']} {event['description']} {event['venue']}".lower()
        event_date = datetime.fromisoformat(event["start_time"]).date()
        if city and city.lower() not in event["city"].lower():
            continue
        if keyword and keyword.lower() not in haystack:
            continue
        if category and category.lower() != event["category"].lower():
            continue
        if start_date and event_date < start_date:
            continue
        if max_price is not None and min_price > max_price:
            continue
        results.append({**event, "min_price": min_price})
    return success({"events": results, "count": len(results)}, "Tìm sự kiện thành công")


@app.get(
    "/events/{event_id}",
    operation_id="get_event_detail",
    summary="Xem chi tiết một sự kiện trước khi đặt vé",
    description="Dùng endpoint này khi người dùng đã chọn hoặc nhắc tới mã sự kiện và muốn xem chi tiết.",
    openapi_extra={"x-risk-level": "low", "x-side-effect-type": "read", "x-retry-policy": "safe_retry"},
)
async def get_event_detail(event_id: str = Path(..., description="Mã sự kiện cần xem chi tiết")) -> dict[str, Any]:
    event = EVENTS.get(event_id)
    if not event:
        return business_error("Không tìm thấy sự kiện", "EVENT_NOT_FOUND", {"event_id": event_id})
    return success({"event": event}, "Lấy chi tiết sự kiện thành công")


@app.get(
    "/tickets/estimate",
    operation_id="estimate_ticket_price",
    summary="Ước tính tổng tiền vé trước khi đặt",
    description="Dùng endpoint này để báo giá vé dự kiến trước khi người dùng xác nhận đặt vé.",
    openapi_extra={"x-risk-level": "low", "x-side-effect-type": "read", "x-retry-policy": "safe_retry"},
)
async def estimate_ticket_price(
    event_id: str = Query(..., description="Mã sự kiện cần ước tính giá vé"),
    ticket_type: Literal["standard", "vip", "student"] = Query("standard", description="Loại vé. Giá trị hợp lệ: standard | vip | student"),
    quantity: int = Query(..., ge=1, le=10, description="Số lượng vé cần đặt"),
) -> dict[str, Any]:
    event = EVENTS.get(event_id)
    if not event:
        return business_error("Không tìm thấy sự kiện", "EVENT_NOT_FOUND", {"event_id": event_id})
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
    openapi_extra={
        "x-risk-level": "high",
        "x-side-effect-type": "mutation",
        "x-requires-hitl": True,
        "x-idempotency-required": True,
        "x-retry-policy": "no_retry",
        "x-action-url-field": "data.checkout_url",
        "x-deep-link-template": f"{PUBLIC_BASE_URL}/checkout/{{booking_id}}",
    },
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
        return business_error("Thiếu Idempotency-Key cho thao tác đặt vé", "IDEMPOTENCY_KEY_REQUIRED")
    if idempotency_key in IDEMPOTENCY_RESULTS:
        return IDEMPOTENCY_RESULTS[idempotency_key]

    event = EVENTS.get(payload.event_id)
    if not event:
        return business_error("Không tìm thấy sự kiện", "EVENT_NOT_FOUND", {"event_id": payload.event_id})
    if payload.quantity > event["remaining_tickets"]:
        return business_error("Không đủ vé còn lại", "NOT_ENOUGH_TICKETS", {"remaining_tickets": event["remaining_tickets"]})

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
    event["remaining_tickets"] -= payload.quantity
    response = success(booking, "Đặt vé thành công, vui lòng mở link thanh toán để hoàn tất")
    IDEMPOTENCY_RESULTS[idempotency_key] = response
    return response


@app.get(
    "/bookings/{booking_id}",
    operation_id="get_booking_status",
    summary="Kiểm tra trạng thái đơn đặt vé",
    description="Dùng endpoint này khi người dùng hỏi trạng thái thanh toán hoặc thông tin đơn vé đã đặt.",
    openapi_extra={"x-risk-level": "low", "x-side-effect-type": "read", "x-retry-policy": "safe_retry"},
)
async def get_booking_status(booking_id: str = Path(..., description="Mã đơn đặt vé cần kiểm tra")) -> dict[str, Any]:
    booking = BOOKINGS.get(booking_id)
    if not booking:
        return business_error("Không tìm thấy đơn đặt vé", "BOOKING_NOT_FOUND", {"booking_id": booking_id})
    return success({"booking": booking}, "Lấy trạng thái đơn vé thành công")


@app.post(
    "/bookings/{booking_id}/cancel",
    operation_id="cancel_event_booking",
    summary="Hủy đơn đặt vé sau khi người dùng xác nhận",
    description="Dùng endpoint này khi người dùng muốn hủy đơn đặt vé đã tạo.",
    openapi_extra={
        "x-risk-level": "high",
        "x-side-effect-type": "mutation",
        "x-requires-hitl": True,
        "x-idempotency-required": True,
        "x-retry-policy": "no_retry",
    },
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
        return business_error("Thiếu Idempotency-Key cho thao tác hủy vé", "IDEMPOTENCY_KEY_REQUIRED")
    if idem_key in IDEMPOTENCY_RESULTS:
        return IDEMPOTENCY_RESULTS[idem_key]

    booking = BOOKINGS.get(booking_id)
    if not booking:
        return business_error("Không tìm thấy đơn đặt vé", "BOOKING_NOT_FOUND", {"booking_id": booking_id})
    if booking["status"] == "CANCELLED":
        response = success({"booking": booking}, "Đơn vé đã được hủy trước đó")
        IDEMPOTENCY_RESULTS[idem_key] = response
        return response

    booking["status"] = "CANCELLED"
    booking["cancel_reason"] = payload.reason
    booking["cancelled_at"] = datetime.now(timezone.utc).isoformat()
    EVENTS[booking["event_id"]]["remaining_tickets"] += booking["quantity"]
    response = success({"booking": booking}, "Hủy đơn đặt vé thành công")
    IDEMPOTENCY_RESULTS[idem_key] = response
    return response
