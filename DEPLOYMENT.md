# Deployment Information

## Public URL

RENDER_URL_PLACEHOLDER

## Platform

**Render** (Blueprint từ `render.yaml` ở gốc repo, build Docker từ `06-lab-complete/Dockerfile`) + **Render Key Value** (Redis) cho rate limit và cost guard.

| Service | Loại | Ghi chú |
|---|---|---|
| `production-ai-agent` | Web service, runtime Docker, plan free | `rootDir: 06-lab-complete`, health check `/health` |
| `agent-redis` | Key Value (tương thích Redis), plan free | Chỉ truy cập nội bộ; `REDIS_URL` của agent lấy tự động bằng `fromService` |

## Test Commands

Đặt biến trước khi chạy (key lấy trong Render Dashboard → service `production-ai-agent` → Environment → `AGENT_API_KEY`, không ghi vào repo):

```bash
BASE=RENDER_URL_PLACEHOLDER
AGENT_API_KEY=<key trên Render>
```

### 4 lệnh tự kiểm (CP6) — mỗi lệnh chỉ in mã HTTP

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

Kết quả:

```text
CP6_RESULT_PLACEHOLDER
```

### Health Check

```bash
curl "$BASE/health"
# {"status":"ok","environment":"production"}
```

### API Test (with authentication)

```bash
curl -X POST "$BASE/ask" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

### Rate limit (10 req/phút) → 429

```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code} " -X POST "$BASE/ask" \
    -H "X-API-Key: $AGENT_API_KEY" -H 'Content-Type: application/json' -d '{"question":"Hi"}'
done; echo
```

### Script chấm với URL public

```bash
cd 06-lab-complete && python check_production_ready.py --public-url "$BASE"
```

## Environment Variables Set

| Biến | Giá trị / nguồn |
|---|---|
| `PORT` | Render tự cấp; `CMD` của Dockerfile đọc `${PORT:-8000}` |
| `ENVIRONMENT` | `production` |
| `AGENT_API_KEY` | `generateValue: true` — Render tự sinh, không có trong repo |
| `REDIS_URL` | `fromService` → connection string nội bộ của `agent-redis` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` / `MONTHLY_BUDGET_USD` | `1.0` / `10.0` |
| `LOG_LEVEL` | mặc định `INFO` (trong code) |

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
