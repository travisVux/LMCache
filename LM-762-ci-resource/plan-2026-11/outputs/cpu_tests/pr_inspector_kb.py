"""Phase C of the PR Inspector: the living knowledge base panel (data: ops-app/backend/kb.py -> <script id="kbData">).

In the Inspector of a PR, the button "RFC / FRS" shows the RFC of that PR and the FRS of every code area it touches:
current version (editable text), version history, open update proposals with the changed facts and a coloured diff,
and the links PR <-> feature <-> CI gate <-> bug analysis. The page is read-only (served by a read-only server), so an
edit is saved with kb.py: "Download .md" + the copied command `kb.py edit <doc> --file <file>`; proposals are
decided with `kb.py accept|reject <id>`. Nothing is overwritten silently.
"""

CSS = r"""
/* PIKB:CSS:START */
.pi-kb-docs{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px}
.pi-kb-docs button[aria-selected="true"]{border-color:var(--series-1);color:var(--text-primary);font-weight:650}
.pi-kb-meta{font-size:12px;color:var(--text-secondary);display:flex;flex-wrap:wrap;gap:4px 12px;margin:4px 0 8px}
.pi-kb-ta{width:100%;box-sizing:border-box;min-height:300px;font:12px/1.45 ui-monospace,Consolas,monospace;background:var(--surface-0,var(--surface-1));color:var(--text-primary);border:1px solid var(--border);border-radius:8px;padding:8px;resize:vertical}
.pi-kb-act{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:6px 0}
.pi-kb-cmd{font:11px ui-monospace,Consolas,monospace;background:var(--surface-2);border-radius:6px;padding:4px 6px;overflow-wrap:anywhere}
.pi-kb-diff{font:11px/1.45 ui-monospace,Consolas,monospace;background:var(--surface-2);border-radius:8px;padding:8px;max-height:340px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;margin:6px 0}
.pi-kb-diff .add{color:var(--series-3)}.pi-kb-diff .del{color:var(--critical,#c0392b)}.pi-kb-diff .hd{color:var(--text-muted)}
.pi-kb-prop{border:1px solid var(--series-2);border-radius:10px;padding:8px 10px;margin:8px 0}
.pi-kb-ch{font-size:12px;margin:2px 0;overflow-wrap:anywhere}
.pi-kb-links{display:flex;flex-wrap:wrap;gap:4px}
/* PIKB:CSS:END */
"""

JS = r"""
<!-- PIKB:JS:START -->
<script>
/* PR Inspector phase C (pr_inspector_kb.py): RFC / FRS panel from kbData (kb.py). Read-only page: edits go through kb.py. */
(function(){
  if(!window.PI) return;
  let K={};try{K=JSON.parse(document.getElementById('kbData').textContent)||{};}catch(e){K={};}
  const DOCS=K.docs||{};
  const T=(en,vi)=>(window.I18N&&I18N.lang==='vi')?vi:en;
  const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  const short=v=>{const s=typeof v==='string'?v:JSON.stringify(v);return s==null?'—':(s.length>140?s.slice(0,140)+'…':s);};
  let sel=null;
  function docsFor(n){const M=PI.model(n);const ids=['rfc:'+n,...M.areas.map(a=>'frs:'+a)];return ids.map(id=>[id,DOCS[id]]);}
  function copy(txt,btn){const done=()=>{const o=btn.textContent;btn.textContent=T('copied','đã copy');setTimeout(()=>btn.textContent=o,1400);};
    if(navigator.clipboard)navigator.clipboard.writeText(txt).then(done,()=>prompt('',txt));else prompt('',txt);}
  function diffHtml(d){return d.split('\n').map(l=>`<span class="${l.startsWith('+++')||l.startsWith('---')||l.startsWith('@@')?'hd':l.startsWith('+')?'add':l.startsWith('-')?'del':''}">${esc(l)}</span>`).join('\n');}
  function linkChip(r){const [ref,rel]=r;const k=ref.split(':')[0];
    const inner=`<span class="obsraw">${esc(ref)}</span> <span class="pi-why">${esc(rel)}</span>`;
    if(k==='pr')return `<a href="#" class="pi-chip" data-pi="${esc(ref)}">${inner}</a>`;
    if(k==='feature'||k==='bug')return `<a href="#" class="pi-chip ent-l" data-ent="${esc(ref)}" role="link">${inner}</a>`;
    return `<span class="pi-chip">${inner}</span>`;}
  function docAge(d){const v=d.versions[0]||[];const at=v[1]||'';const h=(Date.now()-Date.parse(at))/36e5;const days=isNaN(h)?'?':h<48?Math.round(h)+' h':Math.round(h/24)+' d';
    return d.proposals.length?`<span class="ux-chip stale">${T(`stale: ${d.proposals.length} update proposal(s) open, facts changed since v${d.v}`,`cũ: ${d.proposals.length} đề xuất cập nhật đang mở, fact đã đổi từ v${d.v}`)}</span>`
      :frozen(d)?`<span class="ux-chip unk">${T('frozen','đóng băng')}</span> ${T(`v${d.v} from ${String(at).slice(0,10)}: its subject is no longer in the build input (closed PR / older release), so it is not checked against new facts`,`v${d.v} ngày ${String(at).slice(0,10)}: đối tượng không còn trong đầu vào build (PR đã đóng / release cũ), nên không được so với fact mới`)}`
      :factsOld()>48?`<span class="ux-chip stale">${T('unverified','chưa kiểm chứng')}</span> ${T(`v${d.v} matches the facts built ${String(K.facts_made||'?').slice(0,10)}, but those facts come from a PR / CI snapshot ${Math.round(factsOld()/24)} d old`,`v${d.v} khớp fact build ngày ${String(K.facts_made||'?').slice(0,10)}, nhưng fact đó lấy từ snapshot PR / CI đã ${Math.round(factsOld()/24)} ngày`)}`
      :`<span class="ux-chip ok">${T('current','hiện hành')}</span> ${T(`v${d.v} from ${String(at).slice(0,10)} (${days}) matches the facts built ${String(K.facts_made||K.made||'?').slice(0,10)}`,`v${d.v} ngày ${String(at).slice(0,10)} (${days}) khớp fact build ngày ${String(K.facts_made||K.made||'?').slice(0,10)}`)}`;}
  // expert review K5: "current" only when the facts are fresh; a document whose subject left the build input is "frozen"
  function frozen(d){return !!(K.facts_made&&d.last_seen&&String(d.last_seen)<String(K.facts_made));}
  function factsOld(){const at=window.PI&&PI.data&&PI.data.snap_at;const h=(Date.now()-Date.parse(String(at||'').replace(' ','T')+(/Z$/.test(at||'')?'':'Z')))/36e5;return isNaN(h)?Infinity:h;}
  function panel(n,only){
    const list=only?[[only,DOCS[only]]]:docsFor(n);if(only)sel=only;else if(!sel||!list.some(x=>x[0]===sel))sel=(list.find(x=>x[1])||list[0])[0];
    const tabs=list.map(([id,d])=>`<button type="button" class="pi-btn" data-kb="${esc(id)}" aria-selected="${id===sel}">${esc(id.startsWith('rfc')?'RFC':'FRS · '+id.slice(4))}${d?` v${d.v}${d.proposals.length?' · '+d.proposals.length+' ⚑':''}`:' · —'}</button>`).join('');
    const d=DOCS[sel];
    let body='';
    if(!d){body=`<p><span class="pi-unk">${T('unknown','chưa biết')}</span> ${T('No document yet for','Chưa có tài liệu cho')} ${esc(sel)}. ${T('Generate it locally:','Tạo nó ở local:')}</p><div class="pi-kb-cmd">python -X utf8 kb.py build --pr ${esc(n)}</div>`;}
    else{const file=sel.replace(':','_')+'_v'+d.v+'.md';
      const save=`python -X utf8 kb.py edit ${sel} --file ${file} --reason "..."`;
      body=`<div class="pi-kb-meta"><b class="obsraw">${esc(d.title)}</b><span>v${esc(d.v)} · ${esc(d.status)}</span><span>${T('versions','phiên bản')}: ${d.versions.length}</span><span>${T('open proposals','đề xuất mở')}: ${d.proposals.length}</span><span data-ux="doc-age">${docAge(d)}</span><span>${T('store','lưu trong')} <code>ops.db · kb_doc / kb_version</code></span></div>`+
        d.proposals.map(p=>`<div class="pi-kb-prop"><b>${T('Update proposal','Đề xuất cập nhật')} #${esc(p.id)}</b> <span class="pi-why">${esc(p.trigger)} · ${T('from','từ')} v${esc(p.base)} · ${esc((p.at||'').replace('T',' ').slice(0,16))}</span>`+
          `<div>${(p.changes||[]).slice(0,8).map(c=>`<div class="pi-kb-ch obsraw">• ${esc(c.fact)}: ${esc(short(c.before))} → ${esc(short(c.after))}</div>`).join('')}</div>`+
          `<pre class="pi-kb-diff obsraw">${diffHtml(p.diff||'')}</pre><div class="pi-kb-act"><span class="pi-kb-cmd">python -X utf8 kb.py accept ${esc(p.id)}</span><button type="button" class="pi-btn" data-kbcopy="python -X utf8 kb.py accept ${esc(p.id)}">${T('Copy accept','Copy accept')}</button><button type="button" class="pi-btn" data-kbcopy="python -X utf8 kb.py reject ${esc(p.id)}">${T('Copy reject','Copy reject')}</button></div></div>`).join('')+
        `<textarea class="pi-kb-ta obsraw" id="piKbTa" spellcheck="false" aria-label="${esc(sel)}">${esc(d.body)}</textarea>`+
        `<div class="pi-kb-act"><button type="button" class="pi-btn" data-kbdl="${esc(file)}">${T('Download .md','Tải .md')}</button><button type="button" class="pi-btn" data-kbcopy="${esc(save)}">${T('Copy save command','Copy lệnh lưu')}</button><button type="button" class="pi-btn" data-kbreset>${T('Reset','Khôi phục')}</button>`+
        `<span class="pi-why">${T('The page is read-only: save the file, then run the command in ops-app/backend. It becomes a new version (author: human).','Trang chỉ đọc: lưu file rồi chạy lệnh trong ops-app/backend. Nó thành phiên bản mới (tác giả: human).')}</span></div>`+
        `<h4>${T('Links','Liên kết')}</h4><div class="pi-kb-links">${(d.links||[]).map(linkChip).join('')}</div>`+
        `<h4>${T('Versions','Phiên bản')}</h4><table class="pi-gt"><tbody>${d.versions.map(v=>`<tr><td>v${esc(v[0])}</td><td class="pi-why">${esc((v[1]||'').replace('T',' ').slice(0,16))}</td><td>${esc(v[2])}</td><td class="obsraw">${esc(v[3]||'')}</td></tr>`).join('')}</tbody></table>`;}
    if(only)return `<div class="pi-kb" data-pi-kb=""><h3 id="piTitle" class="obsraw" style="margin:0 0 6px;font-size:15px">${esc(d?d.title:only)}</h3>${body}</div>`;
    return `<div class="pi-kb" data-pi-kb="${esc(n)}"><div class="pi-kb-act"><button type="button" class="pi-btn" data-kbback>← ${T('Back to the 5 views','Quay lại 5 góc nhìn')}</button><span class="pi-why">${T('Living knowledge base: RFC of this PR, FRS of the code areas it touches. A fact change creates a proposal, never a silent overwrite.','Knowledge base sống: RFC của PR này, FRS của các code area nó chạm. Fact thay đổi thì tạo đề xuất, không ghi đè ngầm.')}</span></div>`+
      `<div class="pi-kb-docs" role="tablist">${tabs}</div>${body}</div>`;}
  function show(n){const b=document.querySelector('#piDrawer #piBody');if(b){b.innerHTML=panel(n);b.scrollTop=0;}}
  addEventListener('pirender',e=>{const d=e.detail||{};if(!d.key||!d.key.startsWith('pr:'))return;const n=d.key.slice(3);
    const bar=document.querySelector('#piDrawer .pi-bar');if(!bar||bar.querySelector('[data-kbopen]'))return;
    const cnt=docsFor(n).filter(x=>x[1]).length,props=docsFor(n).reduce((s,x)=>s+(x[1]?x[1].proposals.length:0),0);
    const b=document.createElement('button');b.type='button';b.className='pi-btn';b.dataset.kbopen=n;
    b.textContent=`RFC / FRS (${cnt}${props?' · '+props+' ⚑':''})`;bar.appendChild(b);});
  document.addEventListener('click',e=>{const dr=e.target.closest&&e.target.closest('#piDrawer');if(!dr)return;
    const o=e.target.closest('[data-kbopen]');if(o){sel=null;show(o.dataset.kbopen);return;}
    const root=e.target.closest('[data-pi-kb]');if(!root)return;const n=root.dataset.piKb;
    const t=e.target.closest('[data-kb]');if(t){sel=t.dataset.kb;show(n);return;}
    if(e.target.closest('[data-kbback]')){PI.open('pr:'+n);return;}
    const c=e.target.closest('[data-kbcopy]');if(c){copy(c.dataset.kbcopy,c);return;}
    const dl=e.target.closest('[data-kbdl]');if(dl){const ta=document.getElementById('piKbTa');const blob=new Blob([ta.value],{type:'text/markdown'});
      const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=dl.dataset.kbdl;document.body.appendChild(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},500);return;}
    if(e.target.closest('[data-kbreset]')){const ta=document.getElementById('piKbTa');if(ta&&DOCS[sel])ta.value=DOCS[sel].body;}
  });
  window.PIKB={docs:DOCS,show,docsFor,docHtml:id=>panel(null,id),docAge};
})();
</script>
<!-- PIKB:JS:END -->
"""
