# EventBooking

Mini-app đặt vé sự kiện độc lập để Super App có thể gọi qua Gateway.

## Chạy local

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn main:app --reload --port 8501
```

Git Bash:

```bash
cd /d/CODE/AITHUCCHIEN/miniapp/EventBooking
./.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8501
```

Mở:

- UI cơ bản: <http://localhost:8501/>
- Swagger/OpenAPI: <http://localhost:8501/docs>
- Health check: <http://localhost:8501/health>

## Thông tin đăng ký Super App

- `service_code`: `EVENT_BOOKING`
- `name`: `Đặt Vé Sự Kiện & Hội Nghị`
- `category`: `EVENTS`
- `base_url`: `http://localhost:8501`
- `health_check_url`: `http://localhost:8501/health`
- `deep_link_template`: `http://localhost:8501/checkout/{booking_id}`

Endpoint chính:

- `GET /events` - tìm sự kiện
- `GET /events/{event_id}` - xem chi tiết sự kiện
- `GET /tickets/estimate` - ước tính tổng tiền
- `POST /bookings` - đặt vé, yêu cầu `Idempotency-Key`
- `GET /bookings/{booking_id}` - kiểm tra trạng thái đơn
- `POST /bookings/{booking_id}/cancel` - hủy vé, yêu cầu `Idempotency-Key`

Supabase chưa bắt buộc. Khi có key, điền `SUPABASE_URL` và `SUPABASE_ANON_KEY` hoặc `SUPABASE_SERVICE_ROLE_KEY` trong `.env`; bản hiện tại dùng dữ liệu mẫu in-memory để chạy và test contract trước.
