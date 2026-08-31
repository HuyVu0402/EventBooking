# EventBooking - Thông tin điền form đăng ký Mini App

File này dùng để điền nhanh hồ sơ đăng ký EventBooking lên Super App.

## 1. Thông tin cơ bản

| Trường trên form | Giá trị cần điền |
|---|---|
| Mã dịch vụ | `EVENT_BOOKING` |
| Tên dịch vụ | `Đặt Vé Sự Kiện & Hội Nghị` |
| Mô tả chi tiết | `Mini-app hỗ trợ tìm kiếm sự kiện, xem chi tiết sự kiện, ước tính tổng tiền vé, đặt vé, kiểm tra trạng thái đơn vé và hủy vé. API được chuẩn hóa theo Super App Mini App SDK, có operationId ổn định, Idempotency-Key cho mutation, operation_id cho thao tác tạo/hủy và metadata OpenAPI để Agent chọn endpoint.` |
| Danh mục | `EVENTS` hoặc `ENTERTAINMENT` |
| Base URL API | `https://eventbooking-i19e.onrender.com` |
| Health Check URL | `https://eventbooking-i19e.onrender.com/health` |
| Dịch vụ nhạy cảm | `Bật` |
| Outbound API Key | Để trống khi demo. Nếu bật xác thực, tự tạo secret riêng và chỉ điền trong ô secret của dashboard. Không ghi secret vào Markdown, OpenAPI hoặc mô tả công khai. |

## 2. Cấu hình API

Chọn upload file OpenAPI JSON:

```text
eventbooking-openapi.json
```

Endpoint OpenAPI runtime:

```text
https://eventbooking-i19e.onrender.com/openapi.json
```

OpenAPI đã khai báo:

| Method | Endpoint | Operation ID | Capability | Side effect | HITL | Idempotency |
|---|---|---|---|---|---|---|
| `GET` | `/health` | `health_check` | `event.health.read` | `read` | Không | Không |
| `GET` | `/events` | `search_events` | `event.search` | `read` | Không | Không |
| `GET` | `/events/{event_id}` | `get_event_detail` | `event.detail.read` | `read` | Không | Không |
| `GET` | `/tickets/estimate` | `estimate_ticket_price` | `event.ticket.estimate` | `read` | Không | Không |
| `POST` | `/bookings` | `create_event_booking` | `event.booking.create` | `create` | Có | Bắt buộc |
| `GET` | `/bookings/{booking_id}` | `get_booking_status` | `event.booking.status.read` | `read` | Không | Không |
| `POST` | `/bookings/{booking_id}/cancel` | `cancel_event_booking` | `event.booking.cancel` | `cancel` | Có | Bắt buộc |

Mutation cần header:

```text
Idempotency-Key: <khóa ổn định cho cùng một thao tác>
```

Nếu dùng Outbound API Key, Super App Gateway sẽ gửi:

```text
x-api-key: <giá trị đã đăng ký trong dashboard>
```

## 3. Cấu hình AI

| Trường trên form | Giá trị cần điền |
|---|---|
| Deep Link Template | `https://eventbooking-i19e.onrender.com/checkout/{booking_id}` |
| Required Scopes | Để trống hoặc `end_user` |
| Sample Intents | Dùng danh sách bên dưới |

Sample intents:

```text
tìm sự kiện ở Hà Nội
tìm sự kiện âm nhạc ở TP Hồ Chí Minh
có sự kiện nào ở Đà Nẵng không
ước tính giá vé sự kiện AI Summit
đặt 2 vé VIP cho sự kiện AI Summit
đặt vé sinh viên cho sự kiện startup
kiểm tra trạng thái đơn vé
hủy đơn đặt vé sự kiện
có sự kiện nào phù hợp ngân sách 500 nghìn không
```

## 4. Checklist trước khi gửi duyệt

- [x] Base URL public: `https://eventbooking-i19e.onrender.com`
- [x] Health check: `https://eventbooking-i19e.onrender.com/health`
- [x] OpenAPI có `servers[0].url` đúng production URL.
- [x] Mỗi endpoint có `operationId` ổn định.
- [x] Mỗi endpoint có metadata `x-superapp`.
- [x] Mutation có `Idempotency-Key`, `x-idempotency-required: true` và `x-requires-hitl: true`.
- [x] Response mutation thành công có `operation_id` đúng định dạng SDK, ví dụ `event-booking-create-evb-xxxxxxxx`.
- [x] Lỗi nghiệp vụ dùng envelope `status: failure` và `error.code` ổn định.
- [x] Không đưa secret, JWT, API key hoặc Supabase key vào Markdown/OpenAPI.
- [ ] Nếu cấu hình Outbound API Key trên Super App, đặt cùng giá trị trong biến môi trường backend `OUTBOUND_API_KEY`.
- [ ] Sau khi submit, admin cần approve/publish service trong Catalog.

## 5. Lệnh kiểm tra nhanh

PowerShell:

```powershell
curl.exe https://eventbooking-i19e.onrender.com/health
curl.exe https://eventbooking-i19e.onrender.com/events
curl.exe https://eventbooking-i19e.onrender.com/openapi.json
```

Git Bash:

```bash
curl "https://eventbooking-i19e.onrender.com/health"
curl "https://eventbooking-i19e.onrender.com/events"
curl "https://eventbooking-i19e.onrender.com/openapi.json"
```
