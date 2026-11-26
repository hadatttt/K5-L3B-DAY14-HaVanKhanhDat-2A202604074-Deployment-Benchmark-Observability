# Day 14 Lab - Mission Answers

**Học viên:** Hà Văn Khánh Đạt · **Lớp:** K5-L3B · **Ngày làm:** 2026-11-26
**Môi trường:** Windows 11 + WSL2 (Ubuntu 22.04, Python 3.11.18), Docker Desktop 29.9.3

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found (`01-localhost-vs-production/develop/app.py`)

1. **Hard-code secret** — `OPENAI_API_KEY` (dòng 17) và `DATABASE_URL` có cả mật khẩu (dòng 18) nằm thẳng trong code → lộ khi push lên Git.
2. **Log ra secret** — dòng 34 `print` cả API key ra stdout (thấy trong log khi chạy: `[DEBUG] Using key: sk-hard****`).
3. **Config cố định, không đọc env** — `DEBUG = True`, `MAX_TOKENS` (dòng 21–22); muốn đổi phải sửa code.
4. **Dùng `print()` thay vì logging** (dòng 33, 34, 38, 48) — không có level, không có format, không parse được.
5. **Không có health check** (dòng 42–43 chỉ là comment) — `curl /health` trả **404**, platform không biết app còn sống hay đã chết.
6. **Host/port cố định** — `host="localhost"` (dòng 51) nên container/cloud không truy cập được từ ngoài; `port=8000` (dòng 52) bỏ qua biến `PORT` do platform cấp.
7. **`reload=True` trong lúc chạy** (dòng 53) — chế độ dev, tốn tài nguyên, không dùng cho production.
8. **Không xử lý shutdown** — không có lifespan/SIGTERM handler, không có `/ready`.

### Exercise 1.2: Chạy basic version

```text
$ curl -X POST "http://localhost:8000/ask?question=Hello"
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
$ curl -i http://localhost:8000/health
HTTP/1.1 404 Not Found
```

Chạy được, nhưng chưa production-ready: không có health check, secret nằm trong code và bị in ra log.

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | Hard-code trong `app.py` (key, DB URL, DEBUG) | Đọc env qua `config.py` (dòng 17–35), `validate()` báo lỗi nếu thiếu `AGENT_API_KEY` ở production | Cùng một code chạy dev/staging/prod; secret không vào Git |
| Secret trong log | In thẳng API key | Chỉ log độ dài câu hỏi, client IP (dòng 111–115) | Log thường được gửi đi nhiều nơi, lộ key = mất tiền |
| Health check | Không có (404) | `/health` liveness (dòng 135–149), `/ready` readiness trả 503 khi chưa sẵn sàng (dòng 152–161) | Platform restart khi chết, LB chỉ route vào instance sẵn sàng |
| Logging | `print()` | `logging` với format JSON (dòng 16–19) | Tìm kiếm, lọc, cảnh báo được trên hệ thống log tập trung |
| Shutdown | Đột ngột | Lifespan (dòng 39–67) đặt `is_ready=False` rồi dọn dẹp; uvicorn chờ request đang chạy | Không cắt ngang request của người dùng khi deploy/scale |
| Host/Port | `localhost:8000` cố định | `0.0.0.0` + `PORT` từ env (dòng 193–198) | Cloud cấp port động; container phải nghe ở mọi interface |
| Reload/Debug | `reload=True` luôn bật | `reload=settings.debug` | Debug mode chậm và có thể lộ thông tin |

Output bản production:

```text
$ curl /health
{"status":"ok","uptime_seconds":0.2,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T07:55:51.784551+00:00"}
$ curl /ready
{"ready":true}
$ curl -X POST /ask -H 'Content-Type: application/json' -d '{"question":"Hello"}'
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}
```

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` (bản đầy đủ, dòng 8).
2. **Working directory:** `/app` (dòng 11).
3. **Vì sao COPY `requirements.txt` trước:** Docker cache theo layer. Copy `requirements.txt` + `pip install` (dòng 14–17) trước khi copy code (dòng 20–24) thì khi chỉ sửa code, layer cài dependencies vẫn dùng cache → build lại nhanh hơn nhiều. Nếu `COPY . .` trước, mọi thay đổi code đều làm cài lại toàn bộ thư viện.
4. **CMD vs ENTRYPOINT:** `ENTRYPOINT` là lệnh cố định của container; `CMD` là lệnh/tham số mặc định, bị ghi đè khi `docker run image <lệnh khác>`. Khi có cả hai, `CMD` thành tham số cho `ENTRYPOINT`. File này chỉ dùng `CMD ["python", "app.py"]` (dòng 30, exec form → python là PID 1, nhận được SIGTERM).

### Exercise 2.2: Build và run

Build từ gốc repo: `docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .`

```text
$ docker run -d -p 8000:8000 my-agent:develop
$ curl -X POST "http://localhost:8000/ask?question=What%20is%20Docker?"
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

Image develop nặng **1.67 GB** (đo ở 2.3) vì base `python:3.11` đầy đủ có cả compiler, header, tài liệu.

### Exercise 2.3: Multi-stage build (`02-docker/production/Dockerfile`)

- **Stage 1 (builder, `python:3.11-slim`):** cài `gcc`, `libpq-dev` rồi `pip install --user` dependencies vào `/root/.local`.
- **Stage 2 (runtime, `python:3.11-slim`):** tạo user `appuser`, chỉ copy `/root/.local` từ builder và code (`main.py`, `utils/mock_llm.py`), chạy bằng `USER appuser`, có `HEALTHCHECK /health`, CMD `uvicorn ... --workers 2`.
- **Vì sao nhỏ hơn:** base slim thay vì full; compiler, apt cache, file tạm của pip ở lại stage builder, không vào image cuối.

**Image size comparison** (`docker images`, đo trên máy mình):

```text
REPOSITORY:TAG        SIZE
my-agent:advanced     240MB     (239,815,462 bytes)
my-agent:develop      1.67GB    (1,667,779,915 bytes)
```

- Develop: **1667.8 MB**
- Production: **239.8 MB**
- Difference: production nhỏ hơn **85.6%** (chỉ bằng 14.4% bản develop, nhỏ hơn ~7 lần)

### Exercise 2.4: Docker Compose stack

Chạy: `cd 02-docker/production && touch .env.local && docker compose -p k5-day14-docker up -d --build`

```text
                 host :80 (và :443)
                        │
                ┌───────▼────────┐
                │ nginx:alpine   │  reverse proxy / load balancer
                └───────┬────────┘  upstream agent_backend → agent:8000
                        │  mạng nội bộ (bridge "internal")
                ┌───────▼────────┐
                │ agent (FastAPI)│  không publish port ra host
                └───┬────────┬───┘
       depends_on   │        │   depends_on (service_healthy)
          ┌─────────▼──┐  ┌──▼──────────────┐
          │ redis:7    │  │ qdrant v1.9.0   │
          │ (cache)    │  │ (vector DB)     │
          └────────────┘  └─────────────────┘
```

Services được start (4): `redis`, `qdrant` khởi động trước và phải **healthy**, sau đó `agent`, cuối cùng `nginx`.

```text
k5-day14-docker-agent-1   Up 8 seconds (healthy)   8000/tcp
k5-day14-docker-nginx-1   Up 8 seconds             0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
k5-day14-docker-qdrant-1  Up 19 seconds (healthy)  6333-6334/tcp
k5-day14-docker-redis-1   Up 19 seconds (healthy)  6379/tcp

$ curl -i http://localhost/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":6.8,"version":"2.0.0","timestamp":"2026-11-26T08:13:28.797961"}

$ curl -i -X POST http://localhost/ask -H 'Content-Type: application/json' -d '{"question":"Explain microservices"}'
HTTP/1.1 200 OK
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}

nginx-1 | 172.20.0.1 - - [26/Nov/2026:08:13:28 +0000] "POST /ask HTTP/1.1" 200 95 "-" "curl/7.81.0"
```

**Giao tiếp:** các container nằm chung một bridge network, gọi nhau bằng **tên service** qua DNS nội bộ của Docker (`agent:8000`, `redis:6379`, `qdrant:6333`). Chỉ nginx publish port ra host, nên agent/redis/qdrant không bị truy cập trực tiếp từ ngoài. Nhận xét: compose cấp `REDIS_URL`/`QDRANT_URL` nhưng `main.py` bản mẫu chưa dùng tới; nginx publish 443 nhưng `nginx.conf` chỉ listen 80.

---

## Part 3: Cloud Deployment

### Exercise 3.2: Render deployment (agent Part 6 — nền tảng chính)

- Nền tảng: **Render**, Blueprint `render.yaml` (gốc repo, trỏ `rootDir: 06-lab-complete`) gồm web service Docker + Key Value (Redis)
- URL: https://production-ai-agent-cp8l.onrender.com (xem [DEPLOYMENT.md](DEPLOYMENT.md))
- Kiểm tra CP6 trên URL public: `/health` 200, `/ready` 200, `/ask` không key 401, có key 200; 12 request liên tiếp → 429 sau 10 request/phút
- Screenshot: [dashboard](screenshots/dashboard.png) · [running](screenshots/running.png) · [test](screenshots/test.png)
- Chi tiết lệnh và biến môi trường: [DEPLOYMENT.md](DEPLOYMENT.md)

### So sánh `railway.toml` và `render.yaml` (của `06-lab-complete/`)

| Điểm | `railway.toml` | `render.yaml` |
|---|---|---|
| Phạm vi | Chỉ cấu hình **một service** (build + deploy) | **Blueprint** mô tả cả hạ tầng: web service + Redis (`keyvalue`) |
| Build | `builder = "DOCKERFILE"` | `runtime: docker`, `dockerfilePath`, `rootDir: 06-lab-complete` |
| Health check | `healthcheckPath = "/health"`, `healthcheckTimeout` | `healthCheckPath: /health` |
| Restart | `restartPolicyType = "ON_FAILURE"`, tối đa 3 lần | Render tự restart, không cần khai báo |
| Secret | Không ghi trong file; đặt bằng `railway variables set` / dashboard | `AGENT_API_KEY: generateValue: true` (Render tự sinh), có thể dùng `sync: false` để nhập tay |
| Redis | Tạo Redis plugin riêng rồi đặt `REDIS_URL` bằng tay | `REDIS_URL` lấy tự động `fromService ... property: connectionString` |
| Port | Railway cấp `PORT`, CMD đọc `${PORT:-8000}` | Giống vậy |

**Vì sao khác:** Railway thiên về "deploy một thư mục bằng CLI", cấu hình còn lại nằm trên dashboard; Render theo hướng Infrastructure-as-Code nên một file khai báo đủ các service và cách chúng nối với nhau.

### Exercise 3.3: Cloud Run CI/CD (`03-cloud-deployment/production-cloud-run/`)

1. `cloudbuild.yaml` chạy khi có push: bước **test** cài requirements và chạy `pytest tests/`.
2. Bước **build** `docker build` gắn tag `$COMMIT_SHA` và `latest`, dùng `--cache-from latest` để build nhanh.
3. Bước **push** đẩy image lên `gcr.io/$PROJECT_ID/ai-agent`.
4. Bước **deploy** `gcloud run deploy ai-agent` ở `asia-southeast1`, min 1 / max 10 instance, 512Mi, 1 CPU, timeout 60s, `OPENAI_API_KEY` lấy từ Secret Manager (không nằm trong repo).
5. `service.yaml` là bản khai báo Knative tương ứng: `containerConcurrency: 80`, liveness `/health`, startup probe `/ready`, secret mount từ Secret Manager — test fail thì pipeline dừng, không có image lỗi lên production.

---

## Part 4: API Security

### Exercise 4.1: API Key (`04-api-gateway/develop`, chạy `AGENT_API_KEY=secret-key-123 python app.py`)

```text
--- không có key
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
--- sai key
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}
--- đúng key (X-API-Key: secret-key-123)
HTTP/1.1 200 OK
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

Key được kiểm tra qua header `X-API-Key`, so với biến môi trường `AGENT_API_KEY`. Muốn rotate key: đổi biến môi trường và restart, không cần sửa code.

### Exercise 4.2: JWT (`04-api-gateway/production`)

```text
$ curl -X POST /auth/token -d '{"username":"student","password":"demo123"}'
{"access_token": "eyJhbGciOiJI...<redacted>", "token_type": "bearer", "expires_in_minutes": 60, ...}
--- /ask không token
HTTP/1.1 401 Unauthorized
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
--- /ask token sai
HTTP/1.1 403 Forbidden
{"detail":"Invalid token."}
--- /ask token đúng
HTTP/1.1 200 OK
{"question":"What is JWT?","answer":"...","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

JWT ký HS256, có claim `sub`, `role`, `iat`, `exp` (hết hạn sau 60 phút). Server chỉ cần kiểm chữ ký, không cần tra DB mỗi request.

### Exercise 4.3: Rate limiting (token của `student`, giới hạn 10 req/phút)

```text
request 1 -> 200      (request đầu ở 4.2 cũng tính, nên còn 9 lượt)
request 2..9 -> 200
request 10 -> 429 retry-after: 59
request 11 -> 429 retry-after: 59
request 12 -> 429 retry-after: 59

HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
retry-after: 59
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

Thuật toán: sliding window log — lưu timestamp từng request trong 60s gần nhất, user 10 req/phút, admin 100 req/phút. Bản này lưu trong RAM nên không dùng chung giữa nhiều instance; ở Part 6 mình chuyển sang Redis sorted set.

### Exercise 4.4: Cost guard implementation

- **Bản mẫu (`04-api-gateway/production/cost_guard.py`):** ước token rồi tính tiền theo giá gpt-4o-mini ($0.00015/1K input, $0.0006/1K output). Kiểm tra **trước** khi gọi LLM: user vượt $1/ngày → **402**, toàn hệ thống vượt $10 → **503**; ghi nhận chi phí **sau** khi có response. Lưu trong dict RAM, reset theo ngày. `/me/usage` sau 10 request: `cost_usd 0.000191, budget_usd 1.0`.
  Nhận xét: `_global_cost` không bao giờ reset theo ngày (biến `_global_today` không được dùng) và state mất khi restart.
- **Bản của mình (Part 6, `06-lab-complete/app/cost_guard.py`):**
  1. `check_budget()` chạy trước LLM: đọc `cost:daily:YYYY-MM-DD` và `cost:monthly:YYYY-MM` trong Redis bằng `MGET`; vượt `DAILY_BUDGET_USD` hoặc `MONTHLY_BUDGET_USD` → **402**.
  2. `record_cost()` chạy sau LLM: `INCRBYFLOAT` cả hai key trong một pipeline, đặt `EXPIRE` (2 ngày / 32 ngày) để key tự dọn.
  3. Redis lỗi → 503 thay vì cho qua, tránh tiêu tiền không kiểm soát.
  4. Vì state ở Redis nên mọi worker/instance dùng chung một ngân sách và không mất khi restart.
- **Rate limit vs cost guard:** rate limit chặn *tốc độ* (spam, DoS), cost guard chặn *tổng tiền* (nhiều request hợp lệ nhưng prompt dài / model đắt). Cần cả hai.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks (`05-scaling-reliability/develop`)

```text
$ curl /health
{"status":"ok","uptime_seconds":0.4,"version":"1.0.0","environment":"development",...,"checks":{"memory":{"status":"ok","used_percent":18.3}}}
$ curl -i /ready
HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}
```

- **Liveness `/health`:** process còn sống không. Fail → platform **restart** container. Không được phụ thuộc vào Redis/DB, nếu không Redis chập chờn sẽ làm restart hàng loạt.
- **Readiness `/ready`:** instance sẵn sàng nhận traffic chưa (đã load xong, kết nối dependency OK). Fail → LB **ngừng gửi traffic** nhưng không restart. Lúc startup và lúc shutdown đều trả 503.

### Exercise 5.2: Graceful shutdown

Gửi một request `/ask` rồi gửi SIGTERM ngay sau 0.1s:

```text
in-flight response: {"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."} [HTTP 200]
[server exit code 0]
INFO:     Shutting down
INFO:     127.0.0.1:47648 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
INFO 🔄 Graceful shutdown initiated...
INFO ✅ Shutdown complete
INFO:     Finished server process [2569]
```

Request đang chạy vẫn trả 200, process thoát với code 0. Cơ chế: uvicorn bắt SIGTERM → ngừng nhận kết nối mới → chờ request in-flight (`timeout_graceful_shutdown=30`) → chạy phần shutdown của lifespan (đặt `_is_ready=False`, chờ bộ đếm in-flight về 0). Handler SIGTERM tự viết chỉ log, không chặn handler của uvicorn.

### Exercise 5.3: Stateless design

`05-scaling-reliability/production/app.py` lưu session ở Redis với key `session:{id}`, TTL 3600s, giữ tối đa 20 lượt chat. Instance không giữ state trong RAM nên request kế tiếp đến instance nào cũng đọc được lịch sử. (Nếu Redis không có, app fallback sang dict trong RAM — chạy được nhưng mất tính stateless.)

### Exercise 5.4 & 5.5: Load balancing + test stateless

Trong `05-scaling-reliability/production/`:
`docker compose -p k5-day14-scaling up -d --build --scale agent=3` rồi `python test_stateless.py`.

```text
k5-day14-scaling-agent-1   Up (health: starting)   8000/tcp
k5-day14-scaling-agent-2   Up (health: starting)   8000/tcp
k5-day14-scaling-agent-3   Up (health: starting)   8000/tcp
k5-day14-scaling-nginx-1   Up                      0.0.0.0:8080->80/tcp
k5-day14-scaling-redis-1   Up (healthy)            6379/tcp

# 6 request /health qua Nginx, header X-Served-By
X-Served-By: 172.19.0.4:8000
X-Served-By: 172.19.0.3:8000
X-Served-By: 172.19.0.4:8000
X-Served-By: 172.19.0.3:8000   (round-robin luân phiên)
...
```

Output `test_stateless.py`:

```text
Session ID: 3ec70e09-dc58-4731-b5ac-a9f12b3895a8
Request 1: [instance-4d5cef]  Q: What is Docker?
Request 2: [instance-6052cd]  Q: Why do we need containers?
Request 3: [instance-4d5cef]  Q: What is Kubernetes?
Request 4: [instance-6052cd]  Q: How does load balancing work?
Request 5: [instance-4d5cef]  Q: What is Redis used for?
Total requests: 5
Instances used: {'instance-4d5cef', 'instance-6052cd'}
✅ All requests served despite different instances!
--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!

$ redis-cli --scan --pattern 'session:*'
session:3ec70e09-dc58-4731-b5ac-a9f12b3895a8
```

**Giải thích:**
- Nginx (upstream `agent_cluster`, round-robin) chia request luân phiên cho các instance; 5 câu của **cùng một session** rơi vào 2 instance khác nhau nhưng lịch sử vẫn đủ **10 message** (5 hỏi + 5 đáp), vì mỗi instance đọc/ghi session ở Redis (`session:<id>`) chứ không giữ trong RAM. Nếu lưu trong RAM, instance thứ hai sẽ không thấy các lượt trước.
- Chỉ thấy 2 trong 3 instance trả lời: lúc chạy test cả 3 agent vừa khởi động (`health: starting`) và Nginx chỉ phân giải `agent` lúc nó start, nên mới thấy 2 địa chỉ. Đây là hạn chế của Nginx open-source khi dùng `server agent:8000` không có `resolve`; stack ở Part 7 dùng `resolve` để tự cập nhật.
- Script không tự tắt instance nào, nên mình thử thêm: tạo session mới, `docker stop k5-day14-scaling-agent-1`, rồi gửi tiếp 3 câu cùng `session_id`:

```text
stopped agent-1
turn 3 served_by instance-4d5cef storage redis
turn 4 served_by instance-4d5cef storage redis
turn 5 served_by instance-4d5cef storage redis
history messages: 8
```

Instance còn lại tiếp tục cuộc hội thoại, lịch sử không mất (`storage: redis`). Nginx có `proxy_next_upstream error timeout http_503` nên request tới instance chết được chuyển sang instance khác, người dùng không thấy lỗi.

---

## Part 6: Final Project — output `check_production_ready.py`

Chạy trong WSL2 (`os.name == posix`), bản đầy đủ có Docker: `cd 06-lab-complete && python check_production_ready.py`

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

Một vài dòng chi tiết đáng chú ý: image **273 MB**; `429 sau 5 request thành công (RATE_LIMIT_PER_MINUTE=5)`; `restart agent vẫn bị 429` (state trong Redis); `Redis mất kết nối → /ready 503 (còn /health vẫn 200)`; `docker stop tắt êm — exit code 0, 0.8s`.

**Cách làm từng phần (`06-lab-complete/app/`):**

| Tiêu chí | Cách làm |
|---|---|
| Config | `config.py` đọc mọi giá trị từ env bằng `os.getenv` (có ép kiểu an toàn), `.env.example` liệt kê đủ biến, không có secret thật |
| `/health` vs `/ready` | `/health` không chạm Redis nên luôn 200 khi process sống; `/ready` gọi `redis.ping()` (timeout 2s), lỗi → 503. Client Redis tạo lười, không ping lúc import nên app khởi động được khi Redis chưa có |
| Auth | `APIKeyHeader("X-API-Key")`, so sánh bằng `hmac.compare_digest` (tránh timing attack), thiếu/sai → 401 |
| Rate limit | Sliding window bằng Redis sorted set, chạy trong **một Lua script** (ZREMRANGEBYSCORE → ZCARD → ZADD → EXPIRE) để 2 worker không vượt giới hạn cùng lúc; key là hash SHA-256 của API key; trả 429 + `Retry-After` |
| Cost guard | Đếm chi phí theo ngày và tháng trong Redis (`INCRBYFLOAT`), kiểm tra trước khi gọi LLM → 402 |
| Log JSON | `JsonFormatter` tự viết, mỗi request một dòng `{"ts","lvl","event":"request","method","path","status","ms","request_id"}` |
| Graceful shutdown | Dùng `lifespan`; không tự đăng ký handler SIGTERM, để uvicorn tự ngừng nhận kết nối, chờ request đang chạy rồi thoát 0. LLM chạy trong threadpool để không chặn event loop |
| Docker | 2 stage (`python:3.11-slim`): builder cài vào `/opt/venv`, runtime chỉ copy venv + `app/` + `utils/`, user `app` non-root, `HEALTHCHECK` bằng Python urllib, `CMD ["sh","-c","exec uvicorn ... --port ${PORT:-8000}"]` để uvicorn là PID 1 |
| Compose | `agent` build từ Dockerfile, `REDIS_URL=redis://redis:6379/0`, `depends_on: redis (service_healthy)`, `.env` với `required: false`; `redis:7-alpine` có healthcheck + volume AOF |

---

## AI log

Mình dùng Claude Code (trợ lý AI) trong bài này:

- **Setup:** cài WSL2 Ubuntu 22.04 (bản Ubuntu mới nhất không chạy được với WSL 2.4.12 trên máy), Python 3.11, bật Docker WSL integration.
- **Part 6:** AI viết các phần TODO trong `06-lab-complete/` (config, auth, Redis rate limiter bằng Lua script, cost guard, log JSON, lifespan, Dockerfile multi-stage, compose, deploy config). Mình chạy `check_production_ready.py` bản đầy đủ để xác nhận.
- **Part 1–5, 7:** AI chạy các lệnh trong đề và ghi lại output thật; số liệu trong file này và `BENCHMARK_REPORT.md` lấy từ output/JSON/CSV đó, không ước lượng.
- **Phần mình tự làm:** đăng nhập và deploy lên cloud, đặt secret trên nền tảng, kiểm tra lại các câu trả lời.
