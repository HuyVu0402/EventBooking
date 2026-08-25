# Hướng dẫn xây dựng Mini-app tích hợp Super App (X-Space)

Tài liệu này phục vụ 2 đối tượng:
- **Dev độc lập, chưa từng đụng vào code của Super App**, cần xây một mini-app
  (dịch vụ đối tác) để Agent (X-Stra) có thể tìm thấy, gọi và điều khiển được.
  Không cần biết LangGraph hay đọc code Agent — chỉ cần làm đúng hợp đồng API mô
  tả từ mục 1 đến 10.
- **Người dùng/đối tác không rành kỹ thuật**, chỉ cần đăng ký mini-app đã có sẵn
  vào hệ thống qua giao diện web — xem thẳng **mục 11.1 và 11.2** (không cần đọc
  các mục kỹ thuật phía trên).

> Các tài liệu liên quan đã có sẵn trong repo, tài liệu này **bổ sung phần triển
> khai kỹ thuật chi tiết** mà 2 tài liệu kia không đi sâu:
> - [`docs/miniapps/premium-app-submission-template.md`](../miniapps/premium-app-submission-template.md) — biểu mẫu nghiệp vụ điền khi nộp cho Admin duyệt.
> - [`docs/api/premium_miniapp_guide.md`](../api/premium_miniapp_guide.md) — tóm tắt 3 bước đăng ký.

---

## 0. Tóm tắt nhanh (TL;DR)

1. Mini-app = **một REST API độc lập của riêng bạn** (FastAPI, Express, Spring... tuỳ
   ý), tự deploy, có địa chỉ `base_url` mà Platform API gọi tới được qua HTTP(S).
2. Bạn viết **OpenAPI 3.x spec** mô tả các endpoint của mini-app, kèm vài field mở
   rộng `x-*` để khai báo mức rủi ro / quyền / deep-link.
3. Bạn đăng ký `base_url` + OpenAPI spec đó vào catalog của Super App qua
   `POST /api/v1/registry/services` (+ `/versions`), hoặc qua UI **Premium
   Dashboard**.
4. Admin duyệt (`approve`) → service chuyển sang `published` + `active`.
5. Từ lúc đó Agent **tự động** đọc endpoint của bạn từ database, biến thành "tool"
   cho LLM, gọi qua Gateway khi người dùng chat — **bạn không sửa bất kỳ dòng code
   nào trong `apps/platform-api`**.

```
Người dùng chat → Agent (LangGraph) → chọn tool = endpoint của bạn
   → validate theo JSON Schema bạn khai → (nếu POST/PUT/PATCH/DELETE) dừng chờ
     người dùng bấm Xác nhận (HITL) → GatewayService gọi HTTP thật tới base_url
     + path của bạn → bạn trả JSON → Agent tổng hợp câu trả lời + deep-link
```

---

## 1. Vai trò của mini-app trong kiến trúc tổng thể

```
apps/web (Next.js)  ─┐
apps/mobile-mock     ─┼─► POST /api/v1/chat ──► LangGraph Agent (platform-api)
                      ─┘        │                     │
                                │            đọc catalog từ DB
                                │            (bảng services/service_versions)
                                ▼
                     GatewayService.invoke_endpoint()
                                │  HTTP(S) server-to-server, header:
                                │  X-Endpoint-Code, Idempotency-Key, x-api-key
                                ▼
                    ┌───────────────────────────┐
                    │   MINI-APP CỦA BẠN         │  ◄── bạn viết & deploy phần này
                    │   (base_url + path)        │
                    └───────────────────────────┘
                                │  (tuỳ chọn) webhook async status
                                ▼
                POST /api/v1/webhooks/ride-status  (đẩy ngược qua SSE về đúng thread)
```

Platform API **không** import code của bạn, không chạy chung process. Mini-app hoàn
toàn tách biệt — chỉ giao tiếp qua HTTP theo hợp đồng ở mục 5.

---

## 2. Yêu cầu bắt buộc / tuỳ chọn

| # | Yêu cầu | Bắt buộc? | Ghi chú |
|---|---|---|---|
| 1 | Expose HTTP(S) API, reachable từ platform-api | Bắt buộc | Có thể `http://localhost:PORT` khi cả hai chạy local, hoặc domain public khi deploy (Render, Railway...) |
| 2 | Mỗi hành động = 1 REST endpoint riêng (search, estimate, book, cancel, status...) | Bắt buộc | Không gộp nhiều hành động vào 1 endpoint bằng flag |
| 3 | Có OpenAPI 3.x spec mô tả đúng các endpoint đó | Bắt buộc | Có thể tự viết tay JSON, hoặc export từ FastAPI (`app.openapi()`) |
| 4 | Mỗi field trong request có `description` tiếng Việt rõ ràng | Rất khuyến nghị | Trở thành **nhãn hiển thị cho người dùng** khi form nhập liệu thiếu field — xem mục 4 |
| 5 | Trả JSON, khuyến nghị theo envelope `{status, message, data}` | Khuyến nghị | Dùng SDK có sẵn `apps/sdk/python/superapp_sdk` (`PartnerResponse`) |
| 6 | Endpoint mutation (POST/PUT/PATCH/DELETE) tôn trọng header `Idempotency-Key` | Bắt buộc cho action tạo giao dịch | Xem mục 5 & 14 |
| 7 | Health check endpoint trả `200` | Khuyến nghị | Khai ở `health_check_url` lúc đăng ký |
| 8 | Webhook callback đẩy trạng thái async ngược về Super App | Tuỳ chọn | Chỉ cần nếu có trạng thái thay đổi *sau* khi Agent gọi xong (vd tài xế nhận chuyến) |
| 9 | Không cần biết JWT/OAuth của Super App | — | Danh tính người dùng được Platform API tự đính kèm vào payload (mục 5), mini-app không cần màn hình đăng nhập riêng |

---

## 3. Thông tin cần chuẩn bị trước khi đăng ký

Điền đầy đủ **[biểu mẫu nghiệp vụ](../miniapps/premium-app-submission-template.md)** đã có sẵn trong repo. Tóm tắt các trường bắt buộc về mặt kỹ thuật:

| Trường | Map sang | Ví dụ |
|---|---|---|
| `service_code` | `Service.service_code` (unique, 3-100 ký tự) | `RIDE_001` |
| `name` | `Service.name` | `X-Ride Hailing` |
| `description` | `Service.description` | `Dịch vụ gọi xe thông minh` |
| `category` | `Service.category` | `transport` |
| `base_url` | `Service.base_url` | `http://localhost:8001/api/v1/mock/ride` hoặc `https://your-app.onrender.com` |
| `health_check_url` | `Service.health_check_url` | `.../health` |
| `outbound_api_key` (tuỳ chọn) | `Service.outbound_api_key` | secret bạn tự chọn, Platform API sẽ gửi lại đúng giá trị này ở header `x-api-key` mỗi lần gọi bạn — **không** để lộ trong OpenAPI spec/docs |
| `is_sensitive` | `Service.metadata_json.is_sensitive` | `true` nếu toàn bộ service liên quan dữ liệu nhạy cảm |
| `version_number` | `ServiceVersion.version_number` | `1.0.0` |
| `openapi_spec` | `ServiceVersion.openapi_spec` | xem mục 4 |
| `deep_link_template` (tuỳ chọn) | `ServiceVersion.deep_link_template` | `xapp://ride/booking?pickup={pickup}&dropoff={dropoff}` |
| `required_scopes` (tuỳ chọn) | `ServiceVersion.required_scopes` | `["premium_user"]` — để trống thì mọi user đã đăng nhập gọi được |
| `sample_intents` (tuỳ chọn) | `ServiceVersion.sample_intents` | chỉ là metadata hiển thị cho Admin, **không** được đưa vào prompt Agent |

---

## 4. Cách Agent nhìn thấy & chọn mini-app của bạn

Mỗi lượt chat, Agent (`load_active_catalog()` trong
`apps/platform-api/src/agents/navigation_agent.py`) đọc **mọi** service có
`approval_status="published"` và `status="active"`, tách OpenAPI spec của version
hiện hành thành từng `(method, path)`, rồi biến **mỗi operation thành một hàm
(tool) cho LLM chọn gọi** — không dùng embedding/RAG, không có bước "tìm kiếm mờ".

Vì vậy: **operation nào không có trong OpenAPI spec của bạn thì Agent không bao giờ
gọi được**, và ngược lại mọi operation bạn khai đều lộ ra như một hành động khả dụng.

### Vendor extension `x-*` — đây là phần quan trọng nhất khi viết OpenAPI spec

`SchemaService._endpoint_from_operation()` đọc các field mở rộng sau trên từng
`operation` (path + method) trong spec của bạn:

| Field OpenAPI | Kiểu | Mặc định nếu bỏ trống | Ý nghĩa |
|---|---|---|---|
| `operationId` | string | tự sinh từ `service_code.method.path` | Định danh duy nhất, nên đặt tường minh (`book_ride`, `cancel_ride`...) |
| `description` / `summary` | string | mô tả service | Agent dùng làm mô tả tool — viết rõ **khi nào dùng endpoint này** |
| `x-required-scopes` | list[str] | `[]` (rỗng = ai cũng gọi được) | Scope hợp lệ: `end_user`, `premium_user`, `catalog_admin` |
| `x-requires-hitl` / `x-requires-approval` | bool | `false` | Ép buộc dừng chờ xác nhận người dùng dù method là GET |
| `x-risk-level` | `"low"` \| `"high"` \| tuỳ | `"high"` nếu method ≠ GET, `"low"` nếu GET | risk khác `"low"`/rỗng cũng ép buộc HITL |
| `x-side-effect-type` | string | `"read"` (GET) / `"mutation"` (khác) | chỉ mang tính mô tả/trace |
| `x-deep-link-template` | string | dùng `deep_link_template` của version | override deep-link riêng cho 1 operation |
| `x-action-url-field` | string, dot-path | không có | đường dẫn tới field chứa URL động trong response của bạn (mục 6) |
| `x-timeout-ms` | int | `5000` | Gateway huỷ gọi nếu bạn không phản hồi kịp |
| `x-retry-policy` | string | `"safe_retry"` (GET) / `"no_retry"` (khác) | hiện chỉ mang tính mô tả, Gateway không tự động retry |
| `x-idempotency-required` | bool | `true` nếu method ≠ GET | có gửi header `Idempotency-Key` hay không |

> ⚠️ **Quan trọng nhất, không có cách nào tắt được**: logic thực tế trong
> `PolicyService.requires_approval()` là **OR** — `requires_hitl OR method không
> phải GET/HEAD/OPTIONS OR risk_level khác "low"/rỗng`. Nghĩa là **mọi endpoint
> POST/PUT/PATCH/DELETE luôn luôn bắt buộc người dùng bấm xác nhận (HITL) trước
> khi Agent thực sự gọi bạn**, bất kể bạn có set `x-requires-hitl: false` hay
> không. Đây là chủ đích thiết kế (đúng yêu cầu "Sensitive actions require
> Human-in-the-Loop" của dự án), không phải bug — hãy thiết kế flow cho phù hợp
> (xem mục 14).

### Vì sao `description` của từng field quan trọng

Khi request thiếu field bắt buộc, hệ thống trả `missing_fields` +
`input_schema` để frontend tự sinh **Dynamic Form**. Câu hỏi hiển thị cho người
dùng lấy trực tiếp từ mệnh đề đầu tiên trong `description` của field (xem
`_field_label()` trong `navigation_agent.py`) — ví dụ field khai
`"description": "Địa điểm đón (VD: VinUni, Gia Lâm, Hà Nội)"` sẽ hiển thị
"Địa điểm đón" cho người dùng. **Không viết description bằng tiếng Anh kỹ thuật**
nếu muốn UX tốt cho end-user Việt Nam.

Ví dụ field chuẩn (từ `apps/partner-miniapps/mock-suite/schemas/ride.py`):

```python
pickup: str = Field(..., description="Địa điểm đón (VD: VinUni, Gia Lâm, Hà Nội)")
vehicle_type: str = Field(
    "car_4",
    description=(
        "Loại xe. Giá trị hợp lệ: bike | car_4 | car_7 | premium. "
        "Người dùng thường không gõ đúng các mã này — hãy tự quy đổi theo nghĩa: "
        "'xe máy' -> bike; 'ô tô', 'xe 4 chỗ' -> car_4; 'xe 7 chỗ' -> car_7; 'xe sang' -> premium."
    ),
)
```

Agent **không đoán** kiểu dữ liệu hay giá trị hợp lệ — nếu field có tập giá trị cố
định (enum), hãy liệt kê rõ trong `description` như ví dụ trên, hoặc dùng
`"enum": [...]` trong JSON Schema.

---

## 5. Hợp đồng gọi API (contract) — bạn nhận gì, phải trả gì

### 5.1. Request bạn sẽ nhận từ Platform API (`GatewayService.invoke_endpoint`)

| Thành phần | Giá trị |
|---|---|
| Method + URL | `{base_url}/{path}` đúng như khai trong OpenAPI |
| Header `X-Endpoint-Code` | `operationId` của endpoint đang gọi |
| Header `Idempotency-Key` | Chỉ gửi nếu `idempotency_required=true` (mặc định đúng với mọi non-GET). Giá trị dạng `{thread_id}-{task_id}`, **ổn định giữa các lần gọi lại cùng 1 task** |
| Header `x-api-key` | Chỉ gửi nếu bạn có set `outbound_api_key` lúc đăng ký — đúng giá trị bạn đã đặt |
| Body (POST/PUT/PATCH/DELETE) | JSON gồm các field người dùng/Agent cung cấp theo `request_schema`, **cộng thêm** field `customer` (xem dưới) |
| Query params (GET) | Các field trong `request_schema`, gửi qua URL query string (không có body) |

Với mọi method **khác GET**, Platform API tự tra hồ sơ user hiện tại và đính kèm:

```json
"customer": {
  "full_name": "Nguyễn Văn A",
  "email": "a@example.com",
  "username": "nva"
}
```

→ Mini-app **không cần yêu cầu người dùng đăng nhập lại** — tin tưởng field
`customer` này (server-to-server, không phải input do người dùng tự gõ).

### 5.2. Response bạn phải trả

- Trả **HTTP 2xx** với JSON body cho trường hợp thành công. Bất kỳ status code
  khác 2xx nào cũng khiến Gateway coi là lỗi (`http_error`, kèm status code +
  500 ký tự đầu của body) và Agent sẽ báo lỗi lại cho người dùng.
- Không có ràng buộc bắt buộc về shape JSON ở tầng Gateway (nó forward nguyên
  vẹn), nhưng **khuyến nghị mạnh** dùng envelope chuẩn có sẵn trong SDK:

```python
from superapp_sdk import PartnerResponse

# thành công
return PartnerResponse.success(data={"booking_id": "RIDE-001", ...}, message="Đặt xe thành công")
# => {"status": "success", "message": "Đặt xe thành công", "data": {...}}

# lỗi nghiệp vụ (vẫn trả HTTP 200, lỗi nằm trong body — dùng khi muốn Agent
# đọc được message lỗi cụ thể thay vì chỉ biết "http_error")
return PartnerResponse.error(message="Không còn tài xế khả dụng", code="NO_DRIVER")
```

- Toàn bộ body bạn trả sẽ được đặt vào field `data` bên trong kết quả nội bộ mà
  Agent xử lý. Nếu bạn dùng `PartnerResponse.success(data=X)`, tức là kết quả nội
  bộ có dạng `{"data": {"status": "success", "message": "...", "data": X}}`. Vì
  vậy khi khai `x-action-url-field` (mục 6), path phải trỏ vào **bên trong** `X`,
  ví dụ `"x-action-url-field": "data.checkout_url"` ứng với
  `X = {"checkout_url": "https://..."}`.
- **Timeout**: nếu bạn không phản hồi trong `x-timeout-ms` (mặc định 5000ms),
  Gateway trả lỗi `timeout` cho Agent — luồng nghiệp vụ ở phía bạn (nếu đã lỡ xử
  lý) coi như ở "trạng thái không xác định" (điều Gateway tự cảnh báo trong log).
  Đừng để action quan trọng (tạo đơn, trừ tiền) chạy quá lâu trong request đồng
  bộ — nếu cần xử lý dài, trả ngay trạng thái "đang xử lý" và dùng webhook (mục 8)
  để báo kết quả cuối cùng.

---

## 6. Deep-link & mở màn hình mini-app

Có 2 cơ chế, dùng cái nào tuỳ tình huống:

1. **`deep_link_template` tĩnh** (khai ở version hoặc `x-deep-link-template` ở
   từng operation) — Platform API tự thay `{field}` bằng giá trị input của
   người dùng, không cần bạn trả gì thêm:
   ```
   "xapp://ride/booking?pickup={pickup}&dropoff={dropoff}"
   ```
   Field tên `amount`/`price`/`fare`/`payment_amount` được tự động parse từ dạng
   tiếng Việt tự nhiên (`"500k"`, `"2 triệu"`, `"1.5tr"`) sang số nguyên VNĐ trước
   khi chèn vào URL (`DeepLinkService.parse_amount`).

2. **`x-action-url-field` động** — dùng khi URL chỉ có thể sinh ra **tại
   runtime bởi chính mini-app** (ví dụ link thanh toán VNPay ký theo từng đơn
   hàng). Bạn trả URL đó trong response, Platform API đọc đúng field đã khai và
   ưu tiên dùng nó thay cho deep-link template.

**Giới hạn hiện tại của frontend**: nút hành động ở giao diện chat chỉ là một thẻ
`<a href="..." target="_blank">` thông thường
(`apps/web/components/chat/MessageBubble.tsx`). Với URL `http(s)://` thật (mini-app
mock-suite, trang thanh toán, trang đặt lịch...) nó mở tab mới bình thường. Với
scheme giả lập kiểu `xapp://...` trên trình duyệt web, sẽ **không có gì xảy ra**
trừ khi có ứng dụng đã đăng ký scheme đó — chỉ có ý nghĩa đầy đủ trên
`apps/mobile-mock` (iOS) nếu app đó tự xử lý scheme này. Nếu mini-app của bạn chỉ
chạy trên web, ưu tiên trả một URL `http(s)://` thật sự mở được.

---

## 7. HITL, mức rủi ro và quyền truy cập

- **HITL**: xem cảnh báo ở mục 4 — mọi POST/PUT/PATCH/DELETE luôn dừng lại chờ
  người dùng bấm "Xác nhận" trước khi Gateway thực sự gọi bạn. Người dùng thấy
  bảng xem lại thông tin (`PolicyService.approval_payload`) rồi mới confirm.
- **Quyền (`required_scopes` / `x-required-scopes`)**: scope hợp lệ hiện có
  đúng 3 giá trị, suy ra từ role JWT (`get_current_user_scopes` trong
  `chat_router.py`):

  | Role | Scope |
  |---|---|
  | `USER` | `end_user` |
  | `PREMIUM` | `premium_user` |
  | `ADMIN` | `end_user`, `catalog_admin`, `premium_user` (có tất cả) |

  Để trống `required_scopes` = ai đã đăng nhập cũng gọi được. Muốn giới hạn cho
  tài khoản Premium, khai `"x-required-scopes": ["premium_user"]`.
- **Idempotency**: vì `Idempotency-Key` bạn nhận được ổn định cho cùng 1 task
  (kể cả khi Agent retry/resume sau khi người dùng bấm xác nhận), **hãy lưu lại
  key đó** (vd trong Redis/DB) và nếu thấy key đã xử lý rồi thì trả lại đúng kết
  quả cũ thay vì tạo đơn/trừ tiền lần 2.

---

## 8. Webhook — đẩy trạng thái async ngược về Super App

Dùng khi mini-app có sự kiện xảy ra **sau** khi Agent đã gọi xong (vd tài xế nhận
chuyến, đơn hàng chuyển trạng thái giao hàng...), để chat cập nhật real-time qua
SSE thay vì người dùng phải hỏi lại.

Hiện tại backend có sẵn **một** endpoint webhook cụ thể cho luồng đặt xe:

```
POST {PLATFORM_API_URL}/api/v1/webhooks/ride-status
Header: X-Api-Key: <đúng outbound_api_key bạn đã đăng ký>
Body:
{
  "service_code": "RIDE_001",
  "booking_id": "RIDE-APP-XXXXXX",
  "status": "CONFIRMED",
  "driver_name": "...",
  "driver_phone": "...",
  "license_plate": "...",
  "message": "..."
}
```

Xác thực bằng **so khớp trực tiếp** `X-Api-Key` với `outbound_api_key` đã lưu
theo `service_code` (không phải HMAC — mặc dù SDK có sẵn `GatewaySecurity` để ký
HMAC-SHA256 cho các trường hợp cần chữ ký mạnh hơn trong tương lai, endpoint hiện
tại chưa dùng tới).

Để Super App map đúng webhook về đúng đoạn chat, response **thành công** của
endpoint tạo giao dịch ban đầu (khi Agent gọi bạn) phải chứa 1 trong 3 field:
`booking_id`, `order_id`, hoặc `ride_id` ở cấp cao nhất trong `data` — Platform
API tự lưu map `{id đó} -> thread_id` (`_register_booking_thread` trong
`service_invocation_node.py`) để biết đẩy webhook này vào đúng cuộc hội thoại nào.

Nếu mini-app của bạn cần một loại thông báo khác (không phải "ride status"), route
hiện tại **chưa tổng quát hoá** — cần phối hợp với team backend để thêm route
webhook mới tương tự (copy pattern của `webhook_router.py`), tài liệu này chỉ mô tả
route đã có sẵn.

Code mẫu gọi webhook (rút gọn từ `apps/partner-miniapps/mock-suite/routers/ride.py`):

```python
import httpx

SUPERAPP_WEBHOOK_URL = os.getenv("SUPERAPP_WEBHOOK_URL", "http://localhost:8000/api/v1/webhooks/ride-status")
SERVICE_CODE = os.getenv("SERVICE_CODE", "RIDE_001")
SUPERAPP_API_KEY = os.getenv("SUPERAPP_API_KEY", "")

async def notify_superapp(**payload) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                SUPERAPP_WEBHOOK_URL,
                json={"service_code": SERVICE_CODE, **payload},
                headers={"X-Api-Key": SUPERAPP_API_KEY},
            )
        response.raise_for_status()
        return bool(response.json().get("delivered"))
    except httpx.HTTPError:
        return False  # không làm fail request gốc của bạn vì lỗi webhook
```

---

## 9. Bảo mật

- **`outbound_api_key`** đóng vai trò 2 chiều: (a) Platform API gửi nó ở header
  `x-api-key` mỗi lần **gọi bạn**, để bạn có thể xác thực caller thật sự là Super
  App (nếu bạn tự kiểm tra header này); (b) chính bạn gửi lại đúng giá trị đó ở
  header `X-Api-Key` khi **gọi webhook** để Super App xác thực ngược lại bạn.
  Không bắt buộc, nhưng nếu API của bạn có thể gây thiệt hại thật (tiền, dữ liệu),
  hãy đặt key và tự kiểm tra header ở phía bạn.
- **Không** để lộ `outbound_api_key` trong OpenAPI spec, README, hay bất kỳ nội
  dung nào bạn nộp cho Admin — nó chỉ nằm trong field write-only của
  `ServiceCreateRequest`, không bao giờ echo lại trong response.
- Không cần CORS — mọi cuộc gọi từ Platform API là **server-to-server**, không
  qua trình duyệt.
- Tự validate input ở phía bạn dù đã khai JSON Schema — schema ở tầng đăng ký chỉ
  ràng buộc Agent/Dynamic Form, không phải tường lửa; đối xử với mọi input như
  chưa được kiểm chứng.

---

## 10. Local dev & test workflow

1. **Viết mini-app trước, đăng ký sau.** Chạy mini-app độc lập bằng
   `uvicorn main:app --reload --port 8xxx`, tự test qua `/docs` (Swagger UI) tới
   khi hài lòng với schema request/response.
2. **Không có backend thật vẫn xem được luồng Agent hoạt động**: đặt
   `base_url` bắt đầu bằng `mock://` (ví dụ `mock://ride-service`) khi đăng ký —
   `GatewayService._handle_mock_invocation` sẽ tự trả một response giả lập
   "thành công" mà **không hề gọi mạng thật**. Hữu ích để duyệt thử OpenAPI spec
   + luồng HITL/Dynamic Form trước khi code xong backend thật. **Không dùng
   `mock://` cho service thật/production.**
3. **Chạy song song với Platform API** (xem `CLAUDE.md`/README gốc):
   ```
   make run              # platform-api tại :8000
   uvicorn main:app --port 8001   # mini-app của bạn, hoặc make mock-miniapps nếu bạn thêm router vào mock-suite
   ```
   Nếu cả hai chạy trên cùng máy, `base_url` dùng `http://localhost:PORT`.
4. **Đăng ký thử bằng REST API trực tiếp** — xem mục 11 (Cách B) để gọi
   `POST /api/v1/registry/services` rồi `.../versions` bằng curl/`TestClient`,
   sau đó approve. (`scripts/registry/register_mock_apps.py` trong repo hiện
   gọi 2 route cũ đã không còn tồn tại —
   `/api/v1/registry/register` và `/api/v1/registry/{}/approve` — chỉ dùng file
   đó để tham khảo **shape dữ liệu** của `base_url`/`deep_link_template`/
   `openapi_spec`, không chạy trực tiếp được với router hiện tại.)
5. **Test end-to-end qua chat** (không cần UI, dùng curl):
   ```bash
   TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"user","password":"User@123456"}' | jq -r .access_token)

   curl -s -X POST http://localhost:8000/api/v1/chat \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"message":"đặt xe từ VinUni đến sân bay Nội Bài"}' | jq
   ```
   Kiểm tra `workflow_status`/`waiting_for` trong response: `"waiting" / "input"`
   nghĩa là thiếu field (kiểm tra lại `description` + `required`),
   `"waiting" / "approval"` nghĩa là đúng luồng HITL — gọi tiếp
   `POST /api/v1/chat/{thread_id}/resume` với `{"approved": true}` để xác nhận và
   để Agent thực sự gọi mini-app của bạn.

---

## 11. Quy trình đăng ký & duyệt

Phần này chia làm 2: **11.1-11.2 dành cho người dùng** (đối tác/chủ mini-app,
đăng ký hoàn toàn qua giao diện web, **không cần biết code hay curl**) và
**11.3 dành cho dev** (gọi thẳng REST API, hữu ích khi cần tự động hoá/test).

### 11.1. Bước 0 (bắt buộc trước) — Trở thành đối tác (role PREMIUM)

Chỉ tài khoản role `USER` bình thường mới nộp được đơn — nếu bạn chưa có tài
khoản, đăng ký tài khoản thường trước (`/register`), rồi làm theo các bước sau:

1. Đăng nhập, mở form "Đăng ký đối tác" bằng 1 trong 2 cách:
   - Menu tài khoản ở Sidebar → **"Đăng ký đối tác"** (chỉ hiện khi tài khoản
     đang là user thường).
   - Màn hình **Cài đặt/Hồ sơ** → banner **"Trở thành Đối tác Mini App
     (Developer)"** → nút **"Đăng ký ngay"**.
2. Điền đầy đủ form (validate ngay trên giao diện):

   | Trường | Ví dụ / placeholder | Ràng buộc |
   |---|---|---|
   | Tên Tổ chức / Doanh nghiệp / Nhóm phát triển * | "VinAI Technology JSC, Grab Vietnam..." | tối thiểu 2 ký tự |
   | Họ tên người liên hệ * | "Nguyễn Văn A" | tối thiểu 2 ký tự |
   | Số điện thoại liên hệ * | "0912345678" | đúng định dạng số điện thoại |
   | Email xác thực (Gmail) * | "partner.tech@gmail.com" | **bắt buộc đuôi @gmail.com** (để đồng bộ OIDC xác thực) |
   | Mô tả dịch vụ / Mini App dự kiến tích hợp * | "Đặt xe di chuyển, Mua vé rạp chiếu phim, Thanh toán điện nước..." | tối thiểu 20 ký tự |

3. Bấm **"Gửi Hồ Sơ Phê Duyệt"**. Hệ thống chặn gửi đơn thứ 2 nếu đơn trước vẫn
   đang chờ duyệt (`PENDING`).
4. Chờ Admin duyệt (Admin thao tác ở `AdminDashboard.tsx`, tab **"Đối tác"**,
   nút **"Phê duyệt"**/**"Từ chối"**). Bạn có thể mở lại form để xem trạng thái
   đơn của mình (PENDING / APPROVED / REJECTED).
5. **Sau khi được duyệt: đăng xuất rồi đăng nhập lại** — bắt buộc, vì quyền
   (`role`) chỉ được đọc lại từ token lúc đăng nhập, không tự cập nhật giữa
   phiên đang mở. Đăng nhập lại xong, giao diện tự chuyển hẳn sang **"Developer
   Console"** (Premium Dashboard) thay vì màn hình chat thông thường.

### 11.2. Đăng ký mini-app qua Premium Dashboard (wizard 3 bước)

Sau bước 0, mỗi lần đăng nhập bằng tài khoản đối tác, giao diện tự mở thẳng
**Premium Dashboard**. Bấm "Đăng ký Mini App mới" để vào wizard:

**Bước 1 — Thông tin cơ bản**
| Trường | Placeholder gợi ý |
|---|---|
| Mã Dịch Vụ (Code) * | `EVENT_BOOKING` |
| Tên Dịch Vụ * | `Đặt Vé Sự Kiện & Hội Nghị` |
| Mô tả Dịch Vụ * | "Mô tả chức năng để AI Agent hiểu mục đích điều hướng..." |
| Danh Mục Dịch Vụ | `EVENTS / ENTERTAINMENT` |
| Base URL Backend * | `http://localhost:8101` (hoặc domain thật đã deploy) |
| Outbound API Key (tùy chọn) | "Khóa API xác thực gửi kèm header tới Backend đối tác" |

**Bước 2 — Cấu hình API**: khai từng endpoint (method, path, summary/mô tả,
operationId, danh sách parameter hoặc field trong request body) — đây chính là
phần kỹ thuật, nên nhờ dev của bạn điền theo hướng dẫn ở **mục 4-5** phía trên.
Form sẽ tự build thành `openapi_spec` khi submit.

**Bước 3 — Cấu hình AI**: `Deep Link Template` (vd
`http://localhost:8101/docs?booking_id={booking_id}`) và `Sample Intents` — vài
câu người dùng có thể gõ để AI nhận diện đúng dịch vụ (vd "tìm sự kiện ở Hà
Nội, đặt vé sự kiện, có sự kiện nào hot...").

Bấm Submit → hệ thống tự gọi `POST /api/v1/registry/services` rồi
`POST /api/v1/registry/services/{id}/versions` — bạn không cần biết 2 lệnh gọi
này tồn tại. Mỗi mini-app đã đăng ký hiển thị lại thành 1 thẻ trên Dashboard,
kèm huy hiệu trạng thái: **"Chờ duyệt"** (mặc định) → **"Đã duyệt"** hoặc
**"Từ chối"** sau khi Admin xử lý.

### 11.3. Cách khác dành cho dev — gọi thẳng REST API

```bash
# 1. Tạo service (role PREMIUM/ADMIN)
curl -X POST http://localhost:8000/api/v1/registry/services \
  -H "Authorization: Bearer $PREMIUM_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "service_code": "RIDE_001",
    "name": "X-Ride Hailing",
    "description": "Dịch vụ gọi xe thông minh",
    "category": "transport",
    "base_url": "http://localhost:8001/api/v1/mock/ride",
    "health_check_url": "http://localhost:8001/api/v1/mock/health",
    "is_sensitive": false,
    "outbound_api_key": "change-me-secret"
  }'
# -> trả về {"id": "<service_id>", ...}

# 2. Tạo version kèm OpenAPI spec đầy đủ
curl -X POST http://localhost:8000/api/v1/registry/services/<service_id>/versions \
  -H "Authorization: Bearer $PREMIUM_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "version_number": "1.0.0",
    "openapi_spec": { "openapi": "3.1.0", "paths": { "...": {} } },
    "deep_link_template": "xapp://ride/booking?pickup={pickup}&dropoff={dropoff}",
    "sample_intents": ["đặt xe", "gọi xe đi sân bay"]
  }'
# -> service tự chuyển approval_status = "pending_review"
```

### Duyệt (Admin)

```bash
curl -X POST http://localhost:8000/api/v1/admin/registry/services/<service_id>/approve \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

> Route approve/reject/deprecate (`src/api/v1/admin_registry_router.py`) yêu
> cầu JWT hợp lệ **và** role `ADMIN` thật sự (`get_current_admin` parse token,
> trả 401 nếu thiếu/sai token, 403 nếu không phải ADMIN) — cùng chuẩn với
> `partner_admin_router.py` (duyệt hồ sơ đối tác). Gọi thử mà thiếu
> `Authorization: Bearer <admin_token>` sẽ luôn bị chặn, không tự nhiên
> "chạy được" như một số bản cũ trong lịch sử dự án.

Sau khi `approve`: `approval_status = "published"`, `status = "active"` → Agent
thấy ngay ở lượt chat tiếp theo (không cần restart Platform API, vì
`load_active_catalog()` đọc DB **mỗi lượt chat**).

---

## 12. Ví dụ tham khảo đầy đủ trong repo

| File | Vì sao nên xem |
|---|---|
| [`apps/partner-miniapps/mock-suite/routers/ride.py`](../../apps/partner-miniapps/mock-suite/routers/ride.py) + [`schemas/ride.py`](../../apps/partner-miniapps/mock-suite/schemas/ride.py) | Ví dụ đầy đủ nhất: dùng `PartnerResponse`, có webhook callback, idempotent theo `booking_id`, tích hợp thanh toán (VNPay), description tiếng Việt chuẩn cho Dynamic Form |
| [`apps/platform-api/scripts/registry/register_mock_apps.py`](../../apps/platform-api/scripts/registry/register_mock_apps.py) | Chỉ để tham khảo **shape dữ liệu** (`base_url`, `deep_link_template`, `openapi_spec`...) — script này gọi 2 route cũ (`/api/v1/registry/register`, `/api/v1/registry/{}/approve`) **không còn tồn tại** trong router hiện tại, nên không chạy trực tiếp được; dùng flow ở mục 11 (Cách B) thay thế |
| [`apps/sdk/python/superapp_sdk/`](../../apps/sdk/python/superapp_sdk) | `PartnerResponse` (envelope chuẩn), `GatewaySecurity` (ký HMAC nếu cần), `ManifestValidator` (tự kiểm tra manifest hợp lệ trước khi nộp) |
| [`apps/platform-api/src/services/schema_service.py`](../../apps/platform-api/src/services/schema_service.py) | Nguồn sự thật cho toàn bộ bảng `x-*` ở mục 4 |
| [`apps/platform-api/src/services/policy_service.py`](../../apps/platform-api/src/services/policy_service.py) | Nguồn sự thật cho logic HITL/quyền ở mục 7 |
| [`apps/platform-api/src/services/gateway_service.py`](../../apps/platform-api/src/services/gateway_service.py) + [`deeplink_service.py`](../../apps/platform-api/src/services/deeplink_service.py) | Nguồn sự thật cho hợp đồng request/response + deep-link ở mục 5, 6 |

---

## 13. Checklist bàn giao

- [ ] `service_code` duy nhất, đặt tên rõ nghĩa (không trùng service khác)
- [ ] `base_url`/`health_check_url` reachable từ Platform API, health check trả `200`
- [ ] OpenAPI spec hợp lệ (validate được bằng `/docs` hoặc `openapi-spec-validator`)
- [ ] Mọi field request có `description` tiếng Việt rõ ràng, `required` khai đúng
- [ ] Mọi response thành công trả `PartnerResponse.success(...)` (hoặc tương đương)
- [ ] Endpoint mutation tôn trọng `Idempotency-Key`, không tạo trùng giao dịch khi gọi lại
- [ ] Đã cân nhắc HITL: các bước POST liên tiếp không quá 4 lệnh gọi/lượt (giới hạn `agent_max_tool_rounds`), có bước "xem trước" bằng GET trước bước "xác nhận" bằng POST nếu hợp lý
- [ ] Nếu có `x-action-url-field`, path trỏ đúng vào field chứa URL trong `data`
- [ ] Nếu có webhook, đã test đúng key + đúng `service_code` + response chứa `booking_id`/`order_id`/`ride_id`
- [ ] Đã test qua `mock://` (luồng Agent) rồi mới test với backend thật
- [ ] Đã test full round-trip qua `POST /api/v1/chat` (thiếu field → Dynamic Form; mutation → HITL confirm → kết quả + deep-link)
- [ ] Không hardcode `outbound_api_key` hay bất kỳ secret nào vào OpenAPI spec/docs công khai
- [ ] Điền đầy đủ [biểu mẫu nộp Premium](../miniapps/premium-app-submission-template.md) trước khi gửi Admin duyệt

---

## 14. Lỗi thường gặp (pitfalls)

| Triệu chứng | Nguyên nhân thường gặp |
|---|---|
| Agent hỏi lại field người dùng đã cung cấp | `description` field không đủ rõ để LLM nhận diện, hoặc tên field trong OpenAPI không khớp cách người dùng diễn đạt |
| Dynamic Form hiển thị tên field kỹ thuật xấu (`pickup_location_code`) thay vì câu hỏi tự nhiên | Thiếu `description`, hoặc description không bắt đầu bằng câu ngắn gọn (label lấy từ mệnh đề đầu tiên trước dấu `(`, `.`, `:`, `,`) |
| Mọi hành động "đặt/huỷ/thanh toán" đều bị dừng lại chờ xác nhận dù đã set `x-requires-hitl: false` | Không tắt được — bất kỳ method khác GET nào **luôn** yêu cầu HITL, đây là chủ đích (xem mục 4) |
| Agent báo lỗi `"Yêu cầu này có vẻ hơi nhiều việc cùng lúc"` | Một lượt chat giới hạn tối đa 4 lần gọi tool (`agent_max_tool_rounds`, mặc định 4) — chia nhỏ flow |
| Nút deep-link trên web không mở gì cả | Bạn dùng scheme `xapp://...` — trình duyệt không hiểu; trả URL `http(s)://` thật nếu cần hoạt động trên web |
| Webhook gửi tới nhưng chat không cập nhật | Response ban đầu (lúc Agent gọi bạn) thiếu field `booking_id`/`order_id`/`ride_id` ở `data`, nên Platform API không map được `id -> thread_id` |
| Test thấy Gateway luôn trả `mock_gateway` giả dù đã có backend thật | `base_url` vẫn còn bắt đầu bằng `mock://` — sửa lại thành URL thật khi go-live |
| `x-api-key` không bao giờ tới mini-app | Quên set `outbound_api_key` lúc đăng ký (field này là tuỳ chọn — nếu bỏ trống thì Gateway không gửi header đó) |
| Gọi lại cùng 1 hành động (do người dùng bấm xác nhận 2 lần / mạng lag) tạo ra 2 đơn hàng | Chưa dùng `Idempotency-Key` để chặn xử lý trùng ở phía mini-app |
| Tạo/sửa service báo lỗi 400 "base_url must start with http://, https://, or mock://" | `base_url` phải có scheme hợp lệ — không chấp nhận domain trần (`example.com`) hay scheme khác |
| Service đang "Đã duyệt" bỗng quay lại "Chờ duyệt" sau khi bạn đổi Base URL/Outbound API Key | Đúng chủ đích — đổi các trường ảnh hưởng tới nơi Gateway gọi ra luôn cần Admin duyệt lại, Agent sẽ tạm ngưng gọi service này cho tới khi đó |

---

## Phụ lục: bảng tham chiếu nhanh endpoint Platform API liên quan

| Endpoint | Method | Ai gọi | Việc gì |
|---|---|---|---|
| `/api/v1/auth/partner-applications` | `POST` | User thường | Nộp đơn trở thành đối tác (mục 11.1) |
| `/api/v1/auth/partner-applications/me` | `GET` | User đã nộp đơn | Xem trạng thái đơn (PENDING/APPROVED/REJECTED) |
| `/api/v1/admin/partners/applications/{id}/review` | `POST` | Admin | Duyệt/từ chối đơn đối tác → role user thành `PREMIUM` nếu duyệt |
| `/api/v1/registry/services` | `POST` | Owner (PREMIUM/ADMIN) | Tạo service (draft) |
| `/api/v1/registry/services/{id}` | `PATCH`/`PUT` | Owner | Sửa metadata — đổi `base_url`/`outbound_api_key`/`is_sensitive` trên service đã `published` sẽ tự rơi về `pending_review`, phải chờ duyệt lại |
| `/api/v1/registry/services/{id}/versions` | `POST` | Owner | Tạo version kèm OpenAPI spec, tự chuyển `pending_review` |
| `/api/v1/registry/services` | `GET` | Owner | Xem danh sách service của chính mình |
| `/api/v1/admin/registry/services/{id}/approve` | `POST` | Admin (JWT + role ADMIN bắt buộc) | Duyệt → `published`/`active` |
| `/api/v1/admin/registry/services/{id}/reject` | `POST` | Admin | Từ chối kèm lý do |
| `/api/v1/admin/registry/services/{id}/deprecate` | `POST` | Admin | Ngừng hoạt động service đang chạy |
| `/api/v1/chat` | `POST` | End-user (đã login) | Bắt đầu/tiếp tục 1 turn chat với Agent |
| `/api/v1/chat/{thread_id}/resume` | `POST` | End-user | Gửi input còn thiếu hoặc bấm Xác nhận (HITL) |
| `/api/v1/webhooks/ride-status` | `POST` | **Mini-app của bạn** | Đẩy trạng thái async ngược về (mục 8) |
