"""Feature-area rules (first match wins) on test path without the 'tests/' prefix."""
import re

RULES = [
    ("blend", r"multiprocess/test_(blend_|cb_)|^v1/test_fused_rerope|mp_coordinator/test_blend|subscribers/.*/test_cb_server|quality_bench/test_blend"),
    ("p2p", r"distributed/transfer_channel/|l2_adapters/test_p2p|multiprocess/test_p2p|^skills/test_p2p"),
    ("gds", r"gds_backends/|memory_manager/test_gds|test_gds_l1_config|gpu_connector/test_gds_context"),
    ("vllm", r"^v1/test_(vllm_|mp_connector|mp_lookup_state|mp_nonblocking_lookup|mp_tracker|mp_cache_model_identity|decode_save_and_preemption|kv_cache_groups|kv_layer_groups_manager|experimental_dispatcher|mm_hash_utils|cache_identity|blocks_first_group_construction)"),
    ("engines", r"^v1/test_(unified_sglang|tensorrt|atom|trtllm)"),
    ("lifecycle", r"^v1/test_mp_server_autostart|multiprocess/test_(autostart_health|sigterm_cleanup|worker_liveness|grpc_server_shutdown|grpc_real_server|config|client_config|engine_passthroughs)\.py"),
    ("transport", r"multiprocess/test_(mq|protocols|transport_factory|grpc_|request_|client|futures|custom_types|free_locks|affinity_pool|server_module|packed_token_ids|tensor_wire|session)|multiprocess/transport/"),
    ("modules", r"multiprocess/test_(ext_server_module|module_discovery|engine_module|mp_extension_hooks|mp_runtime_plugin)|^v1/plugin/|^examples/"),
    ("datapath", r"multiprocess/test_(engine_driven|async_engine_driven|lmcache_driven|direct_transfer|transfer_ctx_guard|ipc_memory_reclaim|event_ipc_handle_path|posix_shm|compute_mp_checksums|chunk_size_negotiation|skip_first_n_tokens|batched_iteration|l1_owner_completion|unified_touch|qstore|blocked_scale|cache_server|completion_recorder|direct_copy|native_state_alias)|^v1/test_staging_buffer|^v1/test_(mp_)?mem_kernels"),
    ("lookup", r"multiprocess/test_(lookup_|apc_covered|query_lookup|key_resolver|prefetch_service|warm_prefetch|kv_load_policy|native_state_lookup|token_hasher|kv_event_subscriber)|distributed/test_prefetch"),
    ("http", r"multiprocess/http_apis/|multiprocess/test_http_|^v1/test_http_auth|^security/"),
    ("layout", r"^v1/gpu_connector/|^v1/test_(torch_ops|cuda_ops_parity)"),
    ("serde", r"distributed/serde/"),
    ("l2", r"multiprocess/test_raw_block|^v1/storage_backend/|distributed/(l2_adapters/|raw_block/)|distributed/test_.*(l2_|_l2|adapter|valkey|resp_env|raw_block|nixl|multimodel|runtime_adapters)"),
    ("l1", r"distributed/(test_l1_|test_multi_l1|test_memory_|test_devdax|memory_manager/|test_(lru|arc|isolated_lru)_eviction|test_eviction_extra)|^v1/test_(address_manager|memory_management|memory_allocator)"),
    ("smcore", r"distributed/test_(bitmap_ops|object_key|key_codec|namespace_codecs|encoded_object_key|storage_manager|storage_controller|quota_manager|write_policy|store_policy|cache_salt|distributed_storage_manager|report_status|store_controller)"),
    ("lazy", r"lazy_offload/|^v1/test_lazy_offload|^v1/test_token_drop"),
    ("coord", r"^v1/mp_coordinator/|^v1/cli/test_query_coordinator|^cli/commands/test_(coordinator|quota)"),
    ("obs", r"^v1/mp_observability/"),
    ("platform", r"^v1/platform/|^inprocess/v1/platform/|^v1/test_musa_"),
    ("native", r"^v1/lmcache_native/|^v1/test_(bloom_filter|periodic_thread|event_notifier|json_utils|subclass_discovery)|^v1/utils/|^test_utils"),
    ("orch", r"memory_orchestrator/"),
    ("ip_store", r"^inprocess/v1/storage_backend/"),
    ("ip_ctrl", r"^inprocess/(v1/(cache_controller|internal_api_server|health_monitor|lookup_client)|tools|usage_telemetry)|^inprocess/test_observability"),
    ("ip_engine", r"^inprocess/"),
    ("cli", r"^cli/|^tools/|^ci/|^benchmarks/"),
    ("frontend", r"^lmcache_frontend/|^sdk/"),
    ("build", r"^test_(build_profiles|pre_commit|banner|usage_telemetry)|usage_telemetry"),
]
_C = [(a, re.compile(r)) for a, r in RULES]


# Explicit fixes from review (REVIEW_ponytail.md §3); checked before the regex rules.
OVERRIDES = {
    "benchmarks/test_xpu_kernels_microbench.py": "platform",
    "v1/test_cache_identity.py": "smcore",
    "v1/distributed/test_storage_manager_l2_keys.py": "smcore",
    "v1/distributed/test_cache_salt_l2_eviction.py": "smcore",
    "v1/distributed/test_l1_l2_state_metrics.py": "smcore",
    "v1/distributed/test_multimodel.py": "smcore",
    "v1/distributed/test_prefetch_controller.py": "smcore",
    "v1/multiprocess/test_request_auth.py": "http",
    "v1/multiprocess/test_engine_passthroughs.py": "http",
    "v1/multiprocess/test_usage_telemetry_server.py": "lifecycle",
    "v1/test_mem_kernels.py": "layout",
    "v1/test_mp_mem_kernels.py": "layout",
    "v1/multiprocess/test_qstore.py": "modules",
    "inprocess/benchmarks/test_xpu_connector_benchmark.py": "platform",
    "inprocess/benchmarks/test_xpu_layerwise_connector_benchmark.py": "platform",
    "inprocess/benchmarks/test_musa_benchmark.py": "platform",
}


def area_of(path: str) -> str:
    p = path[6:] if path.startswith("tests/") else path
    if p in OVERRIDES:
        return OVERRIDES[p]
    for a, rx in _C:
        if rx.search(p):
            return a
    return "other"
