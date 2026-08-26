# EventBooking - Thông tin đăng ký Mini App

File này dùng để điền form Partner Registration cho mini-app EventBooking đã deploy tại:

```text
https://eventbooking-i19e.onrender.com
```

Không đưa `OUTBOUND_API_KEY`, token, password hoặc Supabase key vào form mô tả công khai hay OpenAPI JSON.

## 1. Thông tin cơ bản

| Trường trên form | Giá trị cần điền |
|---|---|
| Mã dịch vụ | `EVENT_BOOKING` |
| Tên dịch vụ | `Đặt Vé Sự Kiện & Hội Nghị` |
| Mô tả chi tiết | `Mini-app hỗ trợ tìm kiếm sự kiện, xem chi tiết, ước tính giá vé, đặt vé, kiểm tra trạng thái đơn vé và hủy vé. Dữ liệu hiện là demo in-memory, phù hợp kiểm thử luồng Super App và Agent.` |
| Danh mục | `EVENTS` hoặc `ENTERTAINMENT` |
| Base URL API | `https://eventbooking-i19e.onrender.com` |
| Health Check URL | `https://eventbooking-i19e.onrender.com/health` |
| Dịch vụ nhạy cảm | `Bật` |
| Outbound API Key | Để trống khi demo, hoặc tự tạo secret riêng và chỉ điền trong ô secret của dashboard |

Ghi chú: Guide khuyến nghị mã dịch vụ chữ thường, nhưng backend EventBooking hiện trả `SERVICE_CODE=EVENT_BOOKING`. Khi đăng ký bản này, nên giữ `EVENT_BOOKING` để khớp backend và tài liệu mini-app hiện tại.

## 2. Cấu hình API

Chọn cách tải OpenAPI JSON và upload file:

```text
eventbooking-openapi.json
```

File này đã được tạo từ endpoint deploy:

```text
https://eventbooking-i19e.onrender.com/openapi.json
```

và đã chuẩn hóa `servers[0].url` + deep-link về đúng domain:

```text
https://eventbooking-i19e.onrender.com
```

Các endpoint trong spec:

| Method | Endpoint | Operation ID | Mục đích |
|---|---|---|---|
| `GET` | `/health` | `health_check` | Kiểm tra mini-app hoạt động |
| `GET` | `/events` | `search_events` | Tìm sự kiện theo thành phố, từ khóa, danh mục, ngày, ngân sách |
| `GET` | `/events/{event_id}` | `get_event_detail` | Xem chi tiết một sự kiện |
| `GET` | `/tickets/estimate` | `estimate_ticket_price` | Ước tính tổng tiền vé |
| `POST` | `/bookings` | `create_event_booking` | Đặt vé sau khi người dùng xác nhận |
| `GET` | `/bookings/{booking_id}` | `get_booking_status` | Kiểm tra trạng thái đơn vé |
| `POST` | `/bookings/{booking_id}/cancel` | `cancel_event_booking` | Hủy đơn vé sau khi người dùng xác nhận |

Các endpoint mutation đã có metadata:

```json
{
  "x-risk-level": "high",
  "x-side-effect-type": "mutation",
  "x-requires-hitl": true,
  "x-idempotency-required": true,
  "x-retry-policy": "no_retry"
}
```

## 3. Cấu hình AI

| Trường trên form | Giá trị cần điền |
|---|---|
| Deep Link Template | `https://eventbooking-i19e.onrender.com/checkout/{booking_id}` |
| Sample Intents | Xem danh sách bên dưới |
| Required Scopes | Để trống hoặc `end_user` |

Sample intents đề xuất:

```text
tìm sự kiện ở Hà Nội
đặt vé sự kiện AI Summit
có sự kiện âm nhạc nào ở TP Hồ Chí Minh không
ước tính giá vé sự kiện
đặt 2 vé VIP cho sự kiện
kiểm tra trạng thái đơn vé
hủy đơn đặt vé sự kiện
có sự kiện nào phù hợp ngân sách 500 nghìn không
```

## 4. Kiểm tra trước khi gửi duyệt

- [x] Base URL public truy cập được.
- [x] `GET /health` trả `200` với body `status=success`.
- [x] OpenAPI JSON có `openapi`, `info`, `servers`, `paths`.
- [x] Mỗi operation có `operationId` riêng.
- [x] Mutation có `Idempotency-Key` và HITL metadata.
- [x] Không đưa secret vào JSON hoặc Markdown.
- [ ] Nếu đặt `Outbound API Key`, cấu hình cùng giá trị đó trên Render env `OUTBOUND_API_KEY`.
- [ ] Sau khi đăng ký, admin cần approve/publish service trong Catalog.

## 5. Lệnh kiểm tra nhanh

Git Bash:

```bash
curl "https://eventbooking-i19e.onrender.com/health"
curl "https://eventbooking-i19e.onrender.com/events"
curl "https://eventbooking-i19e.onrender.com/openapi.json"
```

PowerShell:

```powershell
curl.exe https://eventbooking-i19e.onrender.com/health
curl.exe https://eventbooking-i19e.onrender.com/events
curl.exe https://eventbooking-i19e.onrender.com/openapi.json
```
