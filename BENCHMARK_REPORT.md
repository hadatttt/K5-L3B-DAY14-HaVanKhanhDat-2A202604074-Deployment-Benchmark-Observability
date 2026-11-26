# Benchmark & Observability Report — Day 14

**Họ tên:** Hà Văn Khánh Đạt
**Ngày chạy:** 2026-11-26
**Môi trường:** Laptop Intel Core i7-12700H, 16 GB RAM, Windows 11 + WSL2 Ubuntu 22.04 (Python 3.11.18), Docker Desktop 29.9.3 (20 CPU / 7.6 GB cho Docker). Mock LLM, không gọi LLM thật.

Số liệu lấy từ: `reports/*.json` (develop), `benchmark-results/scale_*_stats.csv` (Locust), `screenshots/`.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Mock LLM mất ~150–220 ms mỗi call; 500 ms đủ chừa chỗ cho retrieval + mạng, nhưng vẫn bắt được khi request chậm (1.5 s) chiếm ≥ 5% traffic. Đây cũng là ngưỡng mặc định của `load_test.py` |
| Error rate `/ask` | < 2 % | Mock cố tình lỗi upstream ~1%; ngưỡng 2% cho phép mức nền đó nhưng báo động khi lỗi tăng gấp đôi |
| Accuracy trên golden dataset | ≥ 80 % (gate khi merge), mục tiêu 100% sau khi sửa KB | 80% là quality gate mặc định; sau khi sửa KB, mình nâng `--min-accuracy 1.0` để không chấp nhận regression nào |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2, 300 request mỗi mức)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.1 | 191.7 | 224.3 | 1706.8 | 1.33% | ✅ PASS |
| 10 | 33.89 | 192.4 | 298.3 | 1701.1 | 0.67% | ✅ PASS |
| 50 | 105.03 | 196.7 | 246.3 | 1703.0 | 1.00% | ✅ PASS |
| 100 | 67.14 | 358.6 | 2450.0 | 2756.5 | 0.33% | ❌ FAIL (p95) |

(file: `reports/load_v2_c1.json`, `load_v2_c10.json`, `load_v2_c50.json`, `load_v2_c100.json`)

**Nhận xét:** RPS tăng gần tuyến tính từ 1 → 10 (×8.3) vì app là async: lúc chờ LLM, event loop phục vụ request khác, p50 gần như không đổi (~192 ms). Từ 10 → 50 chỉ tăng ×3.1 và ở 100 thì RPS **giảm** (67 req/s) còn p95 vọt lên 2450 ms. Lý do: agent chỉ chạy **một process, một event loop**; khi có 100 kết nối cùng lúc, phần CPU (parse JSON, tính metric, log, tokenizer giả lập) cộng với overhead của chính client load test trên cùng máy làm request phải xếp hàng → latency tăng, throughput bão hoà rồi giảm. Ngưỡng an toàn của 1 instance ở máy này là khoảng 50 concurrent; muốn hơn phải scale ngang.

### 2.2 Tail latency (concurrency 20, 300 request)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 204.6 | 344.3 | 385.9 |
| 0.03 (mặc định) | 218.2 | 221.3 | 1710.4 |
| 0.1 | 329.4 | 1688.4 | 1715.1 |

(file: `reports/load_v2_slow_0.json`, `load_v2_slow_0.03.json`, `load_v2_slow_0.1.json`)

**Nhận xét:** Chỉ số nhạy nhất là **p99** (386 → 1710 ms ngay khi chỉ 3% request chậm) và **p95** (nhảy lên 1688 ms khi 10% chậm, vì lúc đó request chậm chiếm hơn 5% phân phối). Average chỉ tăng từ 205 lên 329 ms — nhìn average thì tưởng "chậm hơn một chút", trong khi thực tế cứ 10 người dùng có 1 người chờ 1.7 s. SLO đặt theo average sẽ che mất trải nghiệm tệ của nhóm người dùng ở đuôi phân phối, nên SLO phải đặt theo p95/p99.
(Lưu ý: p95 ở `MOCK_SLOW_RATE=0` cao hơn bản 0.03 vì nhiễu jitter trên mẫu 300 request; p99 mới là chỉ số phản ánh rõ request chậm.)

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.2 | 109.0 | 117.3 |
| Tổng cost (USD) | 0.000406 | 0.000759 | 0.000822 |
| Cost / câu đúng (USD) | 0.00040575 | 0.00003616 | 0.00003576 |
| Latency p95 (ms) | 191.0 | 225.5 | 222.2 |
| Quality gate | ❌ FAIL (accuracy < 80%) | ✅ PASS (≥ 80%, 0 regression so với v1) | ✅ PASS (≥ 100%, 0 regression so với v2) |

(file: `reports/eval_v1.json`, `eval_v2.json`, `eval_v2_fixed.json`)

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` "JWT khác gì API key trong xác thực?" | `token`, `hết hạn`, `chữ ký` | Không có tài liệu nào khớp nên agent trả câu chung chung. Thêm entry vào `KNOWLEDGE_BASE` với từ khoá `jwt`, `api key`, `xác thực`, `authentication`: JWT là token tự chứa claims kèm chữ ký số, có thời điểm hết hạn (`exp`); API key là chuỗi cố định, thường không hết hạn |
| `scaling-03` "Kubernetes HPA scale dựa trên những chỉ số nào?" | `cpu`, `memory`, `custom metrics` | Thêm entry với từ khoá `hpa`, `kubernetes`, `autoscal`, `horizontal pod`: HPA scale theo CPU, memory hoặc custom metrics (req/s, queue length qua Prometheus Adapter) |

Sau khi sửa (`develop/utils/mock_llm.py`, đã chép sang `production/utils/mock_llm.py`), chạy lại:
`python eval/run_eval.py --url http://localhost:8002 --min-accuracy 1.0 --baseline reports/eval_v2.json --out reports/eval_v2_fixed.json` → **2 câu cải thiện, 0 regression, Quality gate ✅ PASS**, exit code 0.

**Quality gate trong CI (Exercise 7.3 câu 4):** chạy eval cho v1 với `--baseline reports/eval_v2.json` → accuracy 4.3%, **20 câu regression**, `Quality gate ❌ FAIL`, **exit code = 1**. Job [`.github/workflows/eval-quality-gate.yml`](.github/workflows/eval-quality-gate.yml) chạy đúng lệnh này trên mỗi pull request (baseline `eval_v2_fixed.json`, `--min-accuracy 1.0`). Exit code ≠ 0 làm step và job fail; bật branch protection "Require status checks to pass" cho job `eval` thì PR không merge được.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:** v2 có bước retrieval nên prompt dài gấp đôi (109 so với 57 token/câu), tổng cost cao hơn ~1.9 lần và p95 chậm hơn ~35 ms. Nhưng v2 đúng 21/23 so với 1/23, nên **cost trên mỗi câu đúng rẻ hơn ~11 lần** (0.000036 so với 0.000406 USD). Sửa KB thêm 8 token/câu nhưng cost/câu đúng còn giảm nhẹ. So sánh theo "cost / câu" sẽ chọn nhầm v1; "cost / câu đúng" mới phản ánh giá trị thật.

---

## 4. Observability stack (production)

### 4.1 Screenshot

SECTION4_PLACEHOLDER

---

## 5. Benchmark scaling (production, Locust headless, 100 users, ramp 10/s, 2 phút)

Số instance được xác nhận bằng `sum(up{job="agent"})` trong Prometheus trước và sau mỗi lần chạy (1 và 3).

| Số instance | RPS (`/ask`) | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 59.91 | 190 | 250 | 1700 | 78 / 7162 (1.09%, tất cả 503 từ mock LLM) |
| 3 | 59.71 | 190 | 230 | 1700 | 69 / 7113 (0.97%, tất cả 503 từ mock LLM) |

(file: `benchmark-results/scale_1_stats.csv`, `scale_3_stats.csv`; hàng `POST /ask`)

**Giải thích kết quả:** Scale từ 1 lên 3 instance gần như **không đổi** RPS (~60 req/s) và p95 chỉ giảm 250 → 230 ms; p99 giữ nguyên 1700 ms.

- RPS do **phía tải** quyết định: 100 user của Locust mỗi người có thời gian nghỉ giữa các request, nên tổng tải chỉ ~60 req/s. Một instance async đã xử lý được mức này (bước 2.1 đo được ~105 req/s ở concurrency 50), nên thêm instance không có thêm việc để làm.
- Latency do **mock LLM** quyết định: ~190 ms mỗi call cộng 3% request chậm 1.5 s (`MOCK_SLOW_RATE`). Đó là latency của upstream, không phải do agent thiếu CPU, nên p99 = 1700 ms ở cả hai cấu hình. Panel "LLM latency p95" trong Grafana xác nhận nút thắt nằm ở LLM.
- 503 là lỗi upstream giả lập (~1%), cũng không giảm khi scale.

Kết luận: scale ngang chỉ có ích khi instance bị bão hoà (CPU, event loop, in-flight cao). Với agent gọi LLM, muốn giảm tail latency phải xử lý ở tầng LLM: timeout + retry/hedging cho request chậm, cache câu trả lời, model nhanh hơn.

**Lỗi gặp phải khi đo (đã sửa):**
1. Image agent của stack bị lỗi `ModuleNotFoundError: No module named 'uvicorn'`: Dockerfile cài thư viện bằng `pip install --user` rồi copy sang `/home/agent/.local`, nhưng user `agent` có home là `/app` nên Python tìm ở `/app/.local`. Sửa bằng `ENV PYTHONUSERBASE=/home/agent/.local` trong `production/Dockerfile`.
2. Lần đo đầu, `docker compose run locust` tự khởi động lại agent theo `deploy.replicas: 2`, nên cả "1 instance" và "3 instance" thật ra đều chạy 2 instance (thấy được qua Prometheus). Đo lại với `docker compose run --no-deps locust`.

---

## 6. Kết luận

- 3 điều mình học được về benchmark & observability:
  1. **Trung bình nói dối.** Chỉ 3% request chậm đã đẩy p99 từ 386 lên 1710 ms trong khi average chỉ tăng ~14 ms. SLO và alert phải đặt theo percentile.
  2. **Benchmark phải kiểm tra chính nó.** Lần đo scaling đầu tiên cho số "đẹp" nhưng sai vì `compose run` âm thầm đổi số replica; nếu không đối chiếu `up{job="agent"}` thì đã kết luận sai. Ngoài ra RPS ở bước 5 bị giới hạn bởi tải của Locust chứ không phải agent.
  3. **Metric hạ tầng không thấy lỗi chất lượng.** Chuyển sang v1 thì accuracy rơi từ 91% xuống 4% mà không alert nào kêu; chỉ eval trên golden dataset (và quality gate trong CI) mới bắt được. Metric chỉ phản ánh những gì service đó thấy (504 ở Nginx không có trong metric của agent).
- Nếu đưa agent này lên production thật, mình sẽ thêm:
  - Alert **burn rate theo SLO** (multi-window 5m/1h) thay vì ngưỡng cứng, để không báo động vì một đợt nhiễu ngắn.
  - Metric và alert ở **tầng Nginx/LB** (tỉ lệ 5xx, 504, upstream response time) và **synthetic check** từ bên ngoài gọi `/ask` mỗi phút.
  - **Online eval**: lấy mẫu vài % câu trả lời thật để chấm (LLM-as-judge hoặc feedback người dùng), xuất metric `answer_quality_score` và alert khi giảm; kèm metric `retrieval_hit_ratio` có alert.
  - Alert **cost theo ngày/user** (gần chạm `DAILY_BUDGET_USD`), và alert khi tỉ lệ 402/429 tăng đột biến.
  - Metric saturation: event-loop lag, CPU/memory container, độ dài hàng đợi.
