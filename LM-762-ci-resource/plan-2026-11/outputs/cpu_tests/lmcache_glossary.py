"""LMCache domain glossary for onboarding & test explorer ("LMCache meaning" column).

Rewritten for newcomer clarity (/ponytail mode):
- Plain language: explains WHAT it is and WHY it matters instead of raw internal jargon.
- Intuitive mental model: LMCache = shared KV cache (CDN/Redis) for LLM inference engines.
- Bilingual: English (crisp technical clarity) and Vietnamese (natural, intuitive dev explanation).
"""

# area id -> (EN, VI): where this area sits in LMCache
AREA_ROLE = {
    "vllm": (
        "vLLM ↔ LMCache Bridge: Connects vLLM scheduler & workers to LMCache to save/reload KV caches directly in GPU VRAM",
        "Cầu nối vLLM ↔ LMCache: Nối scheduler và worker của vLLM với LMCache để nạp/lưu KV cache thẳng vào VRAM GPU",
    ),
    "engines": (
        "Multi-Engine Adapters: Standardized connectors plugging LMCache into SGLang, TensorRT-LLM, and AMD ATOM",
        "Adapter đa Engine: Cổng cắm chuẩn hóa nối LMCache vào SGLang, TensorRT-LLM và AMD ATOM",
    ),
    "lazy": (
        "Lazy Offload & Token Drop: Saves memory by deferring KV writes until GPU is full and dropping non-critical tokens",
        "Xả đệm lười & Bỏ token: Tiết kiệm bộ nhớ bằng cách chỉ lưu KV khi GPU sắp đầy và loại bỏ token dư thừa",
    ),
    "blend": (
        "CacheBlend (Non-Prefix Reuse): Reuses cached KV from documents placed in the middle of prompts by recalculating RoPE",
        "CacheBlend (Tái sử dụng phi tiền tố): Tái sử dụng KV của tài liệu nằm ở giữa prompt bằng cách tính toán lại RoPE",
    ),
    "lifecycle": (
        "Server Daemon Lifecycle: Handles auto-start, worker heartbeat monitoring, and graceful resource cleanup on exit",
        "Vòng đời tiến trình Server: Tự bật daemon ngầm, theo dõi nhịp tim worker và dọn sạch RAM/socket khi tắt",
    ),
    "transport": (
        "IPC & RPC Transport: High-speed control messaging channel between inference engines and LMCache (ZeroMQ / gRPC)",
        "Kênh giao tiếp IPC / RPC: Đường truyền lệnh điều khiển tốc độ cao giữa engine suy luận và LMCache (ZeroMQ / gRPC)",
    ),
    "modules": (
        "Plugin & Extension Hooks: Modular interfaces allowing custom storage adapters and runtime features without core edits",
        "Cơ chế Plugin mở rộng: Cổng cắm module cho phép gắn backend lưu trữ hoặc tính năng tùy biến mà không sửa core",
    ),
    "datapath": (
        "Tensor Datapath: moves KV bytes between GPU VRAM and LMCache — LMCache-driven (default on CUDA/NPU, zero-copy via IPC/SHM handles) or engine-driven (worker gathers / scatters a copy)",
        "Đường truyền Tensor: chuyển byte KV giữa VRAM GPU và LMCache — LMCache-driven (mặc định trên CUDA/NPU, zero-copy qua IPC/SHM handle) hoặc engine-driven (worker gather / scatter một bản copy)",
    ),
    "lookup": (
        "Prompt Lookup & Prefetch: Hashes prompt tokens to check cache hits and pre-warms KV into RAM before inference starts",
        "Tra cứu & Nạp trước (Lookup & Prefetch): Băm token để kiểm tra cache hit và kéo sẵn KV vào RAM trước khi GPU tính",
    ),
    "http": (
        "Management HTTP APIs: REST endpoints for health checks, live configuration reload, metrics, and auth security",
        "API Quản trị HTTP: Cổng REST để kiểm tra sức khỏe hệ thống, đổi cấu hình nóng, xem quota và xác thực bảo mật",
    ),
    "l1": (
        "L1 Hot Cache (Host DRAM): Fast in-memory cache tier on CPU RAM with auto-eviction (LRU/ARC) when full",
        "L1 Cache nóng (RAM máy chủ): Tầng nhớ đệm siêu tốc trên RAM CPU, tự dọn dẹp (LRU/ARC) khi bộ nhớ đầy",
    ),
    "smcore": (
        "Storage Manager Brain: Core ledger managing chunk keys, token-hit bitmaps, tenant quotas, and tier policies",
        "Lõi Quản lý Lưu trữ: Bộ não quản lý danh bạ khóa chunk, bitmap đánh dấu hit token, quota và chính sách các tầng",
    ),
    "l2": (
        "L2 Persistent Storage: Remote and durable storage tier (Local NVMe, S3, MinIO, Valkey/Redis) for multi-node sharing",
        "L2 Kho lưu trữ bền vững: Tầng lưu trữ ngoài (SSD, S3, MinIO, Redis) để giữ cache vĩnh viễn và chia sẻ đa cụm",
    ),
    "serde": (
        "Serde (Codec & Security): quantization (FP8, K16/V8, TurboQuant) and AES-GCM encryption to shrink and secure KV in L2",
        "Serde (Nén & Bảo mật): lượng tử hoá (FP8, K16/V8, TurboQuant) và mã hoá AES-GCM để KV ở L2 nhỏ hơn và an toàn",
    ),
    "p2p": (
        "P2P Cache Sharing: Direct node-to-node KV streaming across GPU instances without bottlenecking central storage",
        "Chia sẻ ngang hàng P2P: Các node GPU tự truyền KV cache trực tiếp cho nhau, không làm nghẽn máy chủ trung tâm",
    ),
    "gds": (
        "GPU Direct Storage (GDS): Direct DMA streaming between NVMe disks and GPU VRAM, bypassing CPU RAM bottlenecks",
        "GPU Direct Storage (GDS): Đọc/ghi cache trực tiếp giữa ổ NVMe và VRAM GPU qua DMA, bỏ qua nghẽn cổ chai CPU",
    ),
    "orch": (
        "Memory Partition Orchestrator: Allocates and isolates shared memory regions across multiple parallel engine workers",
        "Điều phối Phân vùng Nhớ: Phân bổ và cô lập các vùng nhớ dùng chung (shm) giữa nhiều tiến trình worker song song",
    ),
    "layout": (
        "KV Tensor Layout: Adapts to model-specific attention architectures (DeepSeek MLA, Mamba, Multi-Head Attention)",
        "Hình học Tensor KV: Xử lý cấu trúc nhớ đặc thù của từng kiến trúc mô hình (DeepSeek MLA, Mamba, MHA tiêu chuẩn)",
    ),
    "platform": (
        "Hardware Abstraction Layer: Cross-vendor device support across NVIDIA (CUDA), AMD (ROCm), Intel (XPU), and Moore Threads (MUSA)",
        "Tầng phần cứng đa nền tảng: Hỗ trợ chạy trên GPU NVIDIA (CUDA), AMD (ROCm), Intel (XPU) và Moore Threads (MUSA)",
    ),
    "native": (
        "Native C++ Core: High-performance C++ extensions for ultra-fast memory copy, tensor slicing, and token hashing",
        "Nhân tối ưu C++: Các hàm mở rộng viết bằng C++ giúp tăng tốc tối đa việc copy bộ nhớ, cắt tensor và băm token",
    ),
    "coord": (
        "Fleet Coordinator: central directory of which node holds which chunk (placement lookup), plus fleet quota, eviction and warm prefetch",
        "Tổng chỉ huy Cụm (Coordinator): danh bạ trung tâm cho biết node nào giữ chunk nào (placement lookup), kèm quota, eviction và warm prefetch toàn cụm",
    ),
    "obs": (
        "Observability & Telemetry: Real-time cache hit-rate, save/lookup latencies, and memory stats exported to Prometheus/Grafana",
        "Giám sát & Đo lường: Theo dõi thời gian thực tỷ lệ trúng cache (hit-rate), độ trễ đọc/ghi và tài nguyên cho Prometheus/Grafana",
    ),
    "ip_engine": (
        "Legacy In-Process Engine (v1): Embedded LMCache running inside the vLLM worker process (superseded by MP v2 architecture)",
        "Engine Đơn tiến trình v1 (Cũ): LMCache chạy trực tiếp bên trong worker vLLM (đã được thay thế bởi kiến trúc đa tiến trình MP v2)",
    ),
    "ip_store": (
        "Legacy In-Process Storage (v1): Original local/remote storage backend implementations from LMCache v1",
        "Kho Lưu trữ v1 (Cũ): Các backend lưu trữ cục bộ/từ xa đời đầu của LMCache v1",
    ),
    "ip_ctrl": (
        "Legacy In-Process Controller (v1): Original single-process control loop and health monitors from LMCache v1",
        "Bộ điều khiển v1 (Cũ): Quản lý vòng đời và luồng điều khiển của kiến trúc đơn tiến trình v1",
    ),
    "cli": (
        "CLI & Benchmarking Tools: Command-line utilities for cache inspection, load testing, latency profiling, and stress tests",
        "Dòng lệnh & Đo kiểm (CLI): Công cụ dòng lệnh để kiểm tra cache, đo throughput, latency và chạy benchmark chịu tải",
    ),
    "frontend": (
        "Application Gateway & SDK: Client library for developers to query cache status and manage prompt cache from applications",
        "Cổng Ứng dụng & SDK: Thư viện client giúp lập trình viên quản lý và tái sử dụng KV cache trong các ứng dụng RAG/Chatbot",
    ),
    "build": (
        "Packaging & Repo Governance: Python wheel packaging, C++ compilation flags, linting rules, and CI gates",
        "Đóng gói & Quản trị Repo: Cấu hình build wheel, cờ biên dịch C++, quy chuẩn linting và các cổng kiểm thử CI",
    ),
    "other": (
        "Auxiliary Utilities: Miscellaneous support helpers, test fixtures, and shared baseline utilities",
        "Tiện ích phụ trợ: Các file fixture kiểm thử, hàm tiện ích chung và script mẫu",
    ),
}

# (JS regex on lower-cased "test name + docstring", EN, VI) — first matches win, max 3 per test
CONCEPTS = [
    (r"chunk|unfull|block",
     "Chunk: Fixed block of prompt tokens (e.g. 256) stored as a single cache unit",
     "Chunk: Khối token cố định (vd: 256 token) được lưu trữ thành một đơn vị cache cơ bản"),
    (r"hash|\bkey|codec",
     "Cache Key: Cryptographic hash identifying the prompt tokens and model namespace",
     "Cache Key: Mã băm duy nhất đại diện cho chuỗi token và định danh mô hình"),
    (r"lookup|\bhit|\bmiss",
     "Lookup (Hit/Miss): Checks if prompt prefix exists in cache to skip recomputing",
     "Lookup (Hit/Miss): Kiểm tra prompt đã có trong cache chưa để bỏ qua bước tính toán GPU"),
    (r"retriev|\bload|reload",
     "Retrieve: Loads cached KV tensors directly into GPU VRAM to speed up TTFT",
     "Retrieve: Kéo KV tensor từ cache nạp thẳng vào VRAM GPU để giảm tối đa TTFT"),
    (r"\bstore|\bsave|\bput\b|offload",
     "Store: Offloads newly computed KV from GPU memory into LMCache for reuse",
     "Store: Lưu KV tensor vừa sinh từ GPU vào LMCache để phục vụ các request kế tiếp"),
    (r"prefetch|warm",
     "Prefetch: Proactively pulls KV from remote/disk into fast DRAM before inference starts",
     "Prefetch: Kéo trước KV từ đĩa/mạng vào RAM máy chủ trước khi GPU bắt đầu suy luận"),
    (r"evict|lru|\barc\b",
     "Eviction (LRU/ARC): Smart garbage collection that discards cold chunks when cache is full",
     "Eviction (LRU/ARC): Thu hồi bộ nhớ thông minh — tự dọn chunk ít dùng khi cache chạm giới hạn"),
    (r"\bl1\b|l1_|dram|devdax|\bdax",
     "L1 Tier: Hot in-memory cache residing directly on host CPU DRAM / CXL",
     "Tầng L1: Cache nóng siêu tốc nằm trực tiếp trên RAM CPU của máy chủ / CXL"),
    (r"\bl2\b|l2_|remote|backend|\bs3\b|valkey|resp|bigtable|nixl|mooncake|\bfs\b|disk",
     "L2 Tier: Persistent or shared storage tier (Local NVMe, S3, MinIO, Valkey/Redis)",
     "Tầng L2: Kho lưu trữ bền vững hoặc dùng chung qua mạng (NVMe, S3, MinIO, Redis)"),
    (r"blend|rope|fingerprint",
     "CacheBlend: Reuses non-prefix document chunks anywhere in prompt via RoPE rotation",
     "CacheBlend: Tái sử dụng KV ở giữa prompt (RAG documents) bằng cách tính lại góc quay RoPE"),
    (r"preempt",
     "Preemption: Safely saves and restores KV when engine pauses a request under heavy load",
     "Preemption: Tạm lưu và nạp lại KV an toàn khi engine bị quá tải phải hoãn request"),
    (r"lora",
     "LoRA Cache Isolation: Separates cache keys by adapter ID so fine-tuned weights never mix",
     "LoRA Cache Isolation: Tách riêng khóa cache theo adapter để tránh nạp nhầm trọng số mô hình"),
    (r"\bmm\b|multimodal|image|mm_hash|placeholder",
     "Multimodal Cache: Hashes image embeddings into cache key for Vision-Language Models",
     "Multimodal Cache: Đưa cả embedding hình ảnh vào cache key để lưu đệm cho mô hình thị giác"),
    (r"\bmla\b|mamba|hybrid|group|swa|layout|stride|format",
     "KV Layout: Special tensor layouts for DeepSeek MLA, Mamba, and sliding-window attention",
     "KV Layout: Định dạng tensor nén cho DeepSeek MLA, Mamba và sliding-window attention"),
    (r"\btp\b|rank|world|dcp|parallel",
     "Tensor Parallel: Synchronizes and slices KV cache across multi-GPU parallel ranks",
     "Tensor Parallel: Đồng bộ và phân chia KV cache chuẩn xác giữa các GPU chạy song song"),
    (r"\bshm\b|ipc|transfer|copy|gather|scatter|staging",
     "KV transfer: LMCache-driven = zero-copy via IPC/SHM handles; engine-driven = the worker copies through shm or inline",
     "Truyền KV: LMCache-driven = zero-copy qua IPC/SHM handle; engine-driven = worker copy qua shm hoặc inline"),
    (r"zmq|grpc|rpc|transport|wire|socket|\bmq\b",
     "RPC Transport: Low-latency request channel (ZeroMQ/gRPC) coordinating engine and server",
     "RPC Transport: Kênh giao tiếp điều khiển độ trễ thấp (ZeroMQ/gRPC) giữa engine và LMCache"),
    (r"\block|\bpin|ref ?count|owner",
     "Memory Pinning & Locks: Prevents active KV chunks from being evicted or modified while in use",
     "Memory Pinning: Khóa vùng nhớ an toàn, chống việc xóa hoặc ghi đè chunk trong khi GPU đang đọc"),
    (r"quota|usage|capacity",
     "Capacity Quota: Enforces memory boundaries per tenant to prevent Out-Of-Memory crashes",
     "Capacity Quota: Áp đặt giới hạn dung lượng từng tenant để ngăn chặn tràn bộ nhớ (OOM)"),
    (r"salt|tenant|identity|namespace|model_id|revision",
     "Tenant Isolation: cache_salt and identity tags keep caches of different users / models apart",
     "Tenant Isolation: cache_salt và tag định danh giữ cache của người dùng / model khác nhau tách biệt"),
    (r"restart|recover|reconnect|heartbeat|re-?register",
     "Fault Tolerance & Recovery: Automatic reconnection and cache preservation across crashes",
     "Fault Tolerance: Tự động kết nối lại và giữ nguyên cache khi server hoặc worker khởi động lại"),
    (r"health|liveness|alive|\bping|timeout|hang",
     "Health Watchdog: Continuous health checks and heartbeat detection to catch stuck workers",
     "Health Watchdog: Giám sát nhịp tim liên tục để kịp thời phát hiện và cô lập tiến trình bị treo"),
    (r"schedul",
     "Scheduler Integration: Engine scheduler logic deciding which blocks to load or store",
     "Tích hợp Scheduler: Bộ điều phối của engine quyết định block nào cần nạp trước hoặc xả ra cache"),
    (r"worker",
     "Worker Execution: GPU worker execution context performing the actual tensor copy operations",
     "Thực thi Worker: Tiến trình GPU worker thực hiện trực tiếp các thao tác nạp/lưu tensor"),
    (r"metric|trace|event|log",
     "Telemetry & Profiling: Exporting hit-rates, memory footprints, and latencies for observability",
     "Telemetry & Profiling: Xuất dữ liệu hit-rate, dung lượng nhớ và độ trễ phục vụ giám sát vận hành"),
    (r"auth|token_?key|api.?key|bearer|secur",
     "Access Control: Bearer token and API key validation securing LMCache endpoints",
     "Kiểm soát Truy cập: Xác thực token và API key bảo vệ các endpoint của LMCache"),
    (r"serde|quant|fp8|encrypt|compress",
     "Serde: quantizes (FP8, K16/V8, TurboQuant) and encrypts (AES-GCM) KV to cut I/O and storage",
     "Serde: lượng tử hoá (FP8, K16/V8, TurboQuant) và mã hoá (AES-GCM) KV để giảm I/O và dung lượng"),
    (r"concurr|thread|race|async|deadlock",
     "Concurrency Safety: Thread-safe and async designs (locks, futures) preventing race conditions",
     "An toàn Đồng thời: Thiết kế thread-safe và bất đồng bộ giúp tránh tranh chấp tài nguyên (race condition)"),
    (r"config|\barg|cli|flag|\benv",
     "Configuration Engine: Parsing YAML configs, CLI flags, and environment variables safely",
     "Cấu hình Hệ thống: Đọc và kiểm tra tính hợp lệ của file YAML, cờ lệnh và biến môi trường"),
    (r"fail|error|raise|reject|invalid|unsupported|close",
     "Fail-Safe Guard: Rejects corrupt or invalid operations safely without data degradation",
     "Fail-Safe Guard: Chặn các thao tác lỗi hoặc dữ liệu sai lệch một cách an toàn, chống hỏng cache"),
]
