# P6 / R5 — Representative small-model set for lightweight smoke (WS-E, S5)

Source: local clone `third_party/LMCache` at `fcd50cea` (2026-11-04). Paths are relative to that repo.
HF configs were fetched from `https://huggingface.co/<repo>/raw/main/config.json` on 2026-11-04.
Memory numbers are **estimates** (params x bytes, no activations). Measure on a real run before you gate on them.

## TL;DR

- MP CI uses **7 KV layout families**. Only 2 of them (sparse-MLA+fp8, hybrid MLA+KDA) are behind the big 4-GPU / 2-GPU jobs.
- **The XPU pipeline already runs most of this smoke set on 1 device** with dummy or tiny models
  (`.buildkite/k3_tests/xpu/multiprocess/pipeline.yml:137-247`): `hma_kda_mla_correctness`, `hma_swa_correctness`,
  `hma_dsv4_correctness` (DSV4-Flash, `--load-format dummy`, 4 layers). The CUDA MP pipeline does **not** run them.
  The cheapest WS-E step is: **port these 3 XPU steps to CUDA 1-GPU** and add 2 more (plain MLA, GQA).
- Use `hma_bit_correctness.py` (3-stage check: cold → GPU APC reference → LMCache restore; compares token IDs + top-100 logprobs)
  as the `layout_smoke` checker. It is stronger than the `cmp` text check in `l1-round-trip-verification.sh:114` for dummy weights.
- Keep **per-layer KV shape identical** to the production model (use the real config + `num_hidden_layers` override),
  not a "tiny-random" repo. Tiny-random repos change head dims, which changes vLLM block-size padding for hybrid models.
- Kimi-Linear cross-TP bug class needs **TP>=2**. Keep a TP=2 job, but with a 4-layer dummy model (~3 GB) instead of 48B.

---

## 1. KV layout families in MP CI today

| # | Family | Production model in CI | Workload(s) | GPUs / TP | Engine launch flags that matter | Source |
|---|---|---|---|---|---|---|
| F1 | MHA/GQA, bf16 (8 KV heads x 128) | `Qwen/Qwen3-14B` | default for ~all common workloads (lm_eval, long_doc_qa, vllm_bench, restart_recovery, http_api, ...) | 1–2 / TP1 | `--attention-backend FLASH_ATTN` (default), `--gpu-memory-utilization 0.5` on >90 GB GPUs | `scripts/engines/vllm.sh:5,67-75`; `scripts/run-single-test.sh:51` |
| F1b | MHA (OPT), CPU | `facebook/opt-125m` | `cpu_e2e_validation` (Buildkite CPU pod + GHA) | 0 | vLLM CPU, `VLLM_CPU_KVCACHE_SPACE=1` | `.github/scripts/run-cpu-e2e-validation.sh:27-63`; `.github/workflows/cpu_device.yml:99-107` |
| F2 | Plain MLA, bf16 (latent 512 + rope 64 = 576, 1 "head") | `deepseek-ai/DeepSeek-V2-Lite-Chat` | `deadlock` (no-hang only, **no** byte check) | 2 / TP2 | `--load-format dummy --block-size 64 --trust-remote-code --hf-overrides '{"max_position_embeddings":65536}' --enforce-eager` | `scripts/run-single-test.sh:114-123`; `scripts/engines/vllm.sh:330-360` |
| F2 | Plain MLA, CPU | `DeepSeek-V2-Lite-Chat` (2 layers, 4 experts, dummy) | GHA `cpu-device-test` matrix | 0 | `--load-format dummy`, `hf_overrides {"num_hidden_layers":2,"n_routed_experts":4,"first_k_dense_replace":0,"num_experts_per_tok":2}`, `VLLM_MLA_DISABLE=0` | `.github/workflows/cpu_device.yml:109-133` |
| F3 | Sparse-MLA + fp8 + slot compression (groups with tokens_per_block 256/64/8/4; SWA + C4 + C128 + fp32 indexer) | `deepseek-ai/DeepSeek-V4-Flash` | `dsv4_flash_tp` | **4** / TP4 | vLLM: `--kv-cache-dtype fp8_ds_mla --tokenizer-mode deepseek_v4 --enable-expert-parallel --trust-remote-code --enforce-eager --enable-prefix-caching`, chunk 256, `--separate-object-groups`. SGLang: `--tp 4 --enable-lmcache`, page 256, lmcache_driven only. Needs SM90/SM100/SM120 (DeepGEMM). | `workloads/vllm/dsv4-flash-tp.sh:16-24,73,245-257`; `workloads/sglang/dsv4-flash-tp.sh:27-48,86-96`; `pipeline.yml:90-122` |
| F4 | Hybrid MLA + linear attention (KDA recurrent/conv state, **sharded across TP**) | `moonshotai/Kimi-Linear-48B-A3B-Instruct` | `kimi_linear_tp` | **2** / TP2 | vLLM: `--tensor-parallel-size 2 --trust-remote-code --enforce-eager --moe-backend triton --mamba-cache-mode align --block-size 944 --max-num-batched-tokens 1500`. SGLang: `--tp-size 2 --attention-backend triton --linear-attn-backend triton --page-size 64 --mamba-radix-cache-strategy extra_buffer --mamba-track-interval 256`, chunk 256 | `workloads/vllm/kimi-linear-tp.sh:52-56,107-121`; `workloads/sglang/kimi-linear-tp.sh:24-30,72-85`; `pipeline.yml:226-246` |
| F5 | SWA + full attn, **different head dims** (256 / 512), K=V on full layers | `google/gemma-4-31B-it` | `hma_lm_eval_gemma4` — **disabled** on CUDA | 1 / TP1 | `ATTENTION_BACKEND=auto` (TRITON_ATTN), high `GPU_MEMORY_UTILIZATION`, `--separate-object-groups` | `pipeline.yml:353`; `scripts/run-single-test.sh:76-83`; `workloads/vllm/hma-lm-eval.sh:1-48` |
| F5b | SWA + full, same head dim (256) | `unsloth/gemma-3-270m-it` | `hma_swa_correctness` (XPU only) | 1 XPU | chunk 64 = block 64, `SEPARATE_OBJECT_GROUPS=1`, max_logprobs 100 | `xpu/multiprocess/pipeline.yml:171-200` |
| F6 | Hybrid Mamba/GDN + full attn | `Qwen/Qwen3.5-0.8B` | `hma_lm_eval_qwen3_5` (XPU; selectable on CUDA via run-single-test, not in CUDA pipeline) | 1 | chunk 544 (CUDA) / 576 (XPU), `--mamba-cache-mode align`, `--max-num-batched-tokens 544`, `BATCH_INVARIANT=0` | `scripts/run-single-test.sh:84-101`; `xpu/multiprocess/pipeline.yml:101-133` |
| F7 | MLA + fp8_e4m3 KV (legacy, non-MP) | `DeepSeek-V2-Lite-Chat` dummy, TP2 | `.buildkite/configs/local_cpu_mla.yaml` (old comprehensive suite, not MP) | 2 | `--load-format dummy --kv-cache-dtype fp8_e4m3 --quantization fp8 --block-size 64` | `.buildkite/configs/local_cpu_mla.yaml:12-27` |

Other dummy-weight precedents in MP CI: `mp_autostart_tp2` (`workloads/vllm/mp-autostart-tp2.sh:81-93`, default model, dummy, TP2),
DSV4 vLLM health probe (`workloads/vllm/dsv4-flash-tp.sh:148-167`, full DSV4 with dummy weights at TP4).

---

## 2. Does LMCache treat layers uniformly? (Can we cut layers safely?)

| Question | Answer | Evidence |
|---|---|---|
| How are layers grouped for transfer? | By **physical identity** `(kv_size, num_heads, head_size, block_size, engine_group_idx, dtype, engine_kv_format, block_stride_elems)`. Layer **count** is not part of the identity. | `lmcache/v1/kv_layer_groups.py:60-80` (`KernelGroupIdentity`, `group_layers_by_identity`); `docs/design/integration/vllm/hybrid-kv-cache-groups.md` "Registration" |
| So fewer layers = same code path? | **Yes, if every layer identity is still present at least once.** Kernel groups, object groups and chunk math are per identity; layers inside a group are a pointer list. | `lmcache/v1/platform/devices/cpu/cache_context.py:93-162` (same pattern on CUDA) |
| Hybrid rule | Keep **≥1 layer of each type** (SWA + full; KDA + MLA; GDN + full; DSV4 SWA + C4 + C128). Also keep the **same per-layer dims**: vLLM pads attention block size to match mamba page size (why Kimi uses block 944, Qwen3.5 uses 544). Changing head dims changes this geometry. | `workloads/vllm/kimi-linear-tp.sh:52-55`; `scripts/run-single-test.sh:88-95` |
| vLLM group count | vLLM HMA builds `kv_cache_groups` from per-type layer counts. 5 SWA + 1 full gives the same "N sliding groups + 1 full group" shape as 50+10 (group size 1 instead of 10). Group **count** changes, group **kinds** do not. | vLLM HMA behavior — **verify** on first run by grepping `groups=` in vLLM log (`hma_bit_correctness.py:146-153` already asserts `groups >= 2`) |
| TP-specific paths | `mla_only()` decides "store once on rank 0, share with all ranks". It is true for pure MLA, false for hybrid. **TP=1 never exercises the cross-rank share / shard logic.** | `lmcache/integration/vllm/utils.py:254-283`; `workloads/vllm/kimi-linear-tp.sh:5-14` |
| Cross-layer KV sharing (gemma-4 E2B/E4B `num_kv_shared_layers`) | Separate path (`EXCLUDED_ENGINE_GROUP`). Only E-series gemma-4 has it; 31B / 26B-A4B have `num_kv_shared_layers: 0`. | `hybrid-kv-cache-groups.md` "Cross-layer KV sharing"; HF configs |
| Scratch groups (prefix_cacheable=False) | Skipped by registration. Not in current MP CI models. | `lmcache/integration/vllm/kv_cache_groups.py:35` |

---

## 3. Small-model set (one per family)

### 3a. Smallest public model + dummy config

| Family | (a) Smallest public model, same layout | Same per-layer KV as prod? | (b) Recommended `--load-format dummy` + `--hf-overrides` (keeps per-layer KV shape + dtype) | Source of config facts |
|---|---|---|---|---|
| F1 GQA | `Qwen/Qwen3-0.6B` (28 L, 8 KV heads, head_dim 128, bf16) — **real weights**, 1.2 GB | **Yes** (8 x 128 bf16, same as Qwen3-14B) | Not needed (real weights are cheap and keep greedy/lm_eval meaningful). Exact-shape alt: `Qwen/Qwen3-14B` + `{"num_hidden_layers":4}` dummy | HF `Qwen/Qwen3-14B`, `Qwen/Qwen3-0.6B` config.json |
| F2 MLA | `deepseek-ai/DeepSeek-V2-Lite-Chat` (15.7B, 27 L) | n/a (this is the model) | `{"num_hidden_layers":2,"n_routed_experts":4,"first_k_dense_replace":0,"num_experts_per_tok":2}` — **already used in GHA CPU** | `.github/workflows/cpu_device.yml:126-129`; HF config: kv_lora_rank 512, qk_rope 64 |
| F3 sparse-MLA+fp8 | No smaller public DSV4 model found (UNKNOWN; search HF for `deepseek_v4` model_type) → use `deepseek-ai/DeepSeek-V4-Flash` config | Yes | `{"num_hidden_layers":4,"num_nextn_predict_layers":0,"compress_ratios":[0,0,4,128]}` + `--kv-cache-dtype fp8_ds_mla --tokenizer-mode deepseek_v4 --enable-expert-parallel`, `KV_CACHE_MEMORY_BYTES=536870912`, chunk 256 — **already used on XPU**. Optional: `n_routed_experts:16` to fit 24 GB — UNKNOWN if hash-routing layers (`num_hash_layers:3`) accept it; try once. | `xpu/multiprocess/pipeline.yml:222-247`; HF config: 43 L, 256 experts fp4, compress_ratios pattern `[0,0,4,128,4,128,...,4,0]` |
| F4 hybrid MLA+KDA | `yujiepan/kimi-linear-tiny-random` (5 L, hidden 8) — **changes KDA dims** (8 heads x 32 vs prod 32 x 128); MLA latent kept (512+64) | **No** for KDA state | Prefer prod config + dummy: `{"num_hidden_layers":4,"num_experts":16,"linear_attn_config":{"full_attn_layers":[4],"kda_layers":[1,2,3],"head_dim":128,"num_heads":32,"short_conv_kernel_size":4}}` — keeps 944 block geometry and TP sharding of 32 KDA heads. Keep tiny-random as a fallback (proven on XPU, chunk/block 128). | HF configs; `xpu/multiprocess/pipeline.yml:135-169` |
| F5 SWA, mixed head dim, K=V | No smaller model with **exact** 31B layout. Closest: `google/gemma-4-26B-A4B-it` (same k_eq_v, 256/512 dims, but 8/2 KV heads vs 16/4; MoE). E2B/E4B: different (k_eq_v false, shared-KV layers). | 31B dummy: Yes | `google/gemma-4-31B-it` + `{"text_config":{"num_hidden_layers":6,"layer_types":["sliding_attention","sliding_attention","sliding_attention","sliding_attention","sliding_attention","full_attention"]}}`, `ATTENTION_BACKEND=auto`. Nested `text_config` override — **verify** vLLM applies it to the sub-config. | HF configs gemma-4-31B-it / 26B-A4B / E2B / E4B |
| F5b SWA same head dim | `unsloth/gemma-3-270m-it` (18 L, real weights 0.5 GB) | n/a | None needed — **already used on XPU** with real weights | `xpu/multiprocess/pipeline.yml:171-200` |
| F6 GDN hybrid | `Qwen/Qwen3.5-0.8B` (24 L, real weights) | n/a | None needed. Optional dummy: `{"num_hidden_layers":4,"layer_types":["linear_attention","linear_attention","linear_attention","full_attention"]}` | `scripts/run-single-test.sh:84-101`; HF config |
| F7 MLA+fp8_e4m3 | `DeepSeek-V2-Lite-Chat` | — | F2 overrides + `--kv-cache-dtype fp8_e4m3` (no `--quantization fp8` needed with dummy) | `.buildkite/configs/local_cpu_mla.yaml` |

### 3b. Cost, fit and validity

GPU estimate = weights only at reduced layers (bf16 unless noted) + KV pool you set. "Load time" is a guess (UNKNOWN until measured: read `wait_for_server` timing in the job log).

| Family / profile | GPU weights est. | 1x80 GB? | 1x24 GB? | Arch limit | CPU (vLLM CPU backend)? | byte-identical KV round trip | lm_eval score | TTFT perf |
|---|---|---|---|---|---|---|---|---|
| F1 `qwen3_0_6b` (real) | ~1.2 GB | Yes | Yes | any | Yes (Qwen3 family on vLLM CPU list) | **Valid** | Valid but different threshold than 14B (needs own `lm_eval_score_min`) | Partial: ratio LMCache vs no-cache is meaningful but compute is tiny, so TTFT gain is smaller than 14B; needs own threshold |
| F2 `mla_dsv2lite_dummy` (2 L, 4 exp) | ~1 GB (embed 0.8 GB) | Yes | Yes | any CUDA | **Yes, already in GHA** (vLLM CPU MLA backend, per `cpu_device.yml:110-117`) | **Valid** | No | Partial (transfer cost real, compute fake) |
| F3 `dsv4_flash_dummy_4l` | ~16 GB (4 x ~3.2 GB fp4 experts + 2.1 GB embed/head) + 0.5 GB KV | Yes | **Tight / likely no** (and most 24 GB cards are SM89 → no DeepGEMM) | SM90 / SM100 / SM120 only | **No** (fp8_ds_mla + DeepGEMM are CUDA-only; not on vLLM CPU list) | **Valid** (XPU precedent uses dummy + DeterministicWorker) | No | No (fp8 kernel time differs from TP4 sharded run) |
| F4 `kimi_linear_dummy_4l` TP2 | ~3 GB total (embed+head 1.5 GB, 16 experts) | Yes (also TP1) | Yes | any CUDA with triton | **No** (KDA/mamba not on vLLM CPU list — UNKNOWN, check `vllm/platforms/cpu.py` for mamba support) | **Valid** | No | No |
| F4 alt `kimi_linear_tiny_random` | < 1 GB (embed 163840 x 8) | Yes | Yes | any | No (same as above) | Valid, but KDA shape ≠ prod | No | No |
| F5 `gemma4_31b_dummy_6l` | ~10 GB (6 x ~1 GB + 2.8 GB embed + ~1 GB vision) | Yes | Yes (tight with KV; set `KV_CACHE_MEMORY_BYTES`) | any (TRITON_ATTN) | gemma-4 E2B/E4B/26B-A4B are on vLLM CPU list; 31B not listed. LMCache CPU multi-group: UNKNOWN (design doc says non-GPU path rejects multi-group, but `cpu/cache_context.py:93-162` builds per-group pointers → run once to confirm) | **Valid** | No | No |
| F5b `gemma3_270m` (real) | ~0.5 GB | Yes | Yes | any | gemma-3 4b/12b on CPU list (270m likely OK, UNKNOWN) | **Valid** | Valid (weak model) | Partial |
| F6 `qwen3_5_0_8b` (real) | ~1.6 GB | Yes | Yes | any | UNKNOWN (GDN not on CPU list) | Valid only within tolerance (no batch-invariant GDN, `run-single-test.sh:96-100`) — use logprob compare at same prefix | Valid (with tolerance) | Partial |

Dummy-weight caveats:
- Greedy text from random weights can be **flat** (repeated token). A text `cmp` can then pass even if KV is wrong. Use
  `hma_bit_correctness.py` (token IDs + top-100 logprobs, GPU-APC reference, asserts LMCache hit tokens > 0).
- Cold prefill vs cached prefill can differ in BF16 (`hma_bit_correctness.py:2-11`). That is why the reference is the APC run, not the cold run.
- DSV4 on XPU needed `DeterministicWorker` (`hma_bit_correctness.py:31-40`). On CUDA: UNKNOWN if needed; keep it on.

---

## 4. FP32 / CPU path limits

| Topic | Limit | Source |
|---|---|---|
| dtypes | x86/Arm: FP32, FP16, BF16. macOS: FP32 + FP16 only. FP16 is "unstable" on torch CPU → use BF16 on Linux, FP32 on macOS. | https://docs.vllm.ai/en/latest/getting_started/installation/cpu.html |
| Validated archs | Dense Llama/Qwen2/Qwen3/Qwen3-MoE/Gemma/Gemma3/Gemma4 (E2B, E4B, 26B-A4B)/GLM-4/Phi/Mistral/gpt-oss, some VLMs. **No** DeepSeek-V2/V3/V4, Kimi-Linear, Qwen3.5/GDN, Mamba entries. | https://docs.vllm.ai/en/latest/models/hardware_supported_models/cpu.html |
| MLA on CPU | Works for DeepSeek-V2-Lite via CPU MLA backend (vllm#49453), as LMCache GHA already runs it. Not on the official list → may break on vLLM bumps. | `.github/workflows/cpu_device.yml:110-117` |
| fp8 | No fp8 KV dtype documented for CPU; `fp8_ds_mla` and DeepGEMM fp8/fp4 GEMMs are CUDA-only. **Sparse-MLA+fp8 cannot run on CPU.** | CPU install doc (no fp8 KV section); `workloads/vllm/dsv4-flash-tp.sh:16-24` |
| Quantization | AWQ / GPTQ / INT8 W8A8 only. | CPU install doc |
| Hybrid on LMCache CPU path | Design doc: "HMA on the non-GPU transfer path (it rejects multi-group)". Code: CPU cache context builds per-group buffers. **Conflict → UNKNOWN**. Run F5 gemma-4 E2B dummy on CPU once to find out. | `docs/design/integration/vllm/hybrid-kv-cache-groups.md` (Goals / Store) vs `lmcache/v1/platform/devices/cpu/cache_context.py:93-162` |
| Speed | 8-CPU pod: opt-125m job budget 30 min (`pipeline.yml:458`). A 2-layer DSV2-Lite already runs in GHA within 120 min job timeout. | `pipeline.yml:431-478`; `cpu_device.yml:89` |

Conclusion: CPU can cover **F1, F2 (MLA), maybe F5 (gemma-4 E2B)**. F3, F4, F6 need a GPU.

---

## 5. Proposed PR-tier `layout_smoke` matrix

All 1-GPU unless noted. Engine: vLLM first (adapter already has `VLLM_LOAD_FORMAT`, `VLLM_HF_OVERRIDES`, `VLLM_KV_CACHE_DTYPE`,
`VLLM_TOKENIZER_MODE`, `VLLM_WORKER_EXTENSION_CLS`, `KV_CACHE_MEMORY_BYTES` knobs: `scripts/engines/vllm.sh:103-136`).
SGLang adapter has **no** dummy / override knobs today (`scripts/engines/sglang.sh`: no `load-format` match) → add
`SGLANG_LOAD_FORMAT` + `--json-model-override-args` before SGLang can join (follow-up, not E2).

| Step (proposed) | Profile | GPUs | Checker | Transfer mode / transport | Replaces on PR tier | Est. GPU-min (UNKNOWN, measure) |
|---|---|---|---|---|---|---|
| `layout_smoke / gqa` | `qwen3_0_6b` | 1 | `hma_bit_correctness`-style 3-stage (or `l1-round-trip`) | engine_driven shm | — (new; cheap guard for GQA layout) | ~5 |
| `layout_smoke / mla` | `mla_dsv2lite_dummy` | 1 | 3-stage logprob | engine_driven shm + lmcache_driven | new (CUDA has no MLA byte check today) | ~5 |
| `layout_smoke / dsv4` | `dsv4_flash_dummy_4l` | 1 (SM90+) | `hma_dsv4_correctness` (exists) | engine_driven shm, zmq | `dsv4_flash_tp` (4 GPU x ~90 min budget) | ~15 |
| `layout_smoke / kimi_tp2` | `kimi_linear_dummy_4l` | **2** | `hma_kda_mla_correctness` (exists) with TP=2 | lmcache_driven (current kimi test) | `kimi_linear_tp` (2 GPU x ~60 min budget) | ~2 x 8 |
| `layout_smoke / swa_mixed` | `gemma4_31b_dummy_6l` | 1 | `hma_swa_correctness` (exists) | engine_driven shm | re-enables the disabled `hma_lm_eval_gemma4` layout coverage | ~8 |
| `layout_smoke / swa` | `gemma3_270m` | 1 | `hma_swa_correctness` (exists) | engine_driven inline + shm | new on CUDA (XPU has it) | ~4 |
| `layout_smoke / gdn` | `qwen3_5_0_8b` | 1 | 3-stage logprob (tolerance) | engine_driven shm | new on CUDA (XPU has lm_eval_gdn) | ~5 |
| `cpu_e2e_validation / mla` (E3) | `mla_dsv2lite_dummy` on Buildkite CPU pod | 0 | existing CPU e2e | shm / inline / server_copy | — (GHA already has it; E3 = add to Buildkite CPU matrix, or skip as duplicate) | 0 GPU |

Gate: run all of these in shadow (`soft_fail: true`) for ≥ 20 PRs (03_APPROACH rollout step 1–2) before moving the heavy jobs.

Trigger rule: `layout_smoke` runs on every `core` / `kv_layout` PR (cheap). Full TP jobs run on nightly + PRs whose
`change_class == kv_layout` **and** touch the matching path (see table below).

---

## 6. What moves to nightly and what we lose

| Full-TP test now on PR | Move to | Light stand-in on PR | Coverage loss (what only the full job catches) | Mitigation |
|---|---|---|---|---|
| `dsv4_flash_tp` vLLM, TP4 | nightly + `kv_layout` PRs touching slot-compression / hybrid-group / MLA code | `layout_smoke/dsv4` TP1 | (1) TP>1 MLA "store once on rank 0" share path (`mla_only`); (2) expert-parallel across ranks; (3) TP4 NCCL / custom all-reduce issues; (4) real fp8 weight numerics + real-weight vLLM probe; (5) 160 GB load / timeout behavior; (6) all 43 layers (only kinds, not counts, are covered) | Add a TP2 variant of `layout_smoke/dsv4` (2 GPU, 4 layers) if (1) regresses; plain-MLA TP2 already exercised by `deadlock` (no byte check) |
| `dsv4_flash_tp` SGLang, TP4 | nightly | none until SGLang adapter gets dummy knobs | SGLang composite FULL+SWA pool path for DSV4 — **full loss on PR** | Follow-up: SGLang dummy + `--json-model-override-args`; UNKNOWN if SGLang DSV4 accepts truncated `compress_ratios` |
| `kimi_linear_tp` vLLM, TP2 | nightly + `kv_layout` PRs touching `utils.py::mla_only`, kv_cache_group_edits, mamba code | `layout_smoke/kimi_tp2` (still TP2, 4 layers) | Small: real weights (greedy on real model), MoE with 256 experts, 27-layer group layout. Cross-rank shard bug **still covered** because TP2 kept. | — |
| `kimi_linear_tp` SGLang, TP2 | nightly | none (adapter gap) | SGLang mamba radix extra_buffer + page 64 path — full loss on PR | Same SGLang follow-up |
| `hma_lm_eval_gemma4` (already disabled) | stays nightly (real weights, lm_eval) | `layout_smoke/swa_mixed` | lm_eval accuracy on gemma-4 (dummy can't check accuracy) | — (net gain: layout coverage returns on PR) |

Expected saving per full PR build (estimate): `dsv4_flash_tp` 2 jobs x 4 GPU + `kimi_linear_tp` 2 jobs x 2 GPU leave the PR tier
(12 GPU-slots of the heaviest, longest jobs), replaced by ~6 x 1-GPU + 1 x 2-GPU short jobs. Measure real GPU-minutes in R1 data.

---

## 7. Open items / UNKNOWN

| Item | How to find out |
|---|---|
| Does vLLM apply nested `{"text_config":{...}}` hf-overrides for Gemma4ForConditionalGeneration? | Run gemma4 dummy once; check log for `num_hidden_layers=6` / number of attention layers registered |
| Does DSV4 dummy accept `n_routed_experts:16` (hash-routing layers)? | One local run with the override; if load fails, keep 256 |
| Is `DeterministicWorker` needed on CUDA for DSV4 fp8 compressor? | Run `hma_dsv4_correctness` 10x on CUDA with and without it |
| LMCache CPU path with multi-group (gemma-4 E2B dummy)? | Run `run-cpu-e2e-validation.sh` with `VLLM_MODEL_ID=google/gemma-4-E2B-it VLLM_LOAD_FORMAT=dummy` |
| vLLM CPU support for Mamba/KDA/GDN | Check `vllm/platforms/cpu.py` / `vllm/v1/attention/backends/cpu*` at the pinned vLLM version |
| Smaller public DSV4-family model | Search HF `model_type: deepseek_v4`; ask DeepSeek / vLLM test fixtures (`tests/models/registry.py`) |
| Real load/run minutes per profile | Shadow-run each step; read Buildkite job durations |
