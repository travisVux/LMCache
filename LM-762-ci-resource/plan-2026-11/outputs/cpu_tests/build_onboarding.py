"""Inject the lean, zero-duplication Newbie Onboarding Guide (#gates/guide: 0a–0b) into 06_PR_TO_CI_VISUAL.html.

Covers the Master Specification without duplicating existing tables (#gJobs, #fm, #ffg, #obsTrendBody):
  0a · LMCache Mental Model & 28-Area Architecture Jump Map (Prompt Lifecycle + 4-Tier Storage + 5 Core Concepts + 7-Layer Quick Jump to #fm)
  0b · 5-Min CI Quickstart, Local CPU Runbook & Zero-Cost Data Pipeline (Merge vs Release Gates + Copyable CLI + Local Troubleshooting + 90-Day Sync)
"""
import re

from pathlib import Path as _Path  # noqa: E402
# the page sits in Plan/2026-11/, two levels above outputs/cpu_tests/
PAGE = str(_Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")

HTML = r"""
<!-- ONBOARD:HTML:START -->
<section class="card" data-view="gates" data-tab="guide">
  <div class="head"><h2>0a · LMCache Mental Model &amp; 28-Area Architecture Map</h2>
  <p class="sub">Technical essence in 2 minutes: how LMCache turns 3–5 s LLM prefill into millisecond KV cache hits, and where all 28 feature areas live.</p></div>
  <div id="obMental"></div>
</section>
<section class="card" data-view="gates" data-tab="guide">
  <div class="head"><h2>0b · 5-Min CI Quickstart, Local CPU Runbook &amp; Zero-Cost Sync</h2>
  <p class="sub">Merge vs Release gates at a glance, copyable laptop pytest commands (no GPU needed), and the 90-day incremental sync pipeline.</p></div>
  <div id="obRunbook"></div>
</section>
<!-- ONBOARD:HTML:END -->
"""

CSS = r"""
/* ONBOARD:CSS:START */
.ob-hero{border:1px solid var(--border);border-left:5px solid var(--series-1);border-radius:12px;padding:12px 16px;background:color-mix(in oklab,var(--series-1) 6%,var(--surface-1));margin-bottom:14px;font-size:13px;line-height:1.5}
.ob-hero b{color:var(--text-primary)}
.ob-subh{margin:16px 0 8px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--text-secondary);display:flex;align-items:center;gap:8px}
.ob-flow{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:14px}
@media (max-width:980px){.ob-flow{grid-template-columns:1fr 1fr}}
.ob-step{border:1px solid var(--border);border-top:3px solid var(--series-1);border-radius:10px;padding:10px 12px;background:var(--surface-1);display:flex;flex-direction:column;gap:4px}
.ob-step .sn{font:700 11px ui-monospace,Consolas,monospace;color:var(--series-1);text-transform:uppercase}
.ob-step h4{margin:0;font-size:13px;color:var(--text-primary)}
.ob-step p{margin:0;font-size:12px;color:var(--text-secondary);line-height:1.42}
.ob-grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}
@media (max-width:980px){.ob-grid4{grid-template-columns:1fr 1fr}}
.ob-tier{border:1px solid var(--border);border-radius:10px;padding:10px 12px;background:var(--surface-1);display:flex;flex-direction:column;gap:4px}
.ob-tier .hd{display:flex;justify-content:space-between;align-items:center;gap:6px}
.ob-tier h4{margin:0;font-size:13px;color:var(--text-primary)}
.ob-tier .lat{font:650 10.5px ui-monospace,Consolas,monospace;padding:1px 7px;border-radius:999px;background:var(--surface-2);color:var(--text-secondary)}
.ob-tier p{margin:0;font-size:12px;color:var(--text-secondary);line-height:1.42}
.ob-pillars{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin-bottom:14px}
.ob-pil{border:1px solid var(--border);border-radius:10px;padding:9px 11px;background:var(--surface-1);font-size:12px;line-height:1.42;color:var(--text-secondary)}
.ob-pil b{display:block;font-size:12.5px;color:var(--text-primary);margin-bottom:2px}
.ob-achips{display:flex;flex-wrap:wrap;gap:6px}
.ob-achip{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:7px;border:1px solid var(--border);background:var(--surface-1);font-size:12px;color:var(--text-primary);transition:border-color .12s,background .12s}
.ob-achip:hover{border-color:var(--series-1);background:var(--surface-2)}
.ob-achip small{color:var(--text-muted);font-variant-numeric:tabular-nums;font-size:11px}
.ob-gates{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
@media (max-width:980px){.ob-gates{grid-template-columns:1fr}}
.ob-gbox{border:1px solid var(--border);border-radius:10px;padding:12px 14px;background:var(--surface-1);font-size:12.5px;line-height:1.45;color:var(--text-secondary)}
.ob-gbox.merge{border-top:4px solid var(--critical)}
.ob-gbox.rel{border-top:4px solid var(--series-1)}
.ob-gbox h3{margin:0 0 6px;font-size:14px;color:var(--text-primary);display:flex;align-items:center;justify-content:space-between}
.ob-gbox b{color:var(--text-primary)}
.ob-cmd-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px;margin-bottom:14px}
.ob-cmd{border:1px solid var(--border);border-radius:10px;padding:9px 11px;background:var(--surface-1);display:flex;flex-direction:column;gap:5px}
.ob-cmd .hd{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:12px;font-weight:650;color:var(--text-primary)}
.ob-cmd pre{margin:0;padding:7px 9px;border-radius:7px;background:var(--surface-2);border:1px solid var(--border);font:11.5px ui-monospace,Consolas,monospace;overflow-x:auto;color:var(--text-primary)}
.ob-cmd .cp{all:unset;cursor:pointer;font-size:11px;font-weight:600;padding:2px 8px;border-radius:6px;border:1px solid var(--border);background:var(--surface-0);color:var(--text-secondary)}
.ob-cmd .cp:hover{border-color:var(--series-1);color:var(--series-1)}
.ob-pipe{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:8px}
@media (max-width:980px){.ob-pipe{grid-template-columns:1fr}}
.ob-pcard{border:1px solid var(--border);border-top:3px solid var(--series-2);border-radius:10px;padding:10px 12px;background:var(--surface-1);font-size:12px;line-height:1.42;color:var(--text-secondary)}
.ob-pcard h4{margin:0 0 4px;font-size:13px;color:var(--text-primary)}
/* ONBOARD:CSS:END */
"""

JS = r"""
<!-- ONBOARD:JS:START -->
<script>
(function(){
  const CD=JSON.parse(document.getElementById('cpuData').textContent);
  const $=s=>document.querySelector(s);
  const el=(t,a={},...kids)=>{const e=document.createElement(t);for(const[k,v]of Object.entries(a)){if(v==null)continue;if(k==='class')e.className=v;else if(k==='style')e.style.cssText=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else e.setAttribute(k,v);}
    kids.flat().forEach(c=>{if(c==null||c===false)return;e.append(c.nodeType?c:document.createTextNode(String(c)));});return e;};
  const V=()=>(window.I18N&&I18N.lang==='vi')?1:0, T=(en,vi)=>V()?vi:en;
  const fmt=n=>Number(n).toLocaleString('en-US');
  const trStr=s=>(window.I18N?I18N.t(s):s);

  const AC={},GN={};{let gi=0,ii=0,last=null;CD.areas.forEach(a=>{if(a.group!==last){last=a.group;gi++;ii=0;GN[a.group]=gi;}AC[a.id]=gi+'.'+(++ii);});}

  function jumpArea(aid){
    if(window.vizNav)vizNav.show('cpu','tiers',false);
    setTimeout(()=>{
      const row=document.querySelector(`#fm tr.ar[data-area="${aid}"]`);
      if(!row)return;
      if(row.getAttribute('aria-expanded')!=='true')row.click();
      row.scrollIntoView({behavior:'smooth',block:'center'});
    },60);
  }

  function rMental(){
    const w=$('#obMental');if(!w)return;w.replaceChildren();
    w.append(el('div',{class:'ob-hero'},
      el('b',{},T('Core Concept — LMCache is the "Redis / CDN" for LLM KV-Cache Tensors (vLLM, SGLang, TensorRT-LLM): ',
                  'Bản chất kỹ thuật — LMCache là "Redis / CDN" cho bộ nhớ đệm KV Tensor của LLM (vLLM, SGLang, TensorRT-LLM): ')),
      T('It stores the KV cache of long prompts in CPU RAM (L1) or disk / cloud (L2) and streams it back to the GPU, so time-to-first-token drops from seconds to milliseconds.',
        'Nó lưu KV cache của prompt dài vào RAM CPU (L1) hoặc ổ đĩa / cloud (L2) rồi nạp lại vào GPU, nên thời gian tới token đầu giảm từ vài giây xuống vài mili-giây.')
    ));

    w.append(el('div',{class:'ob-subh'},T('1 · The 5-Step Prompt Lifecycle','1 · Vòng đời 5 bước của một Prompt')));
    const flow=el('div',{class:'ob-flow'});
    [
      [T('Step 1 · Lookup','Bước 1 · Tra cứu'),T('1 · Lookup (Chunk & Hash)','1 · Lookup (Cắt chunk & Băm)'),
       T('Splits the prompt into fixed 256-token Chunks → computes rolling hash (SHA256 / Blake3) into a unique Cache Key → queries the storage index.',
         'Cắt prompt thành các Chunk (256 tokens) → băm cuộn (SHA256 / Blake3) thành Cache Key duy nhất → hỏi danh bạ xem kho đã có chưa.')],
      [T('Step 2 · Hit / Miss','Bước 2 · Trúng / Trượt'),T('2 · Hit / Miss (Retrieve)','2 · Hit / Miss (Nạp thẳng VRAM)'),
       T('Hit → calls Retrieve to stream KV tensors into GPU VRAM via Zero-copy Shm (skips GPU prefill!). Miss → GPU computes normally.',
         'Hit → gọi Retrieve bắn thẳng KV tensor vào VRAM GPU qua Zero-copy Shm (bỏ qua tính toán GPU!). Miss → GPU tự tính bình thường.')],
      [T('Step 3 · Store','Bước 3 · Lưu đệm'),T('3 · Store (Offload KV)','3 · Store (Xả đệm KV)'),
       T('After prefill/decode finishes, the GPU worker calls Store to offload newly generated KV tensors into LMCache for future requests.',
         'Sau khi tính xong, GPU worker gọi lệnh Store xả KV tensor mới sinh vào LMCache để các request sau tái sử dụng.')],
      [T('Step 4 · Prefetch','Bước 4 · Nạp trước'),T('4 · Prefetch (Pre-warm)','4 · Prefetch (Kéo trước vào RAM)'),
       T('Asynchronously pulls candidate KV chunks from L2 disk/network into fast L1 Host DRAM before GPU inference begins.',
         'Kéo trước các chunk KV tiềm năng từ ổ cứng/mạng (L2) lên RAM máy chủ (L1) trước khi GPU bắt đầu suy luận.')],
      [T('Step 5 · Eviction','Bước 5 · Dọn dẹp'),T('5 · Eviction (LRU / ARC)','5 · Eviction (Thu hồi bộ nhớ)'),
       T('Automatically evicts cold/old KV chunks using LRU or ARC policies when L1/L2 memory reaches its capacity quota.',
         'Tự động dọn dẹp các chunk cũ, ít dùng theo thuật toán LRU / ARC khi bộ nhớ chạm ngưỡng giới hạn (Quota).')]
    ].forEach(([sn,t,d])=>flow.append(el('div',{class:'ob-step'},el('span',{class:'sn'},sn),el('h4',{},t),el('p',{},d))));
    w.append(flow);

    w.append(el('div',{class:'ob-subh'},T('2 · 4-Tier Storage & Transfer Hierarchy','2 · Phân tầng Lưu trữ & Truyền tải (4 Tầng)')));
    const g4=el('div',{class:'ob-grid4'});
    [
      [T('⚡ L1 (Host DRAM)','⚡ L1 (RAM Máy chủ)'),T('µs latency · Hot tier','Độ trễ µs · Tầng nóng'),'#10b981',
       T('Ultra-fast in-memory cache on CPU RAM / CXL / Device-DAX. Managed with pinned memory, ref-count locks, and LRU/ARC eviction.',
         'Tầng nhớ nóng siêu tốc nằm ngay trên RAM CPU / CXL / Device-DAX. Quản lý bằng bộ nhớ ghim (pinned), khoá ref-count và thu hồi LRU/ARC.')],
      [T('💾 L2 (Persistent)','💾 L2 (Lưu trữ bền vững)'),T('ms latency · Multi-node','Độ trễ ms · Đa cụm node'),'#3b82f6',
       T('Durable storage tier across Local NVMe SSD (O_DIRECT), AWS S3, MinIO, Valkey/Redis, Bigtable, Mooncake, NIXL, and HF3FS.',
         'Tầng lưu trữ bền vững trên NVMe SSD cục bộ (O_DIRECT), S3, MinIO, Valkey/Redis, Bigtable, Mooncake, NIXL và HF3FS để chia sẻ đa node.')],
      [T('🔗 P2P Transfer','🔗 Truyền ngang hàng P2P'),T('Direct GPU ↔ GPU','Truyền trực tiếp GPU ↔ GPU'),'#8b5cf6',
       T('Peer-to-peer KV streaming directly between GPU worker nodes over the network without bottlenecking central storage.',
         'Các GPU node tự truyền trực tiếp KV cache cho nhau qua mạng ngang hàng, không làm nghẽn máy chủ lưu trữ trung tâm.')],
      [T('🚀 GDS (Direct DMA)','🚀 GDS (Đọc/ghi DMA)'),T('NVMe ↔ GPU VRAM','Đọc/ghi thẳng NVMe ↔ VRAM'),'#f59e0b',
       T('GPU Direct Storage (cuFile / hipFile / muFile / uGDS) streams KV between NVMe disks and GPU VRAM via DMA, bypassing CPU RAM.',
         'GPU Direct Storage (cuFile / hipFile / muFile / uGDS) đọc/ghi thẳng từ ổ NVMe vào VRAM GPU qua đường DMA, bỏ qua nghẽn CPU RAM.')]
    ].forEach(([name,lat,col,desc])=>g4.append(el('div',{class:'ob-tier',style:`border-top:3px solid ${col}`},
      el('div',{class:'hd'},el('h4',{},name),el('span',{class:'lat'},lat)),el('p',{},desc))));
    w.append(g4);

    w.append(el('div',{class:'ob-subh'},T('3 · 5 Core Codebase Concepts','3 · 5 Thuật ngữ Kiến trúc Cốt lõi trong Codebase')));
    const pil=el('div',{class:'ob-pillars'});
    [
      [T('🧩 CacheBlend (Non-Prefix Reuse)','🧩 CacheBlend (Tái sử dụng phi tiền tố)'),
       T('Reuses KV of RAG documents placed in the middle of prompts (not just prefix) by selectively recalculating RoPE positional rotations.',
         'Tái sử dụng KV của đoạn tài liệu nằm ở bất kỳ đâu giữa prompt (không chỉ ở đầu câu) bằng cách tính toán lại góc quay vị trí RoPE.')],
      [T('⏳ Lazy Offload & Token Dropping','⏳ Lazy Offload & Bỏ Token dư'),
       T('Defers KV store operations until GPU blocks are about to be evicted by vLLM; drops non-critical tokens to save memory.',
         'Hoãn ghi KV cho tới khi block trên GPU sắp bị vLLM thu hồi (evict); kết hợp loại bỏ các token dư thừa để tiết kiệm bộ nhớ.')],
      [T('📐 DeepSeek MLA & Hybrid KV Layouts','📐 Định dạng Tensor DeepSeek MLA & Mamba'),
       T('Dedicated KV layout adapters for Multi-head Latent Attention (DeepSeek V2/V3), Mamba state space, and sliding-window models.',
         'Bộ chuyển đổi cấu trúc tensor chuyên biệt cho chuẩn nén KV Multi-head Latent Attention (DeepSeek V2/V3) và kiến trúc lai Mamba.')],
      [T('🔐 Serde (Quantization & Security)','🔐 Serde (Lượng tử hoá & Mã hoá)'),
       T('Compresses KV tensors via FP8, asymmetric K16/V8, or TurboQuant and encrypts with AES-GCM before writing to L2 storage.',
         'Lượng tử hoá nén KV (FP8, K16/V8, TurboQuant) và mã hoá bảo mật AES-GCM trước khi ghi xuống tầng lưu trữ L2.')],
      [T('🔄 Dual KV Datapath','🔄 Hai đường truyền KV (LMCache vs Engine)'),
       T('LMCache-driven (default on CUDA/NPU: server reads GPU VRAM directly via IPC/SHM zero-copy) vs Engine-driven (worker copies via shm/inline).',
         'LMCache-driven (mặc định trên CUDA/NPU: server đọc thẳng VRAM qua IPC/SHM zero-copy) và Engine-driven (worker gom/chép qua shm hoặc inline).')]
    ].forEach(([k,v])=>pil.append(el('div',{class:'ob-pil'},el('b',{},k),v)));
    w.append(pil);

    w.append(el('div',{class:'ob-subh'},T('4 · 7-Layer × 28 Feature Areas Quick Jump (Click any chip → opens full row in Unit tests → 3)','4 · Bản đồ Nhảy nhanh 7 Tầng × 28 Phân khu (Click chip → mở chi tiết tại Unit test → 3)')));
    const tbl=el('table',{class:'obs-t'}),tb=el('tbody');
    tbl.append(el('thead',{},el('tr',{},
      el('th',{style:'width:220px'},T('Architectural Layer','Tầng Kiến trúc')),
      el('th',{},T('28 Feature Areas (What · Why · Main Code · Test Files in Unit tests → 3)','28 Phân khu Tính năng (Xem What · Why · Code · Test tại Unit test → 3)'))
    )),tb);
    const groups=[...new Set(CD.areas.map(a=>a.group))];
    groups.forEach(g=>{
      const chips=el('div',{class:'ob-achips'});
      CD.areas.filter(a=>a.group===g).forEach(a=>{
        const role=(CD.gloss.roles[a.id]||CD.gloss.roles.other)[V()];
        chips.append(el('button',{class:'ob-achip',type:'button',title:`${role}\nCode: ${a.code}`,onclick:()=>jumpArea(a.id)},
          el('span',{class:'no',style:'margin:0'},AC[a.id]),
          el('b',{},trStr(a.name)),
          el('small',{},`${fmt(a.passed)}`)
        ));
      });
      tb.append(el('tr',{},el('td',{style:'font-weight:650;white-space:nowrap'},el('span',{class:'no'},String(GN[g])),trStr(g)),el('td',{},chips)));
    });
    w.append(el('div',{class:'obs-scroll'},tbl));
  }

  function rRunbook(){
    const w=$('#obRunbook');if(!w)return;w.replaceChildren();
    w.append(el('div',{class:'ob-subh',style:'margin-top:0'},T('1 · Merge Gate vs Release Gate & 2 Critical Audit Findings','1 · Cổng Merge vs Cổng Release & 2 Phát hiện Kiểm toán Sống còn')));
    const gates=el('div',{class:'ob-gates'});
    gates.append(
      el('div',{class:'ob-gbox merge'},
        el('h3',{},T('🛑 Merge Gate (Buildkite GPU + GitHub)','🛑 Cổng Merge (Buildkite GPU + GitHub)'),el('span',{class:'badge req'},T('Required','Bắt buộc'))),
        el('div',{},T('Blocks every PR into dev: DCO + Check code quality (< 1m) + k3-unit-tests (1 GPU pod, 25m queue + 24m run, 10,258 tests, --maxfail=1) + k3-multiprocess-test (~35 GPU E2E jobs, 87m p50).',
                      'Chặn cứng mọi PR gộp vào dev: DCO + Check code quality (< 1p) + k3-unit-tests (1 GPU pod, chờ 25p + chạy 24p, 10,258 test, --maxfail=1) + k3-multiprocess-test (~35 job E2E GPU, 87p p50).')),
        el('div',{style:'margin-top:6px'},
          el('b',{},T('⚠️ Audit Trap #1: ','⚠️ Lỗ hổng #1: ')),
          T('8,994 of 10,258 tests on the GPU pod (87.7%) are pure CPU tests — wasting 12.5 GPU-min/PR. ',
            '8,994 / 10,258 test trên GPU pod (87.7%) là test CPU thuần — lãng phí 12.5 phút GPU/PR. '),
          el('a',{class:'xlink',onclick:()=>window.vizNav&&vizNav.show('gates','overview')},T('Gates table →','Bảng cổng →'))
        )
      ),
      el('div',{class:'ob-gbox rel'},
        el('h3',{},T('🚀 Release Gate (GitHub Actions CPU)','🚀 Cổng Release (GitHub Actions CPU)'),el('span',{class:'badge rel'},T('Blocks release','Chặn release'))),
        el('div',{},T('Blocks PyPI wheels & Docker images (publish.yml), advisory on PRs: Test py3.10–3.14 runs 9,326 CPU unit tests across 540 files (~19m × 5) and finishes ~30 min before the GPU pod starts.',
                      'Chặn phát hành PyPI wheel & Docker image (publish.yml), chỉ tham khảo ở PR: Test py3.10–3.14 chạy 9,326 test CPU trên 540 file (~19p × 5), xong trước GPU pod ~30 phút.')),
        el('div',{style:'margin-top:6px'},
          el('b',{},T('🚨 Audit Trap #2: ','🚨 Lỗ hổng #2: ')),
          T('327 critical vLLM MP connector unit tests run ONLY here because k3 GPU pod has no vLLM installed! ',
            '327 unit test cầu nối vLLM MP CHỈ chạy tại đây vì k3 GPU pod không cài vLLM (bị skip âm thầm)! '),
          el('a',{class:'xlink',onclick:()=>window.vizNav&&vizNav.show('cpu','findings')},T('10 Findings & fixes →','10 Phát hiện & cách sửa →'))
        )
      )
    );
    w.append(gates);

    w.append(el('div',{class:'ob-subh'},T('2 · Run & Debug Tests Locally on Any Laptop (No GPU Needed)','2 · Chạy & Debug Test trên Máy Cá Nhân (Không cần GPU)')));
    const cmdGrid=el('div',{class:'ob-cmd-list'});
    [
      [T('1. Run all fast CPU tests (skip CUDA & accelerators)','1. Chạy toàn bộ test CPU nhanh (bỏ qua CUDA & thiết bị tăng tốc)'),
       'pytest -m "not (cuda or musa or xpu or npu or neuron or rbln)" tests/'],
      [T('2. Run a single feature area (e.g. CacheBlend or Lazy Offload)','2. Chạy riêng một phân khu (ví dụ CacheBlend hoặc Lazy Offload)'),
       'pytest tests/v1/multiprocess/test_blend.py\npytest tests/v1/test_lazy_offload.py'],
      [T('3. Fail-fast on first error & print 10 slowest tests','3. Dừng ngay ở lỗi đầu tiên & hiện 10 test chậm nhất'),
       'pytest -m "not (cuda or musa or xpu or npu or neuron or rbln)" --maxfail=1 --durations=10 tests/'],
      [T('4. Incremental sync & verify this All-in-One HTML (< 15s)','4. Đồng bộ vi sai & kiểm định trang HTML All-in-One (< 15s)'),
       'python -I -X utf8 sync_incremental.py\npython -I -X utf8 verify_page.py']
    ].forEach(([title,code])=>{
      const btn=el('button',{class:'cp',type:'button',onclick:()=>{
        navigator.clipboard&&navigator.clipboard.writeText(code);
        btn.textContent=T('✓ Copied','✓ Đã chép');
        setTimeout(()=>{btn.textContent=T('Copy','Chép lệnh');},1500);
      }},T('Copy','Chép lệnh'));
      cmdGrid.append(el('div',{class:'ob-cmd'},el('div',{class:'hd'},el('span',{},title),btn),el('pre',{},el('code',{},code))));
    });
    w.append(cmdGrid);

    const tbl=el('table',{class:'obs-t'}),tb=el('tbody');
    tbl.append(el('thead',{},el('tr',{},
      el('th',{},T('Local Symptom / Error','Triệu chứng / Lỗi khi chạy Local')),
      el('th',{},T('Root Cause','Nguyên nhân gốc')),
      el('th',{},T('How to Fix','Cách xử lý dứt điểm'))
    )),tb);
    [
      ['ZMQError: Address already in use / Socket hang',
       T('Stale pytest or lmcache server subprocess still holding ZMQ / gRPC ports from a previous run.',
         'Tiến trình pytest hoặc lmcache server cũ bị treo vẫn đang chiếm giữ port ZMQ / gRPC.'),
       T('Kill lingering python/pytest processes holding the port; use ephemeral free ports in fixtures.',
         'Tắt các tiến trình pytest/lmcache cũ còn treo; dùng port động tự do trong fixture.')],
      ['ModuleNotFoundError: No module named \'vllm\'',
       T('327 vLLM MP connector & lazy offload tests import vLLM classes (skipped silently on k3 GPU pod).',
         '327 test cầu nối vLLM MP & lazy offload import class từ vLLM (bị skip âm thầm trên k3 GPU pod).'),
       T('Install the vLLM wheel + NO_GPU_EXT=1 pip install -e . (matches GHA test.yml setup).',
         'Cài đặt vLLM wheel kết hợp NO_GPU_EXT=1 pip install -e . theo đúng cấu hình GHA test.yml.')],
      ['HTTP 401 / Timeout in test_create_workload.py',
       T('Unit test makes 13 real HTTP requests to huggingface.co to download a tokenizer.',
         'Unit test gọi mạng thật 13 lần tới huggingface.co để tải tokenizer.'),
       T('Pass -k "not test_create_workload" when running offline, or mock AutoTokenizer in the test.',
         'Thêm cờ -k "not test_create_workload" khi chạy offline, hoặc mock AutoTokenizer trong test.')]
    ].forEach(([sym,cause,fix])=>tb.append(el('tr',{},el('td',{},el('code',{},sym)),el('td',{},cause),el('td',{},fix))));
    w.append(el('div',{class:'obs-scroll',style:'margin-bottom:14px'},tbl));

    w.append(el('div',{class:'ob-subh'},T('3 · 100% Free Automated Data Sync Pipeline (Zero Server Cost)','3 · Luồng Đồng bộ Dữ liệu Tự động 100% Miễn phí (0đ Vận hành)')));
    const pipe=el('div',{class:'ob-pipe'});
    [
      [T('1. Local run only (observe_collect.py)','1. Chỉ chạy local (observe_collect.py)'),
       T('Page data is updated only by local runs: run observe_collect.py, then build_page.py. No refresh from the browser, no CI/CD.',
         'Dữ liệu trang chỉ cập nhật bằng lần chạy local: chạy observe_collect.py rồi build_page.py. Không làm mới từ trình duyệt, không CI/CD.')],
      [T('2. Server-Side Checkpoint Sync (sync_incremental.py)','2. Đồng bộ Checkpoint Mốc thời gian (sync_incremental.py)'),
       T('Reads the "made" timestamp watermark in report_data.json and queries only the last 48h delta from GitHub API. Finishes in ~10 seconds instead of scanning full history.',
         'Đọc mốc thời gian "made" trong report_data.json và chỉ kéo dữ liệu thay đổi trong 48 giờ gần nhất từ GitHub API. Chạy xong trong ~10 giây thay vì quét lại từ đầu.')],
      [T('3. 90-Day Sliding Window Auto-Prune','3. Cửa sổ trượt 90 ngày Tự động Cắt tỉa'),
       T('Automatically prunes PR/run records older than 90 days before rebuilding 06_PR_TO_CI_VISUAL.html — guaranteeing the single-file HTML stays fixed at ~1.67 MB forever.',
         'Tự động cắt bỏ các bản ghi cũ hơn 90 ngày trước khi build lại 06_PR_TO_CI_VISUAL.html — đảm bảo file HTML đơn lẻ luôn cố định ~1.67 MB vĩnh viễn, không bao giờ phình to.')]
    ].forEach(([h,p])=>pipe.append(el('div',{class:'ob-pcard'},el('h4',{},h),el('div',{},p))));
    w.append(pipe);
  }

  function renderAll(){rMental();rRunbook();}
  addEventListener('langchange',renderAll);
  renderAll();
})();
</script>
<!-- ONBOARD:JS:END -->
"""


def put(page, start, end, block, anchor):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor)
    return page[:i] + block.strip() + "\n" + page[i:]


def main():
    page = open(PAGE, encoding="utf-8").read()
    page = put(page, "/* ONBOARD:CSS:START */", "/* ONBOARD:CSS:END */", CSS, "@media (max-width:980px)")
    page = put(page, "<!-- ONBOARD:HTML:START -->", "<!-- ONBOARD:HTML:END -->", HTML, "<!-- GATES:HTML:START -->")
    page = put(page, "<!-- ONBOARD:JS:START -->", "<!-- ONBOARD:JS:END -->", JS, "</body>")
    open(PAGE, "w", encoding="utf-8").write(page)
    print("onboard: injected #gates/guide (0a..0b)")


if __name__ == "__main__":
    main()
