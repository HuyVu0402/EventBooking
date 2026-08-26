# Hướng dẫn đăng ký Mini App cho Partner

Tài liệu này giúp Partner chuẩn bị hồ sơ để đăng ký dịch vụ lên Xclvia Super
App. Hồ sơ gồm ba phần: thông tin cơ bản, cấu hình API và cấu hình AI.

> Không đưa API key, client secret, mật khẩu hoặc token vào file JSON,
> Markdown, OpenAPI hay phần mô tả công khai.

## 1. Thông tin cơ bản

Điền tại bước **Thông tin cơ bản**:

| Trường | Cách điền | Ví dụ |
|---|---|---|
| Mã dịch vụ | Mã duy nhất, chữ thường, dùng dấu gạch dưới | home_repair |
| Tên dịch vụ | Tên hiển thị cho người dùng | Sửa chữa nhà X |
| Mô tả chi tiết | Nêu dịch vụ cung cấp và giới hạn | Tiếp nhận và theo dõi yêu cầu sửa chữa tại nhà. |
| Danh mục | Nhóm nghiệp vụ chính | Dịch vụ gia đình |
| Base URL API | URL gốc, không bao gồm path endpoint | https://home-repair.example.com |

Mẫu:

~~~text
Mã dịch vụ: home_repair
Tên dịch vụ: Sửa chữa nhà X
Mô tả: Tiếp nhận yêu cầu sửa điện, nước và thiết bị gia dụng tại nhà.
Danh mục: Dịch vụ gia đình
Base URL API: https://home-repair.example.com
~~~

## 2. Cấu hình API

Partner có thể khai báo endpoint trực tiếp trên biểu mẫu hoặc tải lên file
OpenAPI JSON. Nên dùng file JSON để giảm lỗi nhập liệu và dễ quản lý phiên bản.

### 2.1. Quy tắc OpenAPI

- Dùng chuẩn OpenAPI 3.0.x hoặc 3.1.x.
- Có các phần openapi, info, servers và paths.
- servers[0].url phải trùng hoặc tương thích với Base URL API.
- Mỗi endpoint có summary và operationId duy nhất.
- operationId viết bằng tiếng Anh, không có khoảng trắng.
- Biến trong path phải có tham số in là path và required là true.
- Tham số tìm kiếm dùng in là query.
- POST, PUT, PATCH phải khai báo requestBody nếu có dữ liệu gửi lên.
- Không khai báo secret trong security, example, description hoặc servers.

### 2.2. File OpenAPI JSON mẫu

Lưu nội dung sau thành file home-repair-openapi.json, sau đó chọn **Tải file
OpenAPI JSON** tại bước **Cấu hình API**.

~~~json
{
  "openapi": "3.0.3",
  "info": {
    "title": "Home Repair API",
    "version": "1.0.0",
    "description": "API tiếp nhận, tra cứu và hủy yêu cầu sửa chữa tại nhà."
  },
  "servers": [
    {
      "url": "https://home-repair.example.com"
    }
  ],
  "paths": {
    "/v1/repair-services": {
      "get": {
        "summary": "Tra cứu loại dịch vụ sửa chữa",
        "operationId": "search_repair_services",
        "parameters": [
          {
            "name": "keyword",
            "in": "query",
            "required": false,
            "description": "Từ khóa như điện, nước hoặc thiết bị gia dụng.",
            "schema": { "type": "string" }
          },
          {
            "name": "location",
            "in": "query",
            "required": false,
            "description": "Khu vực cần cung cấp dịch vụ.",
            "schema": { "type": "string" }
          }
        ],
        "responses": {
          "200": {
            "description": "Danh sách dịch vụ phù hợp.",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "items": {
                      "type": "array",
                      "items": { "$ref": "#/components/schemas/RepairService" }
                    }
                  }
                }
              }
            }
          }
        }
      }
    },
    "/v1/repair-requests": {
      "post": {
        "summary": "Tạo yêu cầu sửa chữa tại nhà",
        "operationId": "create_repair_request",
        "parameters": [
          {
            "name": "Idempotency-Key",
            "in": "header",
            "required": true,
            "description": "Khóa duy nhất cho mỗi lần tạo yêu cầu.",
            "schema": { "type": "string" }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": { "$ref": "#/components/schemas/CreateRepairRequest" }
            }
          }
        },
        "responses": {
          "201": { "description": "Đã tạo yêu cầu sửa chữa." },
          "400": { "description": "Dữ liệu không hợp lệ." }
        }
      }
    },
    "/v1/repair-requests/{request_id}": {
      "get": {
        "summary": "Xem trạng thái yêu cầu sửa chữa",
        "operationId": "get_repair_request",
        "parameters": [
          {
            "name": "request_id",
            "in": "path",
            "required": true,
            "description": "Mã yêu cầu sửa chữa.",
            "schema": { "type": "string" }
          }
        ],
        "responses": {
          "200": { "description": "Thông tin yêu cầu." },
          "404": { "description": "Không tìm thấy yêu cầu." }
        }
      },
      "delete": {
        "summary": "Hủy yêu cầu sửa chữa",
        "operationId": "cancel_repair_request",
        "parameters": [
          {
            "name": "request_id",
            "in": "path",
            "required": true,
            "description": "Mã yêu cầu cần hủy.",
            "schema": { "type": "string" }
          },
          {
            "name": "Idempotency-Key",
            "in": "header",
            "required": true,
            "description": "Khóa duy nhất cho thao tác hủy.",
            "schema": { "type": "string" }
          }
        ],
        "responses": {
          "200": { "description": "Đã hủy yêu cầu." },
          "409": { "description": "Yêu cầu không thể hủy ở trạng thái hiện tại." }
        }
      }
    }
  },
  "components": {
    "schemas": {
      "RepairService": {
        "type": "object",
        "required": ["code", "name"],
        "properties": {
          "code": {
            "type": "string",
            "description": "Mã loại dịch vụ.",
            "example": "plumbing"
          },
          "name": {
            "type": "string",
            "description": "Tên loại dịch vụ.",
            "example": "Sửa đường nước"
          }
        }
      },
      "CreateRepairRequest": {
        "type": "object",
        "required": [
          "service_code",
          "customer_name",
          "phone",
          "address",
          "description"
        ],
        "properties": {
          "service_code": {
            "type": "string",
            "description": "Mã loại dịch vụ cần sửa.",
            "example": "plumbing"
          },
          "customer_name": {
            "type": "string",
            "description": "Họ và tên người yêu cầu.",
            "example": "Nguyễn Văn An"
          },
          "phone": {
            "type": "string",
            "description": "Số điện thoại liên hệ.",
            "example": "0901234567"
          },
          "address": {
            "type": "string",
            "description": "Địa chỉ cần cung cấp dịch vụ.",
            "example": "250 Kim Giang, Hà Nội"
          },
          "description": {
            "type": "string",
            "description": "Mô tả hiện trạng cần sửa.",
            "example": "Vòi nước nhà bếp bị rò rỉ."
          },
          "preferred_time": {
            "type": "string",
            "format": "date-time",
            "description": "Thời gian mong muốn, nếu có."
          }
        }
      }
    }
  }
}
~~~

### 2.3. Kiểm tra file JSON

Trên PowerShell:

~~~powershell
Get-Content .\home-repair-openapi.json | ConvertFrom-Json | Out-Null
~~~

Trên Git Bash nếu đã cài jq:

~~~bash
jq empty home-repair-openapi.json
~~~

Kiểm tra cú pháp JSON thành công chưa đủ; Partner vẫn cần gọi thử endpoint bằng
Swagger UI hoặc Postman.

## 3. Cấu hình AI

Sau khi tải JSON, hệ thống tự trích xuất endpoint. Partner bổ sung:

| Trường | Cách điền | Ví dụ |
|---|---|---|
| Deep Link Template | URL mở màn hình của mini-app; dùng biến trong dấu ngoặc nhọn | xclvia://home-repair/request/{request_id} |
| Sample Intents | Câu người dùng thường nói, ngăn cách bằng dấu phẩy | tôi cần sửa vòi nước, đặt thợ sửa điện, kiểm tra yêu cầu sửa nhà |
| Dịch vụ nhạy cảm | Bật nếu có tạo, hủy, thanh toán hoặc thay đổi dữ liệu | Bật |

Mẫu:

~~~text
Deep Link Template:
xclvia://home-repair/request/{request_id}

Sample Intents:
tôi cần sửa vòi nước, đặt thợ sửa điện, sửa điều hòa tại nhà,
kiểm tra yêu cầu sửa chữa, hủy yêu cầu sửa nhà

Dịch vụ nhạy cảm: Bật
~~~

Agent dùng summary, operationId, mô tả tham số, request body và sample intents
để chọn endpoint. Khi Partner thêm service mới, không cần sửa code Agent; service
cần được duyệt và publish trong Catalog trước khi được sử dụng.

## 4. Checklist trước khi gửi duyệt

- [ ] service_code là duy nhất.
- [ ] Base URL truy cập được từ Platform API.
- [ ] File OpenAPI có cú pháp hợp lệ.
- [ ] Mỗi operation có operationId duy nhất.
- [ ] GET có đủ query/path parameters.
- [ ] POST/PUT/PATCH có request body và required fields.
- [ ] DELETE có quy tắc hủy rõ ràng.
- [ ] Mutation có Idempotency-Key.
- [ ] Không có secret trong OpenAPI hoặc tài liệu.
- [ ] Deep link mở đúng màn hình.
- [ ] Có tối thiểu 5 sample intents.
- [ ] Đã kiểm thử các mã lỗi 400, 404, 409 và 500.
- [ ] Đã xác định hành động cần HITL xác nhận.

## 5. Luồng sau khi gửi

1. Partner gửi thông tin và OpenAPI lên Platform.
2. Platform kiểm tra schema, endpoint, quyền và chính sách rủi ro.
3. Service chuyển sang trạng thái chờ duyệt.
4. Admin kiểm tra hồ sơ, API và phê duyệt hoặc từ chối.
5. Sau khi publish, Catalog và Agent mới được sử dụng service.
6. Khi thay đổi Base URL, OpenAPI hoặc chính sách nhạy cảm, version cần được
   kiểm tra lại.
