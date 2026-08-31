# Tiêu chuẩn SDK Mini App của Super App v1

## 1. Mục tiêu

Tài liệu này là hợp đồng tối thiểu dành cho mọi Mini App được đăng ký vào Super App.
Mini App không được tự tạo response tùy ý nếu response đó được Agent xử lý.

## 2. Nguyên tắc bắt buộc

- Mini App phải có `service_code`, `base_url`, OpenAPI và `operationId` ổn định.
- Mọi thao tác thành công có phát sinh side effect phải trả về `operation_id`.
- `operation_id` phải đại diện cho cùng một nghiệp vụ trong các lần retry.
- Không dùng `request_id`, `task_id` hoặc `thread_id` thay cho `operation_id`.
- ID nghiệp vụ phải nằm trong `data` ở cấp cao nhất.
- Không trả secret, JWT, API key hoặc dữ liệu nội bộ trong response.

## 3. Quy tắc ID theo Agent

### 3.1. `operation_id`

Định dạng:

```text
<domain>-<opaque-id>
```

Quy tắc:

- Chỉ dùng chữ thường và chữ số.
- Bắt đầu bằng chữ cái.
- Phải có dấu gạch ngang ngăn cách domain và opaque ID.
- Độ dài tối đa 128 ký tự.
- Ổn định khi retry cùng một nghiệp vụ.

Ví dụ hợp lệ:

```text
ride-123
payment-123
event-booking-abc123
health-appointment-20260831-001
```

Ví dụ không hợp lệ:

```text
Ride-123
ride_123
123
ride
```

### 3.2. Các ID liên quan

| Trường | Mục đích | Ví dụ |
|---|---|---|
| `operation_id` | ID nghiệp vụ chính, bắt buộc với mutation thành công | `ride-123` |
| `booking_id` | ID đặt chỗ/đặt lịch | `BOOK-123` |
| `ride_id` | ID chuyến xe | `RIDE-123` |
| `payment_id` | ID giao dịch thanh toán | `PAY-123` |
| `request_id` | ID của một HTTP request | `req-uuid` |
| `event_id` | ID callback/event, dùng để deduplicate | `evt-uuid` |

`request_id`, `event_id` và `operation_id` không được dùng thay thế cho nhau.

## 4. Success response

```json
{
  "status": "success",
  "message": "Đặt xe thành công",
  "operation_id": "ride-123",
  "data": {
    "ride_id": "RIDE-123",
    "status": "CONFIRMED"
  }
}
```

Với `create`, `update`, `cancel`, `payment` hoặc thao tác có side effect:

- Phải có `operation_id`.
- Phải có ID tài nguyên nếu thao tác tạo/cập nhật tài nguyên.
- Cùng `Idempotency-Key` và cùng input phải trả về cùng operation.

## 5. Error response

```json
{
  "status": "failure",
  "error": {
    "code": "SLOT_UNAVAILABLE",
    "message": "Ca đã được đặt",
    "details": {}
  }
}
```

Code gợi ý:

| Code | Ý nghĩa |
|---|---|
| `INVALID_REQUEST` | Input không hợp lệ |
| `UNAUTHORIZED` | Thiếu hoặc sai xác thực |
| `FORBIDDEN` | Không đủ quyền |
| `DOMAIN_NOT_ALLOWED` | Domain không nằm trong allowlist |
| `INVALID_SIGNATURE` | Chữ ký không đúng |
| `IDEMPOTENCY_CONFLICT` | Cùng key nhưng input khác |
| `NOT_FOUND` | Không tìm thấy tài nguyên |
| `CONFLICT` | Trạng thái nghiệp vụ không cho phép |
| `PARTNER_ERROR` | Lỗi nghiệp vụ của Mini App |

## 6. Yêu cầu OpenAPI

Mỗi operation phải có:

```yaml
operationId: bookRide
x-superapp:
  capability: ride.booking.create
  sideEffect: create
  riskLevel: high
  requiresConfirmation: true
  idempotency: required
```

Operation mutation phải khai báo idempotency. Operation có rủi ro cao phải yêu cầu
người dùng xác nhận trước khi Agent gọi.

## 7. Domain và credential

- Partner khai báo `allowed_domains` khi đăng ký Mini App.
- Platform chỉ chấp nhận request từ domain đã được phê duyệt.
- Secret key chỉ được hiển thị một lần sau khi cấp.
- Database chỉ lưu hash và key prefix, không lưu secret plaintext.
- Không nhúng secret key vào JavaScript public của Mini App.
- Request phải có `app_id`, `key_id`, timestamp, nonce, body hash và signature.

### 7.1. Cấu hình credential cho callback

Sau khi Admin phê duyệt Mini App, Partner Portal cấp một credential. Partner phải
lưu các giá trị này trong backend Mini App, không lưu ở frontend:

```dotenv
SUPERAPP_APP_ID=app_ride_xxxxxxxx
SUPERAPP_KEY_ID=key_xxxxxxxxxxxxxxxxxxxxxxxx
SUPERAPP_API_KEY=sa_sandbox_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SUPERAPP_ENVIRONMENT=sandbox
```

`SUPERAPP_API_KEY` chỉ hiển thị một lần khi issue/rotate. Khi Mini App gọi
callback vào Platform, gửi `x-app-id`, `x-key-id`, `x-api-key`,
`x-miniapp-origin`, `x-timestamp`, `x-nonce`, `x-signature`. Signature là
HMAC-SHA256 của payload tạo bởi
`build_request_signature_payload(app_id, key_id, method, path, timestamp, nonce, body)`.
Không log giá trị `x-api-key` hoặc plaintext secret.

## 8. Checklist trước khi submit

- [ ] `operationId` duy nhất và ổn định.
- [ ] Response mutation có `operation_id` đúng định dạng.
- [ ] Response có resource ID trong `data`.
- [ ] Có error code ổn định.
- [ ] Có `Idempotency-Key` với mutation.
- [ ] Domain đã được xác minh.
- [ ] Không có secret/JWT/PII trong log và response không cần thiết.
- [ ] OpenAPI validate pass.
- [ ] Test retry không tạo duplicate operation.

## 9. Ví dụ Python SDK

```python
from superapp_sdk import PartnerResponse

return PartnerResponse.success(
    data={"booking_id": "BOOK-123", "status": "CONFIRMED"},
    message="Đặt lịch thành công",
operation_id="event-booking-123",
)
```

## 10. Quy trÃ¬nh Ä‘Äƒng kÃ½ vÃ  callback

Partner gá»­i `POST /api/v1/registry/services` kÃ¨m Bearer token vÃ  JSON:

```json
{
  "service_code": "EVENT_BOOKING",
  "name": "Event Booking",
  "base_url": "https://eventbooking.example.com",
  "allowed_domains": ["https://eventbooking.example.com"],
  "callback_event": "event-status"
}
```

`callback_event` do Mini App tá»± Ä‘iá»n, pháº£i lÃ  slug chá»¯ thÆ°á»ng káº¿t thÃºc báº±ng
`-status`, vÃ­ dá»¥ `ride-status`, `event-status`, `health-status`. Response tráº£ vá»:

```json
{
  "service_code": "EVENT_BOOKING",
  "callback_event": "event-status",
  "callback_url": "https://xspacesuperapp.dpdns.org/api/v1/webhooks/event-status",
  "approval_status": "draft"
}
```

Hostname trong `callback_url` Ä‘Æ°á»£c sinh tá»« `PLATFORM_PUBLIC_URL` cá»§a Super App,
khÃ´ng hardcode trong Mini App. Production Ä‘áº·t
`PLATFORM_PUBLIC_URL=https://xspacesuperapp.dpdns.org`; local Ä‘áº·t
`PLATFORM_PUBLIC_URL=http://localhost:8000`. Callback chá»‰ Ä‘Æ°á»£c cháº¥p nháº­n sau
khi Admin phÃª duyá»‡t vÃ  cáº¥p credential.

### OpenAPI endpoint

Má»—i mutation pháº£i cÃ³ `operationId`, metadata `x-superapp`, idempotency vÃ  response cÃ³
`operation_id`:

```yaml
/bookings:
  post:
    operationId: createEventBooking
    x-superapp:
      capability: event.booking.create
      sideEffect: create
      riskLevel: high
      requiresConfirmation: true
      idempotency: required
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [event_id, attendee_name]
            properties:
              event_id: {type: string}
              attendee_name: {type: string}
```

```json
{
  "status": "success",
  "operation_id": "event-booking-123",
  "data": {"booking_id": "BOOK-123", "status": "CONFIRMED"}
}
```

### Callback JSON vÃ  headers

```http
POST {callback_url}
Content-Type: application/json
X-App-Id: <SUPERAPP_APP_ID>
X-Key-Id: <SUPERAPP_KEY_ID>
X-Api-Key: <SUPERAPP_API_KEY>
X-Miniapp-Origin: https://eventbooking.example.com
X-Timestamp: <unix-seconds>
X-Nonce: <unique-value>
X-Signature: <hmac-sha256>
```

```json
{
  "service_code": "EVENT_BOOKING",
  "operation_id": "event-booking-123",
  "booking_id": "BOOK-123",
  "status": "CONFIRMED",
  "message": "VÃ© Ä‘Ã£ Ä‘Æ°á»£c xÃ¡c nháº­n",
  "event_id": "evt-unique-123"
}
```

Payload pháº£i cÃ³ `service_code` vÃ  Ã­t nháº¥t má»™t ID Ä‘á»ƒ map vá» chat:
`booking_id`, `order_id` hoáº·c `ride_id`. Platform tá»« chá»‘i náº¿u sai credential,
domain, signature, callback event hoáº·c service code.

Nếu `operation_id` sai định dạng, SDK phải reject response trước khi trả về Platform.
