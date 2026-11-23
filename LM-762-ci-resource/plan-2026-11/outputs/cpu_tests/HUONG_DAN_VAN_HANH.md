# Hướng dẫn vận hành: Bản đồ PR → CI của LMCache

> Đọc trong khoảng 15 phút. Sau khi đọc, bạn sẽ: (1) hiểu trang báo cáo trả lời câu hỏi gì, (2) biết dữ liệu đi từ đâu tới đâu, (3) tự refresh trang từ một CI run mới, (4) sửa hoặc thêm nội dung mà không làm hỏng trang.

Trang chính: [`../../06_PR_TO_CI_VISUAL.html`](../../06_PR_TO_CI_VISUAL.html). Mở trực tiếp bằng trình duyệt, không cần server.
Thư mục vận hành: `LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/` (thư mục chứa file này).

---

## 1. Dự án này để làm gì

LMCache muốn **merge PR nhanh hơn và tốn ít GPU hơn**. Muốn vậy cần hai thứ:

1. **Fail-fast:** ngắt sớm khi gặp lỗi. Test rẻ (CPU) chạy trước; nếu fail thì huỷ các job GPU đắt tiền.
2. **Test tiering:** chia test thành tầng (L0 → Full). Một PR chỉ chạy những tầng mà thay đổi của nó cần.

Không thiết kế được hai thứ này nếu chưa biết **mỗi test bảo vệ cái gì**. Trang báo cáo là bản đồ đó:

| View | Trả lời câu hỏi | Nguồn dữ liệu |
|---|---|---|
| **CPU** (mặc định) | ~9.3k test CPU kiểm tra feature nào, vì sao cần có, setup thế nào. Job nào thật sự chặn merge. Cái gì đang làm chậm hoặc gây test flake | Log pytest của GitHub Actions + source test, sinh tự động bằng script |
| **GPU** | GPU-phút của mỗi build PR đi đâu. Bậc thang fail-fast đề xuất. Loại thay đổi nào cần tầng nào | Phân tích P1–P8 (Buildkite, 30 ngày), viết tay trong HTML |

Bối cảnh: đây là đầu vào cho các task fail-fast (task C, task 1, task 4) và CPU logic test (task 2) trong `LM-1062-fast-fail/` (task C), `LM-1077-vllm-stable-pin/` (task A), `LM-781-vendor-pypi/` (task B) và kế hoạch `LM-762-ci-resource/plan-2026-11/`.

---

## 2. Hiểu CI của LMCache trong 5 phút

### 2.1 Job nào chặn cái gì

| Job | Chạy ở | Vai trò | Ghi chú |
|---|---|---|---|
| DCO, Check code quality | GitHub | **Chặn merge** | lint, ký commit |
| **k3-unit-tests** | Buildkite, 1 GPU | **Chặn merge** | toàn bộ `tests/`, gồm test cuda, `--maxfail=1`. Chờ GPU ~25 phút + chạy ~24 phút |
| **k3-multiprocess-test** | Buildkite, ~35 job, 0–4 GPU | **Chặn merge** | gồm `cpu_e2e_validation` (vLLM-CPU thật) và các workload GPU |
| **Test** (py3.10–3.14) | GitHub, CPU | **Tham khảo** (không chặn merge), nhưng **chặn release** | chính là nội dung view CPU. ≈19 phút × 5 phiên bản |
| CPU device (`cpu_device.yml`) | GitHub, CPU | Tham khảo | cùng script E2E với `cpu_e2e_validation`, thêm macOS / MLA / gRPC |
| gRPC native, token-drop, raw-block, Rust, HF3FS | GitHub, CPU | Tham khảo | job nhỏ, chạy theo path thay đổi |

**Hai phát hiện quan trọng nhất** (đo từng test, cùng commit, `k3_overlap.py`):
- 8,994 test pass trên **cả hai** runner (87.7% của k3). Job CPU xong sớm hơn ≈30 phút, nên nó là **tín hiệu fail-fast miễn phí**: CPU fail thì huỷ build GPU đang chờ.
- **327 unit test vLLM connector / lazy offload chỉ chạy ở GHA Test (tham khảo).** k3 không cài vLLM nên skip chúng, vì vậy **không điều kiện chặn merge nào bao phủ chúng**.

### 2.2 Thuật ngữ dùng trên trang

| Thuật ngữ | Nghĩa |
|---|---|
| Required / chặn merge | Check nằm trong branch protection; fail thì không merge được |
| Advisory / tham khảo | Fail nhưng PR vẫn merge được |
| Gates release / chặn release | `publish.yml` cần job này pass mới publish PyPI / Docker |
| Deselected / bị lọc bỏ | Test không khớp `-m "not (cuda or …)"`, pytest không chạy |
| Module-level skip / skip cả module | `pytest.skip(..., allow_module_level=True)` lúc collection, ví dụ khi không có GPU |
| Itemized skip / skip từng ca | Một hàm test bị skip lúc chạy |
| Test flake | Test lúc pass lúc fail mà code không đổi (port, timeout, mạng) |
| Quarantine / cách ly test | Đưa test flake ra khỏi đường chặn chính |
| CPU-portable / chạy được trên CPU | File test đang bị skip chỉ vì guard thiết bị, thân test không dùng tensor GPU, nên có thể chuyển sang CPU |
| L0 … Full | Các tầng test, từ rẻ (lint) tới đắt (full GPU, nightly). Xem GPU view mục 4 |

### 2.3 Bản đồ tư duy LMCache cho người mới (Mental Model trong 2 phút)

Người mới tiếp cận codebase LMCache chỉ cần nhớ 4 khối tư duy cốt lõi sau:

#### 1. LMCache là gì?
> **LMCache là "CDN / Redis" cho bộ nhớ đệm KV của LLM.**
- Khi có một prompt dài (ví dụ tài liệu RAG 10,000 từ hay codebase), GPU thông thường phải mất vài giây tính toán lại từ đầu (Prefill Phase) để sinh ra **KV Cache (Key-Value tensors)**.
- LMCache lưu sẵn các KV tensor này vào RAM máy chủ (L1) hoặc ổ đĩa/cloud (L2). Khi có request tương tự, LMCache nạp thẳng KV vào VRAM GPU, giảm mạnh thời gian tới token đầu tiên (**TTFT - Time-to-First-Token**). Ví dụ trong CI: workload `long_doc_qa` yêu cầu TTFT khi có cache nhanh hơn ≥ 60% (vLLM).

#### 2. Vòng đời xử lý một Prompt (The Prompt Lifecycle)
1. **Lookup (Tra cứu):** Cắt prompt thành các **Chunk** (thường 256 tokens) $\rightarrow$ băm cuộn (rolling hash, ví dụ blake3) thành **Cache Key** — key của chunk sau phụ thuộc chunk trước $\rightarrow$ hỏi kho xem chunk nào đã có.
2. **Hit / Miss (Trúng / Trượt):**
   - **Hit:** Gọi **Retrieve** để bắn KV tensor từ cache nạp thẳng vào VRAM GPU. Bỏ qua việc tính toán!
   - **Miss:** GPU tự tính toán bình thường.
3. **Store (Lưu đệm):** Sau khi tính xong, worker gọi lệnh Store đẩy KV tensor mới vào LMCache để lần sau dùng lại.
4. **Prefetch (Nạp trước):** Kéo trước các chunk KV tiềm năng từ đĩa/mạng lên RAM host để khi GPU cần là có ngay.
5. **Eviction (Dọn dẹp):** Khi bộ nhớ đầy, thuật toán LRU/ARC tự xóa các chunk cũ, ít dùng để giải phóng chỗ.

#### 3. Các tầng lưu trữ (Storage Hierarchy)
- **L1 (Host DRAM):** Tầng nhớ nóng siêu tốc nằm trên RAM CPU của máy chủ (nhanh nhất, nằm ngay trên máy).
- **L2 (Persistent Storage):** Tầng bền vững lưu trên NVMe SSD cục bộ, S3, MinIO, Redis/Valkey (chia sẻ giữa nhiều máy chủ).
- **P2P Transfer:** Các GPU node tự truyền trực tiếp KV cache cho nhau qua mạng, không làm nghẽn máy chủ trung tâm.
- **GDS (GPU Direct Storage):** Nối thẳng dữ liệu từ ổ cứng NVMe vào VRAM GPU qua đường DMA, bỏ qua nghẽn CPU.

#### 4. Thuật ngữ kiến trúc quan trọng trong Codebase
- **CacheBlend:** Thay vì chỉ cache đoạn đầu câu (prefix), CacheBlend cho phép ghép nối và tái sử dụng các đoạn tài liệu nằm ở **bất kỳ đâu trong prompt** bằng cách tính toán lại góc quay RoPE.
- **Lazy Offload:** Store muộn — KV không được lưu ngay mà thành ứng viên chờ; policy quyết định lưu khi block GPU sắp bị vLLM tái sử dụng (evict). Token dropping là phần cấp phát KV khi engine bỏ bớt token.
- **MLA (Multi-head Latent Attention):** Định dạng nén KV đặc thù của DeepSeek V2/V3 — yêu cầu LMCache có bộ layout adapter riêng biệt.
- **Serde (Serialization / Deserialization):** Lượng tử hoá KV (FP8, K16/V8, TurboQuant) và mã hoá AES-GCM trước khi ghi xuống L2.
- **Hai đường truyền KV:** *LMCache-driven* (mặc định trên CUDA/NPU) — server đọc thẳng bộ nhớ GPU qua IPC/SHM handle, zero-copy; *engine-driven* (thiết bị khác) — worker gather/scatter một bản copy qua shm hoặc inline (`transfer_mode.py`).

### 2.4 Bản đồ 28 Phân khu Tính năng (28 Feature Areas Map)

Mỗi phân khu trả lời rõ 4 câu hỏi: **Làm gì (What)** → **Vì sao cần (Why)** → **Code chính ở đâu** → **File test ở đâu**:

| Mã & Phân khu | Làm gì (What) | Vì sao cần (Why) | Code chính | File test chính |
|---|---|---|---|---|
| **1. Engine Integration** | | | | |
| `1.1 vllm` (vLLM MP connector) | Cầu nối scheduler lookup, worker store/retrieve, hybrid/Mamba/MLA groups, LoRA/MM keys, preemption | vLLM đổi API liên tục; sai key/slot gây nạp nhầm KV âm thầm mà không crash | `lmcache/integration/vllm/`, `lmcache/v1/multiprocess/` | `tests/v1/multiprocess/test_vllm_*.py`, `tests/integration/vllm/` |
| `1.2 engines` (SGLang / TRT-LLM / ATOM) | Adapter chuẩn hoá nối LMCache vào SGLang, TensorRT-LLM, AMD ATOM | TRT-LLM & ATOM không có GPU runner riêng trên PR CI, đây là chốt chặn duy nhất | `lmcache/integration/sglang/`, `tensorrt/`, `atom/` | `tests/integration/sglang/`, `tests/v1/test_*_adapter.py` |
| `1.3 lazy` (Lazy offload & token drop) | Xả đệm lười khi block GPU sắp bị evict (FIFO/eviction-aware) & bỏ token dư | Quyết định *khi nào* lưu KV; lỗi sẽ làm mất KV hoặc ghi đè block vLLM đã tái sử dụng | `lmcache/integration/vllm/lazy_offload*.py` | `tests/v1/test_lazy_offload*.py`, `tests/v1/test_token_drop*.py` |
| `1.4 blend` (CacheBlend) | Tái sử dụng KV ở giữa prompt (non-prefix) bằng fingerprint matching & tính lại RoPE | Sai góc quay RoPE hoặc vị trí token sẽ sinh câu trả lời sai mà không báo lỗi | `lmcache/v1/multiprocess/modules/blend/` | `tests/v1/multiprocess/test_blend*.py` |
| **2. MP Server (Multiprocess Mode)** | | | | |
| `2.1 lifecycle` (MP server lifecycle) | Tự bật daemon từ engine, health check, SIGTERM cleanup, nhịp tim worker | Server không bật/tắt hoặc không phát hiện worker chết sẽ làm treo toàn bộ request | `lmcache/v1/multiprocess/server.py`, `heartbeat.py` | `tests/v1/multiprocess/test_server*.py`, `test_worker_liveness.py` |
| `2.2 transport` (IPC & RPC transport) | Kênh điều khiển ZMQ & gRPC (aio + native), futures, session, wire format | Mọi lệnh lookup/store/retrieve đều đi qua đây; lệch wire format là gãy kết nối | `lmcache/v1/multiprocess/transport/`, `rpc.py` | `tests/v1/multiprocess/test_zmq*.py`, `test_grpc*.py` |
| `2.3 modules` (Server modules & plugins) | Cơ chế nạp động module, extension hooks, plugin lưu trữ ngoài | Bảo vệ tương thích cho code mở rộng out-of-tree của bên thứ ba | `lmcache/v1/multiprocess/modules/`, `plugin/` | `tests/v1/multiprocess/test_module*.py`, `examples/lmc_external_l2_adapter/` |
| `2.4 datapath` (KV data path) | Đường truyền byte KV: zero-copy IPC/POSIX Shm hoặc inline copy, checksum | Nơi dễ xảy ra hỏng dữ liệu âm thầm (sai offset, giải phóng buffer quá sớm) | `lmcache/v1/multiprocess/transfer_context/`, `posix_shm.py` | `tests/v1/multiprocess/test_*transfer*.py`, `test_posix_shm.py` |
| `2.5 lookup` (Lookup, hashing & prefetch) | Băm cuộn token thành chunk key, kiểm tra hit, chính sách prefetch vào RAM | Quyết định hit-rate; đổi thuật toán hash làm vô hiệu hoá toàn bộ cache cũ | `lmcache/v1/multiprocess/lookup*.py`, `token_hasher.py` | `tests/v1/multiprocess/test_lookup*.py`, `test_prefetch*.py` |
| `2.6 http` (MP HTTP APIs & auth) | REST `/cache`, `/config`, `/info`, reload cấu hình nóng, quota, xác thực Bearer/API key | Cổng vận hành của operator & coordinator; kiểm soát an toàn bảo mật | `lmcache/v1/multiprocess/http_apis/` | `tests/v1/multiprocess/test_http*.py`, `test_auth*.py` |
| **3. Storage: L1 / L2 / Serde** | | | | |
| `3.1 l1` (L1 memory & eviction) | Cấp phát DRAM host / Device-DAX, quản lý địa chỉ, mlock, thu hồi LRU/ARC | L1 là cache nóng nhất; rò rỉ bộ nhớ hoặc double-free làm sập server ngay khi tải cao | `lmcache/v1/distributed/l1_*.py`, `eviction*.py` | `tests/v1/distributed/test_l1_*.py`, `test_eviction*.py` |
| `3.2 smcore` (Storage manager core) | Quản lý danh bạ object key, bitmap đánh dấu prefix-hit, quota, điều phối các tầng | Bộ não dùng chung cho mọi tầng lưu trữ; phải tương thích ngược với dữ liệu đã lưu | `lmcache/v1/distributed/storage_manager.py`, `bitmap_ops.py` | `tests/v1/distributed/test_storage_manager*.py`, `test_bitmap*.py` |
| `3.3 l2` (L2 storage adapters) | Kết nối ổ NVMe FS (`O_DIRECT`), S3, Valkey/Redis, Bigtable, Mooncake, NIXL, HF3FS | Mỗi backend dùng SDK riêng; kiểm tra cấu hình, key layout và xử lý lỗi mạng/đĩa | `lmcache/v1/distributed/l2_adapters/` | `tests/v1/distributed/l2_adapters/test_*.py` |
| `3.4 serde` (Compression & encryption) | Lượng tử hoá FP8, K16/V8, TurboQuant và mã hoá AES-GCM trước khi xuống L2 | Sai serde làm hỏng KV sau khi đọc lại hoặc không đọc được dữ liệu khi nâng cấp | `lmcache/v1/distributed/serde/` | `tests/v1/distributed/serde/test_*.py` |
| `3.5 p2p` (P2P & transfer channel) | Truyền KV trực tiếp ngang hàng giữa các node GPU không qua kho trung tâm | Kiểm tra giao thức điều phối và state machine P2P trước khi chạy trên phần cứng GPU | `lmcache/v1/distributed/transfer_channel/` | `tests/v1/distributed/test_p2p*.py`, `test_transfer_channel*.py` |
| `3.6 gds` (GPU Direct Storage) | Đọc/ghi DMA trực tiếp giữa NVMe và VRAM GPU (cuFile, hipFile, muFile, uGDS) | Kiểm tra hợp đồng gọi thư viện native của từng hãng và cơ chế fallback | `lmcache/v1/gpu_connector/gds_backends/` | `tests/v1/gpu_connector/test_gds*.py` |
| `3.7 orch` (Memory orchestrator) | Máy trạng thái phân vùng nhớ dùng chung giữa nhiều tiến trình worker | Tránh rò rỉ hoặc cấp phát trùng vùng nhớ giữa các tiến trình song song | `lmcache/v1/memory_orchestrator/` | `tests/v1/memory_orchestrator/test_*.py` |
| **4. KV Layout & Devices** | | | | |
| `4.1 layout` (KV layout & format) | Nhận diện cấu trúc tensor KV (DeepSeek MLA, Mamba, MHA) và bảng chuẩn golden | Sai 1 stride là nạp rác vào GPU; golden test buộc mọi thay đổi layout phải tường minh | `lmcache/v1/gpu_connector/kv_format/` | `tests/v1/gpu_connector/test_kv_format*.py` |
| `4.2 platform` (Device platforms) | Lớp trừu tượng phần cứng cho CUDA, ROCm, XPU, MUSA, NPU, MLU, Neuron, RBLN | Đa số hãng phần cứng không có runner trên PR CI; giữ hợp đồng API trên CPU | `lmcache/v1/platform/` | `tests/v1/platform/test_*.py` |
| `4.3 native` (Native C++ core) | Hàm mở rộng C++ cho bitmap, pattern matcher, TTL lock, bloom filter, copy | Khối nền tảng cấp thấp dùng khắp nơi; lỗi ở đây gây sập ngẫu nhiên ở tầng trên | `csrc/`, `lmcache/v1/utils/` | `tests/native/`, `tests/v1/test_utils*.py` |
| **5. Control Plane & Observability** | | | | |
| `5.1 coord` (MP coordinator) | Tổng chỉ huy toàn cụm: danh bạ node giữ chunk nào, ingest sự kiện, quota, warm prefetch | Sai trạng thái cụm sẽ điều hướng sai node và xoá nhầm cache toàn hệ thống | `lmcache/v1/mp_coordinator/` | `tests/v1/mp_coordinator/test_*.py` |
| `5.2 obs` (Observability) | Event bus xuất chỉ số hit-rate, độ trễ, dung lượng ra Prometheus / OpenTelemetry | Giúp người vận hành thấy hiệu quả cache; đảm bảo subscriber không làm chậm đường nóng | `lmcache/v1/mp_observability/` | `tests/v1/mp_observability/test_*.py` |
| **6. Legacy In-Process Mode (v1)** | | | | |
| `6.1 ip_engine` · `6.2 ip_store` · `6.3 ip_ctrl` | Kiến trúc đơn tiến trình đời đầu (chạy trong worker vLLM): engine, storage, controller | Vẫn đang phát hành; chống hồi quy các lỗi cũ (#3337, #3318) | `lmcache/inprocess/` | `tests/inprocess/`, `tests/v1/cache_controller/` |
| **7. Tooling & Repo Governance** | | | | |
| `7.1 cli` · `7.2 frontend` · `7.3 build` · `7.4 other` | Công cụ `lmcache` CLI (`bench`, `query`, `server`), SDK client, kiểm tra đóng gói & lint | Đảm bảo giao diện người dùng, công cụ đo kiểm CI và quy chuẩn đóng gói không lệch | `lmcache/cli/`, `lmcache/sdk/`, `tools/` | `tests/cli/`, `tests/sdk/`, `tests/test_check_*.py` |

### 2.5 Sổ tay Xử lý Sự cố & Debug Test Local (Troubleshooting Runbook)

Hướng dẫn kỹ sư mới chạy và debug test ngay trên máy cá nhân **không có GPU**:

```bash
# 1. Chạy toàn bộ test CPU nhanh (bỏ qua CUDA và các thiết bị tăng tốc):
pytest -m "not (cuda or musa or xpu or npu or neuron or rbln)" tests/

# 2. Chạy riêng một phân khu tính năng (ví dụ CacheBlend hoặc Lazy Offload):
pytest tests/v1/multiprocess/test_blend.py
pytest tests/v1/test_lazy_offload.py

# 3. Chạy nhanh với cờ dừng ngay ở lỗi đầu tiên và hiện 10 test chậm nhất:
pytest -m "not (cuda or musa or xpu or npu or neuron or rbln)" --maxfail=1 --durations=10 tests/

# 4. Các lỗi thường gặp trên máy local & cách xử lý:
# - Test socket port hang / ZMQError (Address already in use):
#   Kiểm tra tiến trình pytest/lmcache cũ còn treo chiếm port ZMQ/gRPC hay không (ps aux | grep pytest).
# - ModuleNotFoundError: No module named 'vllm':
#   Cài đặt vLLM wheel kết hợp NO_GPU_EXT=1 pip install -e . theo đúng cấu hình GHA test.yml.
# - Lỗi mạng 401 ở test_create_workload.py:
#   Test gọi trực tiếp huggingface.co; chạy thêm -k "not test_create_workload" khi offline.
```

---

## 3. Kiến trúc end-to-end

```
 NGUỒN DỮ LIỆU                          SCRIPT (outputs/cpu_tests/)                 KẾT QUẢ
 ─────────────                          ───────────────────────────                 ───────
 GHA log job "test: 3.12" ──┐
   (job312.log)             ├──► parse.py ──► cpu_tests.json ─┐
 Source test của cùng commit┘     (pass/skip/time, test,      │
   (src/tests, src/examples)       docstring, setup tags)     │
                                                              ▼
 areas.py      (path → nhóm feature) ─────────────────► build_page.py ──► view CPU (mục 1–9)
 area_meta.py  (what / why / setup / code) ────────────►   │  dùng section9_html.py (template,
 section9_html.py (HTML, CSS, finding cards, timeline) ►   │  thẻ phát hiện, số Buildkite)
                                                           ├─► build_nav.py  ──► công tắc CPU/GPU + 5 tab
                                                           └─► build_i18n.py ──► công tắc EN/VI (i18n_vi.py)
 P1–P8 (Plan/2026-11/outputs/P*) ──► viết tay trong HTML; fix_gpu.py đã áp bản sửa ──► view GPU (mục 1–9)

 verify_page.py ──► Chrome headless: lỗi JS, tab, widget, chữ chưa dịch, screenshot
```

### 3.1 Từng file làm gì

| File | Vai trò | Khi nào sửa |
|---|---|---|
| `parse.py` | Đọc log + source, tạo `cpu_tests.json` | Khi định dạng log pytest đổi |
| `areas.py` | Luật regex path → nhóm feature + `OVERRIDES` | Khi có file test mới bị xếp sai nhóm |
| `area_meta.py` | Mô tả 28 nhóm: what / why / setup / main code; nhóm lớn (`GROUPS`) | Khi feature đổi hoặc mô tả sai |
| `lmcache_glossary.py` | Từ điển định nghĩa kỹ thuật song ngữ (`AREA_ROLE` + `CONCEPTS`) cho cột "Ý nghĩa trong LMCache" | Khi thêm khái niệm kiến trúc hoặc tinh chỉnh giải thích cho newbie |
| `gates.py` / `build_gates.py` | Nguồn sự thật duy nhất cho cổng kiểm thử, bậc thang L0→Full, ma trận tác động (`#gates/...`) | Khi đổi job chặn merge, định nghĩa tầng hoặc workload |
| `build_observe.py` | Giao diện Giám sát & Báo cáo (`#obs/...`): 4 Hero KPI Cards (The Vital Four), Radial Donut Gauges, Area Sparklines, bảng biến động 3 cột, khối thu gọn 16 metric chi tiết | Khi đổi ngưỡng cảnh báo, KPI mũi nhọn hoặc bố cục báo cáo |
| `sync_incremental.py` | Đồng bộ vi sai (< 15 giây) dùng mốc `made`, tự động cắt tỉa cửa sổ trượt 90 ngày (Sliding Window Auto-Prune) để giữ HTML cố định ~1.6 MB | Chạy định kỳ hoặc qua GitHub Actions cron |
| `section9_html.py` | Template view CPU, CSS, `FINDINGS` (thẻ phát hiện), JS timeline | Khi đổi bố cục, số Buildkite, phát hiện |
| `build_page.py` | Ghép tất cả, tính tổng, chèn vào trang, rồi gọi `build_nav` + `build_i18n` | Hiếm khi |
| `build_nav.py` | Công tắc CPU/GPU, 5 tab, link sâu `#cpu/explore` | Khi thêm tab |
| `i18n_vi.py` | Từ điển EN → VI + luật regex cho chuỗi có số | **Mỗi khi thêm hoặc đổi chữ tiếng Anh** |
| `build_i18n.py` | Bộ máy dịch, nút EN/VI, phím `L` | Hiếm khi |
| `fix_gpu.py` | Bản sửa một lần cho view GPU (theo review). Chạy lại an toàn | Không cần chạy lại |
| `verify_page.py` | Kiểm tra trang trước khi chia sẻ | Chạy sau mỗi lần build |
| `k3_overlap.py` | Tải log k3 (Buildkite REST, token đọc lúc chạy) rồi so từng test với `job312.log` | Khi refresh: sửa build/job ID ở đầu file, cập nhật số trong `section9_html.py` (thanh overlap + 2 thẻ đầu) |
| `cpu_tests.json`, `job312.log`, `src/` | Dữ liệu của lần refresh hiện tại | Thay khi refresh |
| `REVIEW_ponytail.md` | Review độc lập, **nguồn đáng tin**. Các fix đã áp dụng | Đọc khi cần bằng chứng |
| `REVIEW.md` | Review của một agent khác; **có 4 chỗ sai đã biết** (vụ v0.5.7, "4 nhóm lỗi", số file xếp sai nhóm, 74 vs 68) | Không dùng làm nguồn |

### 3.2 Dữ liệu hiện tại (snapshot)

| Thứ | Giá trị |
|---|---|
| Commit | `05d8eb84` (PR #6367, 2026-11-06) |
| GHA run / job | `42189301949` / `127850987819` (`test: 3.12`) |
| Buildkite k3-unit-tests | build `#14829` (cùng commit) |
| Kết quả CPU | 9,326 pass · 402 skip từng ca · 47 skip cả module · 443 bị lọc bỏ · 540 file |
| Không chạy trên CPU | 68 file test (+6 file helper); 13 file chạy được trên CPU (≈9.7k dòng) |
| View GPU | Buildkite 30 ngày (2026-10-05 → 11-04), commit phân tích `fcd50cea` |

### 3.3 Ba tầng tài liệu test

| Tầng | Cho ai | Ở đâu trên trang | Nguồn | Cách cập nhật |
|---|---|---|---|---|
| **Vĩ mô** — 28 nhóm feature: what / why / setup / code | Tech lead | CPU mục 3 (click dòng) | `area_meta.py` | Sửa tay khi feature đổi |
| **Vi mô** — từng test | Dev tra cứu | CPU mục 9 (Explorer): docstring + cột "Ý nghĩa trong LMCache" | Docstring trong repo LMCache + `lmcache_glossary.py` (tự sinh) | Muốn hay hơn thì PR thêm docstring vào chính file test trong LMCache |
| **Trọng yếu** — 46 test chặn PR (L0 · L1G · CPU E2E + L1 chính + 5 test vLLM chưa được gate) | Fail-fast, merge gate | CPU mục 10, và ★ trong Explorer | `curated_tests.py` (viết tay, đọc từ source ở 05d8eb84) | Đọc lại test mỗi khi nó đổi; mỗi dòng có đủ EN + VI |

### 3.4 Ba view và nguồn sự thật duy nhất (từ 2026-11-07)

| View | Trả lời | Nguồn |
|---|---|---|
| **Cổng & tầng** (`#gates/…`) | PR phải qua gì: job chặn merge / release, bậc thang L0→Full, loại thay đổi → tầng, **tra cứu tác động** (nhóm feature → tầng → unit test → workload) | `gates.py` |
| **Unit test** (`#cpu/…`) | Test pytest nào bảo vệ cái gì (GHA CPU + k3 GPU pod) | log CI + `area_meta.py`, `curated_tests.py`, `lmcache_glossary.py` |
| **Workload E2E** (`#gpu/…`) | Pipeline MP: workload kiểm tra gì, cái gì chỉ nó bắt được, GPU tiêu vào đâu | `gates.py` (`WORKLOADS`) + P1/P2/P8 |
| **Theo dõi PR / Release** (`#obs/…`, phím `O`) | Trạng thái gần thời gian thực: release, hàng đợi PR, CI dev, hàng đợi CI. Xem mục 5.5 | GitHub + Buildkite API, `build_observe.py` (`CONFIG`) |

**Quy tắc:** muốn đổi job chặn merge, định nghĩa tầng, loại thay đổi hay ma trận workload → chỉ sửa `gates.py` rồi build. Không sửa trong HTML: staircase, bảng tầng, ma trận và mindmap đều đọc từ `gates.py`. Mô tả "Mục đích / điểm mấu chốt / Dữ liệu" của mọi mục cũng nằm trong `gates.py` (`DESC`, khoá theo view + số mục).

Chuỗi build (v2, 2026-11-13): `build_entities` → `build_nav` → `build_gates` → `build_onboarding` → `build_observe` → `build_ops_tabs` → `build_report1130` → `build_today` → `build_entity_ui` → `build_i18n`, rồi `verify_page.py`. Không chạy lẻ `build_observe`/`build_gates`: CSS của OPS và R1130 nằm lồng trong khối của chúng và sẽ mất cho tới khi chạy lại cả chuỗi (verify báo "CSS blocks missing").

---

## 4. Đọc trang thế nào

Ba view: **Cổng & tầng** (2 tab), **Unit test** và **Workload E2E** (cùng 5 tab). Mỗi view tự đánh số mục. Phím `T` / `U` / `E` đổi view.

| Bạn muốn biết | Mở |
|---|---|
| Job nào chặn merge / release | Cổng & tầng → mục 1 |
| Đổi code nhóm X thì phải chạy gì | Cổng & tầng → mục 5 (tra cứu tác động) |
| Feature X có test CPU không, test gì, vì sao, setup ra sao | CPU → Tầng & độ phủ → mục 3 (click dòng) |
| Nhóm nào dùng socket / subprocess (dễ flake) | CPU → mục 4 (setup matrix) |
| CPU E2E kiểm tra những bước nào | CPU → mục 5 |
| Test nào không chạy trên CPU, cái nào chuyển được | CPU → mục 6 (lọc "chỉ suite chạy được trên CPU") |
| Thời gian: CPU so với GPU unit pod, file nào chậm | CPU → Chi phí & thời gian (mục 7) |
| Việc nên làm cho fail-fast | CPU → Phát hiện (mục 8), rê chuột vào thẻ để xem bằng chứng |
| Tìm một test cụ thể | CPU → Khám phá (mục 9), tìm theo tên / docstring |
| Test nào quyết định PR được merge, fail thì xem đâu | CPU → Khám phá → mục 10 (lọc theo tầng) |
| GPU-phút đi đâu, lộ trình tiết kiệm | GPU → Tổng quan, Chi phí & thời gian |
| Thay đổi loại X cần chạy tầng nào | GPU → Tầng & độ phủ (mục 5) và Mindmap (mục 9) |

### 4.1 Từng mục của view CPU

Cùng nội dung với nút ⓘ cạnh tiêu đề mỗi mục trên trang.

| Mục | Mục đích | Điểm mấu chốt |
|---|---|---|
| 1 · Tổng quan số liệu | Bức tranh toàn cảnh: 9,326 test CPU trên GitHub Actions đặt cạnh 10,258 test trên GPU unit pod bắt buộc của Buildkite. | 540 file trong 28 nhóm feature. Job CPU xong ≈30 phút trước khi GPU pod bắt đầu: cơ hội fail-fast. |
| 2 · Điều kiện chặn merge & release | Job nào bắt buộc để merge vào dev, job nào chỉ chặn release. | GHA Test chặn release, không chặn merge. Job unit chặn merge là GPU pod; nó trùng 8,994 test (87.7%) với job CPU, còn 327 test vLLM connector chỉ chạy ở job CPU nên không điều kiện chặn merge nào bao phủ. |
| 3 · Ma trận feature | Mỗi nhóm trong 28 nhóm feature của LMCache được test trên CPU thế nào: số test pass, thời gian, số file. | Click một dòng để xem test kiểm tra gì, vì sao phải có, setup thế nào, code chính và danh sách file. |
| 4 · Ma trận setup | Các file test dựng môi trường thế nào: mock, asyncio, subprocess, socket ZMQ / gRPC thật. | Cột subprocess và socket là nơi sinh lỗi trùng port (Address already in use) và test flake do timeout. |
| 5 · CPU E2E: một script, hai runner | Bài kiểm thử end-to-end LMCache với engine vLLM thật, chạy hoàn toàn trên CPU. | Một script bash kiểm tra vòng đời KV cache (store → hit → reset → restart), chạy ở Buildkite (bắt buộc) và GHA (tham khảo, 7 leg). |
| 6 · Suite bị loại khỏi CPU | 68 file test không bao giờ chạy trong job CPU: do marker accelerator hoặc skip cả module (+6 file helper không có test). | 13 file (≈9.7k dòng, chủ yếu logic lưu trữ) chạy được trên CPU: chỉ bị loại vì guard thiết bị. |
| 7 · Thời gian: cùng unit test, hai runner | Đặt cạnh nhau job CPU của GitHub và GPU pod của Buildkite trên cùng commit, kèm các file chậm nhất. | Job CPU xong ở phút ≈18; GPU pod chờ tới phút 25 mới có GPU. Nếu job CPU fail, huỷ build GPU đang chờ. |
| 8 · Phát hiện về fail-fast | 10 phát hiện rút ra từ log CI, mỗi phát hiện có bằng chứng và cách sửa cụ thể (rê chuột vào thẻ). | Làm ngay: gate 327 test vLLM, bỏ hardcoded sleep 70 s, mock lệnh gọi Hugging Face, thêm --maxfail. |
| 9 · Khám phá test | Tra cứu từng hàm test trong 540 file. | Tìm theo tên và docstring, lọc theo nhóm feature, sắp xếp file chậm nhất để ưu tiên tối ưu. |

Phím tắt: `C` / `G` đổi view · `←` `→` đổi tab · `L` đổi EN/VI. "Hiện tất cả" hiện cả trang dài, tiện khi in.
Link sâu: `06_PR_TO_CI_VISUAL.html#cpu/findings`, `#gpu/explore`, …

---

## 5. Vận hành

> Mọi lệnh chạy trong **Git Bash**, tại thư mục `outputs/cpu_tests/`. Luôn chạy Python với `-I -X utf8`: `-I` cách ly môi trường, `-X utf8` để in được tiếng Việt và ký tự đặc biệt (`-I` bỏ qua `PYTHONIOENCODING`).

```bash
cd /c/Users/<user>/Desktop/Works/CacheAgent/LM-762-ci-resource/plan-2026-11/outputs/cpu_tests
REPO=/c/Users/<user>/Desktop/Works/CacheAgent/third_party/LMCache
```

### 5.1 Build lại trang (dữ liệu giữ nguyên)

Dùng khi bạn chỉ sửa text, mô tả, bản dịch, phát hiện…

```bash
python -I -X utf8 build_page.py      # tự chạy build_nav + build_i18n
python -I -X utf8 verify_page.py     # phải ra RESULT: PASS
```

### 5.2 Refresh từ một CI run mới

**Bước 1. Chọn một run `Test` đã pass và lấy job `test: 3.12`**

```bash
gh run list -R LMCache/LMCache -w test.yml -s success -L 5 --json databaseId,headSha,createdAt
RUN=<databaseId>
gh run view $RUN -R LMCache/LMCache --json headSha,jobs -q '.headSha, (.jobs[]|select(.name|test("3.12"))|.databaseId)'
SHA=<headSha>; JOB=<job id>
```

**Bước 2. Tải log (bỏ mã màu ANSI)**

```bash
gh api --allow-escape-sequences repos/LMCache/LMCache/actions/jobs/$JOB/logs | sed 's/\x1b\[[0-9;]*m//g' > job312.log
```

**Bước 3. Lấy source test của đúng commit đó (không checkout!)**

```bash
git -C "$REPO" fetch -q origin $SHA
rm -rf src && mkdir src
git -C "$REPO" archive $SHA tests examples | tar -x -C src
```

**Bước 4. Parse và build**

```bash
python -I -X utf8 parse.py           # in ra: files / pass / skip … — đối chiếu với dòng tổng kết pytest trong log
python -I -X utf8 build_page.py
```

Đối chiếu: `pass` của parse.py = passed + xpassed của pytest. `skip` + số skip cả module (dòng `collected … / N skipped` trong log) = skipped của pytest.

**Bước 5. Lấy số Buildkite k3-unit-tests cho cùng commit**

- Tìm build: Buildkite UI → pipeline `k3-unit-tests` → lọc theo commit. Hoặc dùng công cụ MCP `list_builds` (org `lmcache`, `commit=<SHA>`).
- Lấy: thời điểm job **created → started** (thời gian chờ GPU), **started → finished** (thời gian chạy), và dòng tổng kết pytest (`N passed … in X s`) qua `search_logs`.

**Bước 6. Cập nhật số ghi cứng** (chưa tự động hoá; xem mục 7)

| File | Chỗ cần sửa |
|---|---|
| `section9_html.py` | dòng nguồn ở mục 1 (run, build, commit); bảng mục 2 (10,258 / 25 phút / 24 phút / 3.6 phút / 9,326); mục 5 (1,034 run, 44/11/22); mục 7 (commit); `FINDINGS` (số trong thẻ); `JS_ADD` timeline (`5.6`, `18.1`, `24.9`, `48.8`) |
| `build_page.py` | tiles: `required GPU unit pod: 10,258`, `18 vs 49 min`, `≈95 min` |
| `build_nav.py` | nhãn công tắc `9,326 tests · 28 features`, `540 files`, phụ đề có commit |
| `i18n_vi.py` | **mọi câu tiếng Anh vừa sửa ở trên phải sửa khoá tương ứng**, nếu không bản VI sẽ hiện tiếng Anh |

Cách tìm nhanh: `grep -n "10,258\|9,326\|05d8eb84\|42189301949\|14829" *.py`

**Bước 7. Kiểm tra**

```bash
python -I -X utf8 build_page.py
python -I -X utf8 verify_page.py --shots ../../_shots    # PASS + ảnh chụp mọi tab, EN và VI
```

Mở vài ảnh trong `_shots/` để nhìn bằng mắt: số có hợp lý không, có chữ đè nhau không.

### 5.3 Sửa hoặc thêm nội dung

| Việc | Làm thế nào |
|---|---|
| File test bị xếp sai nhóm | Thêm vào `OVERRIDES` trong `areas.py` (path tính từ sau `tests/`) |
| Cột "Ý nghĩa trong LMCache" (mục 9) | Tự sinh từ `lmcache_glossary.py`: `AREA_ROLE` (vai trò của nhóm, EN/VI) + `CONCEPTS` (regex trên tên test + docstring, tối đa 3 khái niệm). Khớp ~68% số test. Khớp sai thì sửa regex; thêm khái niệm thì thêm dòng (có cả EN và VI) |
| Mã số feature (1.1, 2.3…) | Tự sinh theo thứ tự trong `GROUPS` (`area_meta.py`): nhóm lớn = số trước dấu chấm, vị trí trong nhóm = số sau. Đổi thứ tự hoặc thêm nhóm thì mã số đổi theo, nên khi trích dẫn hãy ghi kèm tên |
| Thêm nhóm feature mới | Thêm luật trong `RULES` (`areas.py`), mô tả trong `AREAS` và vị trí trong `GROUPS` (`area_meta.py`), bản dịch tên + mô tả trong `i18n_vi.py` |
| Sửa mô tả what / why / setup | `area_meta.py`, rồi sửa khoá tương ứng trong `i18n_vi.py` |
| Thêm / sửa thẻ phát hiện | `FINDINGS` trong `section9_html.py`: `[badge, title, detail, action, evidence]`, badge ∈ `new / ok / part / fix`. Thêm bản dịch cho title / detail / action |
| Sửa view GPU | Sửa thẳng trong HTML (khối `<script>` đầu tiên chứa `steps`, `rows`, `W`, `F`; mindmap ở khối thứ hai). **Không có generator** — ghi lại thay đổi trong `fix_gpu.py` nếu muốn tái lập được |
| Thêm chữ tiếng Anh mới ở bất kỳ đâu | Thêm khoá vào `i18n_vi.py`. Chuỗi có số thay đổi theo dữ liệu thì thêm luật vào `RULES` (regex JS, nhóm `$1`) |

Sau mỗi lần sửa: `build_page.py` → `verify_page.py`. Mục "untranslated in VI" phải bằng 0.

### 5.5 View "Theo dõi PR / Release" (`#obs/…`, cho team quản lý release & CI)

Mở trang, bấm **PR / Release watch** (hoặc phím `O`). Có 5 tab:

| Tab | Mục | Dùng để |
|---|---|---|
| Hiện tại (`#obs/now`) | 1 Radar release · 2 Cần xử lý + Thay đổi | Nhìn nhanh: stable / RC mới nhất, số PR đã merge chưa release, PR sẵn sàng merge, CI dev, tải CI, nightly. Danh sách cảnh báo tự tính từ dữ liệu |
| Hàng đợi PR (`#obs/prs`) | 3 Hàng đợi PR · 4 Đã merge từ stable | 100 PR cập nhật gần nhất, mỗi PR một nhóm (sẵn sàng / cổng merge fail / CI đang chạy / cần sửa / chờ review / xung đột / nháp). Chip cổng: DCO, Lint, k3 unit, k3 MP (+ GHA Test, CPU device tham khảo) |
| Release (`#obs/release`) | 5 Chuỗi release · 6 Publish run + nightly | rc1 → … → stable cho từng phiên bản, kết quả `publish.yml` của từng tag, từng job của publish run mới nhất, độ mới của các bản nightly |
| Sức khoẻ CI (`#obs/ci`) | 7 Sức khoẻ dev · 8 Hàng đợi CI | 10 build dev gần nhất mỗi pipeline Buildkite / workflow GitHub; build đang chạy, job chờ agent, thời gian chờ p50/p90 của k3-unit-tests và k3-multiprocess-test |
| Báo cáo theo kỳ (`#obs/trend`) | **Đã xoá 2026-11-13 (v2 P5).** Hash `#obs/trend` giờ mở tab Release; quyết định hằng ngày nằm ở tab Today (`#obs/today`) |

**Dữ liệu lấy từ đâu (Pipeline đồng bộ 100% miễn phí)**

| Cách | Khi nào | Lệnh |
|---|---|---|
| Đồng bộ vi sai + cắt tỉa 90 ngày (`sync_incremental.py`) | Cập nhật nhanh (< 15 giây) dữ liệu báo cáo lịch sử mà không quét lại từ đầu | `python -I -X utf8 sync_incremental.py` (đọc mốc `made`, chỉ kéo delta 48h gần nhất từ GitHub API, tự động xoá bản ghi cũ hơn 90 ngày để giữ file HTML cố định ~1.6 MB vĩnh viễn, rồi rebuild HTML) |
| Snapshot nhúng trong trang | Mặc định khi mở file (chạy cả khi offline) | `python -I -X utf8 observe_collect.py` (lấy dữ liệu → `observe_snapshot.json` → build lại trang) |
| ~~Làm mới trong trình duyệt~~ | **Đã tắt (2026-11-09).** Dữ liệu chỉ cập nhật bằng lần chạy local; không Refresh, không tự làm mới, không token trên UI, không CI/CD | — |

**Cập nhật = chỉ chạy local.** Thanh trên cùng hiện "Update: local run only · observe_collect.py". Token nằm ở máy chạy collector: GitHub qua `gh` đã đăng nhập, Buildkite qua `BUILDKITE_API_TOKEN`. Snapshot do `observe_collect.py` tạo **không** chứa token. Bật lại UI refresh: `CONFIG.local_only=False` trong `build_observe.py` (cần người phụ trách đồng ý).

**Thay đổi cấu hình:** repo, ID workflow, mẫu tên check của từng cổng, danh sách pipeline, ngưỡng cảnh báo (nightly cũ > 36 giờ, chờ > 30 phút, …) đều nằm trong `CONFIG` của `build_observe.py`. Loại cổng (merge / release / tham khảo) đọc từ `gates.py`.

**Lưu ý khi đọc**

- "Sẵn sàng merge" dùng `mergeStateStatus` của GitHub (CLEAN / UNSTABLE / HAS_HOOKS), chỉ hỏi cho PR đã approve vì trường này rất chậm (hỏi cho 100 PR thì GraphQL trả 502).
- Change feed so sánh hai lần dữ liệu **trong cùng trình duyệt** (lưu ở localStorage). Đổi chế độ (có / không token) thì không so PR để tránh báo nhầm.
- Một tag có thể có nhiều run `publish.yml` (event `push` và `release`). Chip hiện run mới nhất; rê chuột để xem tất cả. Ví dụ v0.5.7: run `push` pass, run `release` fail ở `Build image`.

### 5.6 Trace Agent: release → PR → đề xuất fix, cập nhật thẳng vào UI (từ v0.5.7)

**Quy tắc:** với release **v0.5.7 trở về sau** (gồm cả rc), mọi hướng fix hiện trên tracer `#obs/release` phải đi qua prompt [`knowledge/prompts/PR_FAILURE_TRACE_AGENT_PROMPT.md`](../../../../knowledge/prompts/PR_FAILURE_TRACE_AGENT_PROMPT.md). Text fix viết tay trong `report_model.py` không còn được hiển thị cho các release này. Release cũ hơn 0.5.7 vẫn hiện fix viết tay như trước.

**Cách nó chạy** (`trace_agent_daily.py`):

| Bước | Chi tiết |
|---|---|
| 1. Release | Mỗi release ≥ v0.5.7 trong tracer, theo thứ tự rc1 → stable |
| 2. PR | Với từng PR của release: `gh pr checks` (rẻ, không gọi agent). Kết quả ✓/✗ hiện ngay trên node PR |
| 3. Truy vết | PR có check **fail** → chạy prompt với `{{PR_OR_BUILD}}` = PR đó, bằng `claude -p` **chỉ đọc** (gh view/list/api GET, git log/show/diff, Buildkite MCP; chặn Edit/Write, rerun, comment, push). Trần $3/PR, 25 phút/PR, $20/lần chạy |
| 4. Cập nhật UI | Sau **mỗi PR**: ghi `outputs/trace_agent/proposals.json` + `proposals.js`. Trang đang mở đọc lại `proposals.js` mỗi 30 giây và vẽ lại tracer (header hiện `● live`), **không cần build lại** |
| 5. Build | Cuối lần chạy: `build_page.py` + `verify_page.py` để nhúng snapshot vào trang (dùng khi mở trên gh-pages). **Không push** |

PR được truy vết lại khi: mới có check fail, danh sách check fail đổi, lần chạy trước lỗi, hoặc đề xuất cũ hơn `--max-age-hours` (mặc định 168h = 1 tuần). Check CI thì được đọc lại mỗi ngày.

| Việc | Lệnh (ở thư mục gốc `CacheAgent`) |
|---|---|
| Xem release, PR và trạng thái | `python -I -X utf8 LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/trace_agent_daily.py --list` |
| Chạy hằng ngày | `... trace_agent_daily.py` |
| Chỉ đọc check CI, không gọi agent | `... trace_agent_daily.py --checks-only` |
| Một release / một PR | `... trace_agent_daily.py --tag v0.5.7rc4 --pr 6208` |
| Truy vết lại dù đề xuất còn mới | thêm `--force` |
| Không build trang ở cuối | thêm `--no-build` |

**Trên trang:**

| Chỗ | Hiện gì |
|---|---|
| Header tracer | `🤖 Trace Agent: x/y PR đã kiểm · n lỗi · m đã đề xuất · thời gian · ● live` |
| Node PR (cột 2) | Badge `CI ✓`, `CI ✗n`, hoặc `🤖 ✗n` khi đã có đề xuất |
| Stage 1 | Tổng kết Trace Agent của release + chip các PR có check lỗi |
| Stage 2 | Chip PR có ✓/✗/🤖, danh sách check lỗi có link, khối đề xuất của PR |
| Stage 5 + cột phải | Nguyên nhân gốc + hướng fix từ đề xuất của PR đang chọn; nếu chưa có thì "⏳ đang chờ truy vết" kèm lệnh chạy |

**Lịch chạy:** Windows Task Scheduler `CacheAgent\TraceAgentDaily`, 07:30 mỗi ngày, gọi `outputs/cpu_tests/run_trace_agent_daily.cmd` (log ở `outputs/trace_agent/scheduler.log`). Task chỉ chạy khi bạn đang đăng nhập Windows.

| Việc | Lệnh |
|---|---|
| Đăng ký | `schtasks /create /tn "CacheAgent\TraceAgentDaily" /sc daily /st 07:30 /tr "\"<đường dẫn>\run_trace_agent_daily.cmd\"" /f` |
| Chạy ngay | `schtasks /run /tn "CacheAgent\TraceAgentDaily"` |
| Gỡ | `schtasks /delete /tn "CacheAgent\TraceAgentDaily" /f` |

Biến môi trường tùy chọn: `TRACE_AGENT_MODEL`, `TRACE_AGENT_BUDGET_USD` ($/PR), `TRACE_AGENT_BUDGET_TOTAL_USD` ($/lần chạy), `CLAUDE_BIN`.

### 5.7 Ba hướng trace mới: Flaky · Tải GPU · Bug (`#obs/flaky`, `#obs/gpuload`, `#obs/bug`)

Thêm ngày 2026-11-09. Trace Agent theo release (5.6) giữ nguyên; ba tab này là ba hướng trace khác.

| Tab | Trả lời câu hỏi | Dữ liệu | Prompt agent |
|---|---|---|---|
| 9 · Flaky (`#debug`, `#optimal`) | Job nào lỗi lần đầu rồi qua khi retry cùng commit? Tốn bao nhiêu GPU-h? | Chuỗi retry job MP 30 ngày (`../P1/`), GHA Test `run_attempt`, build đổi kết quả cùng commit | `knowledge/prompts/TRACE_FLAKY_AGENT_PROMPT.md` |
| 10 · Tải GPU (`#optimal`, `#increase PRs merged`) | GPU-h đi đâu, phần nào lãng phí, đòn bẩy nào tiết kiệm nhất, ảnh hưởng thời gian chờ merge | `cost_by_workload.csv`, build theo kết quả, `fastfail_savings.json` | `knowledge/prompts/TRACE_GPU_LOAD_AGENT_PROMPT.md` |
| 11 · Bug / Lỗi (`#6530`) | Truy vết một issue / PR từ lỗi đầu tiên đến hướng fix | GitHub live (trình duyệt), số mặc định ở `trace_dirs_model.BUG_TARGET` | `knowledge/prompts/TRACE_BUG_AGENT_PROMPT.md` |

| File | Vai trò |
|---|---|
| `trace_dirs_model.py` | Tính số liệu cho 3 tab → `../trace_agent/directions.json` + `directions.js` |
| `_retired/build_trace_dirs.py` | Đã bỏ (2026-11-13, v2 P5): 3 tab flaky / gpuload / bug đã xoá khỏi trang; hash cũ dẫn sang tab còn hiện |
| `trace_agent_dirs.py` | Chạy agent theo hướng → `../trace_agent/directions/<dir>.json`; trang đọc lại mỗi 30 giây |

Lệnh (từ thư mục gốc CacheAgent):

```
python -I -X utf8 LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/trace_agent_dirs.py --data-only     # chỉ làm mới số liệu, không tốn phí
python -I -X utf8 LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/trace_agent_dirs.py --dir flaky     # chạy agent 1 hướng (tối đa $3)
python -I -X utf8 LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/trace_agent_dirs.py --dir bug --bug 6531
```

- Agent chỉ chạy lại khi: chưa có kết quả, dữ liệu đổi, lần trước lỗi, hoặc kết quả cũ hơn 7 ngày.
- Tab Bug: khi số chưa tồn tại trên GitHub, agent bỏ qua (không tốn phí). Đổi số trong ô "Mục tiêu" chỉ nhớ trong trình duyệt; đổi mặc định ở `BUG_TARGET`.
- Số liệu Flaky / GPU lấy từ cache `../P1/` (cửa sổ 2026-10-05 → 2026-11-04). Muốn số mới hơn: chạy lại `../P1/fetch_builds.py` và `build_jobs_table.py`, `aggregate.py`.

### 5.4 Trước khi chia sẻ trang

1. `verify_page.py` ra **PASS**.
2. Xem ảnh ở cả 2 ngôn ngữ, 2 view.
3. Các con số mới phải có bằng chứng: run ID, build ID hoặc `file:line` trong thẻ phát hiện.
4. Trang đang private (file local). Muốn đưa lên mạng thì hỏi trước: trang có tên job, đường dẫn nội bộ và một nhận định bảo mật (HF_TOKEN).

---

## 6. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Mục 6 hiện "not collected", số dòng = 0, không có file nào chạy được trên CPU | Thiếu `src/` hoặc sai commit | Làm lại bước 3, hoặc đặt `LMCACHE_SRC=<đường dẫn>` |
| `parse.py` ra số pass thấp hơn log | Định dạng log đổi (dòng bị tách, tham số có dấu cách) | Xem regex `LINE` / `NODE` / `STAT` trong `parse.py`; so với `grep -c "PASSED" job312.log` |
| `UnicodeEncodeError: 'charmap'` | Python in ra console Windows | Thêm `-X utf8` |
| Bản VI còn chữ tiếng Anh | Câu tiếng Anh đổi nhưng chưa sửa khoá trong `i18n_vi.py` | `verify_page.py` sẽ liệt kê; thêm khoá |
| Tab trống, hoặc mindmap nhỏ xíu | Lỗi JS, hoặc mindmap fit lúc bị ẩn | `verify_page.py` báo lỗi JS; mindmap tự fit khi mở tab Khám phá |
| `fix_gpu.py` in `applied 0` | Bình thường: bản sửa đã có | Không cần làm gì |
| Bash báo "unexpected EOF" khi dán script Python dài | Heredoc gặp dấu nháy | Ghi script ra file rồi chạy |

---

## 7. Quy tắc an toàn

- **Chỉ đọc** với GitHub và Buildkite: không re-run, không cancel, không comment nếu chưa được đồng ý.
- **Không** `checkout` / `reset` / `stash` trong `third_party/LMCache`: working tree đang có thay đổi chưa commit. Chỉ dùng `fetch` + `git show` / `git archive`.
- Không push hay mở PR từ thư mục này.
- Số liệu nào chưa kiểm chứng thì ghi rõ "estimate" / "reported", như tile −80% và HF_TOKEN.

---

## 8. Việc còn mở (ưu tiên cho SDD fail-fast)

| # | Việc | Vì sao |
|---|---|---|
| 1 | ~~Diff từng test k3 vs GHA~~ **Đã xong** (`k3_overlap.py`): 8,994 chung · 327 chỉ GHA · 1,264 chỉ k3. Việc tiếp theo: quyết định gate 327 test vLLM | Không điều kiện chặn merge nào bao phủ 327 test vLLM connector |
| 2 | Lịch sử fail theo từng file test, ≥30 ngày (GHA + k3) | Căn cứ cho quarantine; hiện mới có 21 run |
| 3 | Chạy nightly cả 5 phiên bản Python, không fail-fast | Biết lỗi có phụ thuộc phiên bản không, trước khi giảm số phiên bản cho PR |
| 4 | Chuyển 13 file "chạy được trên CPU" (≈9.7k dòng) sang CPU | Task 2 |
| 5 | Sửa nhanh: mock HF trong `test_create_workload.py`; patch `_EVICTION_SETTLE_SECONDS` = 0 | −70 s mỗi phiên bản, bớt test flake do mạng |
| 6 | Tự động hoá bước 5–6 của mục 5.2 (đọc số Buildkite → ghi vào template) | Bớt sửa tay, bớt quên bản dịch |

Ngoài lề, cần báo release owner: publish run `42131253314` của tag `v0.5.7` có job `test: 3.10` treo ở `in_progress` hơn 15 giờ (kiểm tra 2026-11-06), nên chặn bước publish.

---

## 9. Tài liệu liên quan

| Tài liệu | Nội dung |
|---|---|
| [`README.md`](README.md) | Danh sách file, lệnh rebuild ngắn |
| [`REVIEW_ponytail.md`](REVIEW_ponytail.md) | Review độc lập, bằng chứng cho từng nhận định |
| `../../README.md`, `../../03_APPROACH_AND_PLAN.md` | Kế hoạch Plan 2026-11 (lightweight tests, P1–P11) |
| `../P1/`, `../P2/`, `../P8/` | Dữ liệu và phân tích cho view GPU |
| `../../../../LM-1077-vllm-stable-pin/`, `../../../../LM-781-vendor-pypi/`, `../../../../LM-1062-fast-fail/` | Task A (Docker vLLM stable), B (vendor PyPI), C (fast-fail cancel) |


## Cập nhật 2026-11-15: dữ liệu registry, Go/No-Go, kiểm tra mobile

| Việc | Lệnh / file |
|---|---|
| Lấy dữ liệu registry (PyPI, Docker Hub, GitHub; cần mạng) | `cd LM-762-ci-resource/ops-app/backend && python -X utf8 collect_release.py` |
| Đưa dữ liệu vào trang | Tự động: `build_today.py` chạy `ops-app/backend/export_page_data.py` → `release_desk.json` (không cần mạng) |
| Tab Hôm nay | Thêm: dải Go/No-Go cho RC tiếp, bản rollback `$GOOD`, tuổi dữ liệu theo **nguồn cũ nhất**, chip "dữ liệu N d" (> 48 giờ), dòng lỗi đầu tiên của job publish, hàng PR chờ maintainer + nút copy lệnh `gh pr edit … --add-label full`, LKG cho pipeline đỏ |
| Tab Release | Thêm: dòng "Registry x/y" mỗi release + ma trận artifact. Không bỏ cột nào |
| Kiểm tra điện thoại 390 px | `python -X utf8 check_mobile.py` (dùng iframe 390 px: Chrome headless có bề rộng cửa sổ tối thiểu 518 px nên ảnh `--window-size=390` bị cắt, báo tràn sai) |
| build_gates `sub_block` | Không còn crash khi trang bị format lại: so khớp đầu dòng + bỏ qua khoảng trắng; thiếu điểm cuối → in `skip` |

## Cập nhật 2026-11-15 (tối): Release Management có thêm tab Release Desk và Xu hướng

| Việc | Chi tiết |
|---|---|
| Kiến trúc | Giữ 3 mục lớn: Quản lý Release · Khám phá Release · Report 1130. Chỉ mục Quản lý Release thay đổi; 2 mục kia giữ nguyên nội dung (chỉ thêm CSS cho màn hẹp ≤ 700 px) |
| `#obs/today` = **0 · Bây giờ · Release Desk** (mặc định) | Đang ở đâu (verdict + 5 thẻ STABLE / $GOOD / tag mới nhất / quyết định mở / đang chặn), tuổi dữ liệu từng nguồn + STALE, D1–D4 + bằng chứng, đang chặn (publish lỗi, thiếu artifact, dev đỏ + LKG, bug, mang sang; owner + copy lệnh), pipeline gate, rồi Hộp việc hôm nay (BLOCK / FIX / REBASE + PR chờ 'full') |
| `#obs/hist` = **1 · Xu hướng** | Thẻ KPI + delta, nightly, publish.yml theo tuần, tỉ lệ xanh gate 30 ngày, chu kỳ release, job fail nhiều nhất |
| Builder | `build_desk.py` (chạy sau `build_today.py` trong chuỗi `build_page.py`), đọc `release_desk.json` (`overview`, `history`, `lkg` từ ops-app) |
| Kiểm tra | `verify_page.py` (JS, VI, tab) và `check_mobile.py` (28 tab của cả 3 mục, iframe 390 px) |
