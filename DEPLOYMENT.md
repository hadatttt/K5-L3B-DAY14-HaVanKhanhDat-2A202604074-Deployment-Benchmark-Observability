# Deployment Information

## Public URL

https://production-ai-agent-cp8l.onrender.com

## Platform

**Render** (Blueprint từ `render.yaml` ở gốc repo, build Docker từ `06-lab-complete/Dockerfile`) + **Render Key Value** (Redis) cho rate limit và cost guard.

| Service | Loại | Ghi chú |
|---|---|---|
| `production-ai-agent` | Web service, runtime Docker, plan free | `rootDir: 06-lab-complete`, health check `/health` |
| `agent-redis` | Key Value (tương thích Redis), plan free | Chỉ truy cập nội bộ; `REDIS_URL` của agent lấy tự động bằng `fromService` |

## Test Commands

Đặt biến trước khi chạy (key lấy trong Render Dashboard → service `production-ai-agent` → Environment → `AGENT_API_KEY`, không ghi vào repo):

```bash
BASE=https://production-ai-agent-cp8l.onrender.com
AGENT_API_KEY=<key trên Render>
```

### 4 lệnh tự kiểm (CP6) — mỗi lệnh chỉ in mã HTTP

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

Kết quả chạy ngày 2026-11-26 (ảnh: [screenshots/test.png](screenshots/test.png)):

```text
$ BASE=https://production-ai-agent-cp8l.onrender.com
$ curl ... $BASE/health
200
$ curl ... $BASE/ready
200
$ curl ... POST /ask (không key)
401
$ curl ... POST /ask -H "X-API-Key: $AGENT_API_KEY"
200
$ curl ... POST /ask có key (body)
{"question":"What is deployment?","answer":"Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được."}
$ rate limit: 12 request liên tiếp (RATE_LIMIT_PER_MINUTE=10)
200 200 200 200 200 200 200 200 429 429 429 429
```

Rate limit: 2 request có key ở trên đã tính vào cửa sổ 60 giây, nên vòng 12 request chỉ còn 8 lượt 200 rồi chuyển 429 (tổng 10 request/phút). State nằm trong Render Key Value (Redis) nên dùng chung khi service restart hoặc scale.

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
