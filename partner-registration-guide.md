# Hướng dẫn đăng ký Mini App cho Partner

Tài liệu này tóm tắt cách chuẩn bị hồ sơ đăng ký một Mini App lên Super App. Với EventBooking, dùng file `eventbooking-registration-fields.md` để điền nhanh các giá trị cụ thể.

## 1. Nguyên tắc bảo mật

- Không đưa API key, client secret, mật khẩu, JWT, Supabase key hoặc token vào Markdown, OpenAPI, mô tả công khai hay ví dụ request.
- Nếu có Outbound API Key, chỉ điền trong ô secret của dashboard và cấu hình cùng giá trị ở backend Mini App.
- Credential do Partner Portal cấp như `SUPERAPP_APP_ID`, `SUPERAPP_KEY_ID`, `SUPERAPP_API_KEY` chỉ lưu ở backend.

## 2. Thông tin cơ bản

| Trường | Cách điền |
|---|---|
| Mã dịch vụ | Mã duy nhất của Mini App, ví dụ `EVENT_BOOKING`. |
| Tên dịch vụ | Tên hiển thị cho người dùng. |
| Mô tả chi tiết | Mô tả chức năng chính, giới hạn demo/production và các thao tác Agent có thể gọi. |
| Danh mục | Nhóm nghiệp vụ chính, ví dụ `EVENTS` hoặc `ENTERTAINMENT`. |
| Base URL API | URL gốc của backend, không thêm path endpoint. |
| Health Check URL | Endpoint health check trả HTTP 200. |
| Dịch vụ nhạy cảm | Bật nếu có tạo đơn, hủy đơn, thanh toán hoặc thay đổi dữ liệu. |

## 3. Cấu hình API

Nên upload file OpenAPI JSON thay vì nhập tay từng endpoint.

Checklist OpenAPI:

- Có `openapi`, `info`, `servers`, `paths`.
- `servers[0].url` khớp Base URL API.
- Mỗi operation có `operationId` duy nhất và ổn định.
- Request field có `description` rõ ràng bằng tiếng Việt để Dynamic Form hiển thị dễ hiểu.
- Mutation có header `Idempotency-Key`.
- Mutation có metadata `x-superapp`, `x-idempotency-required: true`, `x-requires-hitl: true`.
- Không khai báo secret trong `security`, `example`, `description` hoặc `servers`.

## 4. Cấu hình AI

| Trường | Cách điền |
|---|---|
| Deep Link Template | URL mở màn hình liên quan sau khi thao tác thành công, ví dụ `https://example.com/checkout/{booking_id}`. |
| Required Scopes | Để trống nếu mọi end-user đã đăng nhập đều được dùng, hoặc dùng scope do Super App hỗ trợ. |
| Sample Intents | Ít nhất 5 câu người dùng có thể hỏi để Agent nhận diện đúng dịch vụ. |

## 5. Luồng sau khi gửi

1. Partner submit thông tin dịch vụ và OpenAPI.
2. Platform kiểm tra schema, endpoint, quyền và metadata rủi ro.
3. Service chuyển sang trạng thái chờ duyệt.
4. Admin phê duyệt hoặc từ chối.
5. Sau khi publish, Catalog và Agent mới có thể gọi Mini App.

## 6. Kiểm tra trước khi submit

- [ ] Base URL truy cập được từ Platform.
- [ ] Health check trả HTTP 200.
- [ ] OpenAPI JSON parse hợp lệ.
- [ ] Mutation retry cùng `Idempotency-Key` không tạo duplicate operation.
- [ ] Mutation thành công trả `operation_id` đúng định dạng `<domain>-<opaque-id>`.
- [ ] Lỗi nghiệp vụ trả envelope `status: failure` và `error.code` ổn định.
- [ ] Không có secret trong tài liệu hoặc OpenAPI.
