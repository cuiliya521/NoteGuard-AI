/* Streamlit V1 transport, based on this repository's clipboard component protocol. */
"use strict";
const paths={doc:'<path d="M14 3H5v18h14V8zM14 3v5h5M8 12h8M8 16h5"/>',note:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h4"/>',history:'<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7M12 7v5l3 2"/>',rule:'<path d="M4 6h16M4 12h16M4 18h16M8 3v6M16 9v6M9 15v6"/>',shield:'<path d="m12 3-8 3v6c0 5 8 9 8 9s8-4 8-9V6z"/><path d="m8 12 3 3 5-6"/>',lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',check:'<path d="m5 12 4 4 10-10"/>',close:'<path d="m6 6 12 12M18 6 6 18"/>',edit:'<path d="m15 4 5 5M4 20l5-1L21 7l-5-5L4 14z"/>',arrow:'<path d="M4 12h16M14 6l6 6-6 6"/>',chevron:'<path d="m9 5 7 7-7 7"/>'};const icon=x=>`<svg viewBox="0 0 24 24" aria-hidden="true">${paths[x]||paths.doc}</svg>`;
document.querySelectorAll("[data-icon]").forEach(el=>el.innerHTML=icon(el.dataset.icon));
const $ = id => document.getElementById(id);
const escapeHTML = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let model = null, view = "original", selected = 0, pending = null, editMode = "edit_accept";
let parentOrigin = "*", restored = false, resumeToken = "", transportReady = false;
let responseTimer = null;
const storageKey = "noteguard.forest-paper.v2.resume";
function send(type, payload = {}) {
  window.parent.postMessage({isStreamlitMessage:true, type, ...payload}, parentOrigin);
}
function dispatch(action, extra = {}) {
  if (pending || !model || !transportReady) return;
  const id = crypto.randomUUID();
  pending = {id, action};
  lockButtons(true);
  $("decision-state").textContent = ["accept","edit_accept","recheck"].includes(action) ? "复检中…等待真实规则与语义结果。" : "正在处理…";
  send("streamlit:setComponentValue", {dataType:"json", value:{id, action, version:model.version, ...extra}});
  responseTimer = setTimeout(()=>{
    if(pending?.id!==id)return;
    pending=null;lockButtons(false);render();
    $("decision-state").textContent="连接响应超时，本次操作尚未确认。可重试；不视为审核通过。";
  },70000);
}
function lockButtons(value) {
  document.querySelectorAll("button").forEach(b => b.disabled = value);
}
function risksFor(review) { return review ? [...review.rules, ...review.semantic] : []; }
function activeReview() { return view === "final" ? model.final_review : model.original_review; }
function riskRanges(text, field) {
  const chars = Array.from(text), ranges = [];
  risksFor(activeReview()).forEach((r, index) => {
    if (r.field !== field) return;
    if (r.positioning === "detector-offset" && chars.slice(r.start,r.end).join("") === r.excerpt) {
      ranges.push({start:r.start,end:r.end,index});
    } else if (r.positioning === "exact-quote" && r.excerpt) {
      const needle = Array.from(r.excerpt);
      for(let i=0;i<=chars.length-needle.length;i++)
        if(chars.slice(i,i+needle.length).join("") === r.excerpt) ranges.push({start:i,end:i+needle.length,index});
    }
  });
  const chosen = [];
  ranges.sort((a,b)=>(a.index===selected?-1:0)-(b.index===selected?-1:0)||a.start-b.start);
  ranges.forEach(r => {if(!chosen.some(x=>r.start<x.end && x.start<r.end))chosen.push(r);});
  return chosen.sort((a,b)=>a.start-b.start);
}
function highlight(text, field) {
  if(view === "draft") return escapeHTML(text).replace(/\n/g,"<br>");
  const chars = Array.from(text), ranges = riskRanges(text,field);let out="",cursor=0;
  ranges.forEach(r=>{out+=escapeHTML(chars.slice(cursor,r.start).join(""));out+=`<button type="button" class="mark ${r.index===selected?"active":""}" data-risk="${r.index}">${escapeHTML(chars.slice(r.start,r.end).join(""))}<sup>${r.index+1}</sup></button>`;cursor=r.end;});
  return (out+escapeHTML(chars.slice(cursor).join(""))).replace(/\n/g,"<br>");
}
function selectRisk(index) {selected=index;render();document.querySelector('.mark.active')?.scrollIntoView({block:"nearest"});}
function renderPaper() {
  const doc = view === "draft" ? model.draft : view === "final" ? model.final : model.original;
  $("document-title").textContent = doc?.title?.trim() || (doc ? "无标题内容" : "待审核内容");
  $("document-title").title = $("document-title").textContent;
  $("paper").innerHTML = doc ? `<div class="kicker">${icon(view === "original" ? "lock" : "doc")}${view === "draft" ? "完整 AI 建议稿 · 独立候选版本" : view === "final" ? "最终采用稿 · 独立确认版本" : "原始内容 · 只读快照"}</div><div class="field">标题</div><h2>${highlight(doc.title,"title")}</h2><div class="field">正文</div><p>${highlight(doc.body,"body")}</p>${view === "draft" ? `<div class="draft-note">建议来源：${escapeHTML(model.draft.source)}。建议稿尚未复检。</div><p class="independent">${escapeHTML(model.draft.reason)}${model.draft.error?"<br>"+escapeHTML(model.draft.error):""}</p>${model.draft.confirmation_items?.length?`<p class="independent">人工确认项（不属于建议正文）：<br>${model.draft.confirmation_items.map(escapeHTML).join("<br>")}</p>`:""}` : ""}${view === "final" ? diffHTML(model.diff) : ""}` : '<div class="kicker">输入标题与正文，开始真实 V2 审核。</div><p class="service-status">尚未评测。请点击右上角「输入内容」。</p>';
  document.querySelectorAll("[data-view]").forEach(b=>{b.classList.toggle("active",b.dataset.view===view);b.setAttribute("aria-selected",b.dataset.view===view);});
  $("paper").setAttribute("aria-labelledby",view+"-tab");
  $("view-label").textContent = view === "draft" ? "候选稿 · 未复检" : view === "final" ? statusText() : "原文快照 · 只读";
  $("foot-text").textContent = view === "final" ? "原文、建议稿、最终采用稿分别保留" : "原文保留，建议不会覆盖正文";
  $("doc-count").textContent = activeReview() ? `${risksFor(activeReview()).length} 项风险证据` : "尚未评测";
  document.querySelectorAll(".mark[data-risk]").forEach(b=>b.onclick=()=>selectRisk(Number(b.dataset.risk)));
}
function diffHTML(rows) {
  return `<div class="independent">原文 → 最终采用稿 · 实际修改差异</div>${rows.length ? rows.map(r=>`<div class="difference-log"><span>${r.field === "title" ? "标题" : "正文"}：</span>${r.removed?`<del>− ${escapeHTML(r.removed)}</del>`:""}${r.added?`<ins>＋ ${escapeHTML(r.added)}</ins>`:""}</div>`).join("") : '<p class="difference-log">最终采用稿与原文一致。</p>'}`;
}
function statusText() {
  return ({not_adopted:"尚未采用",pending:"待复检",running:"复检中",failed:"复检未完成 · 可重试",completed:model.final_review?.message ?? "尚未评测"})[model.final_status];
}
function renderRisk() {
  const review = activeReview(), risks = risksFor(review);selected=Math.min(selected,Math.max(0,risks.length-1));
  document.querySelector(".panel-title h2").innerHTML=`${view==="final"?"最终稿复检":"风险审阅"}<span class="count">${risks.length}</span>`;
  document.querySelector(".panel-title .warn").textContent=view==="final"?statusText():model.final?`已采用 · ${statusText()}`:model.path==="rejected"?"已拒绝建议":model.state==="input"||!model.original?"尚未评测":"待人工确认";
  document.querySelector(".counts").textContent=review ? `规则 ${review.rules.length} 项 · 语义 ${review.semantic_available?review.semantic.length+" 项":"未完成"}` : "尚未评测";
  $("evidence-context").hidden=view!=="draft";
  $("risk-nav").innerHTML=risks.map((r,i)=>`<button class="risk-item ${i===selected?"active":""}" data-index="${i}"><span class="num">${i+1}</span><span><strong>${escapeHTML(r.category||"语义风险")}</strong><small>${r.field==="title"?"标题":"正文"} · ${r.source==="rule"?"规则结果":"语义结果"}</small></span>${icon("chevron")}</button>`).join("");
  document.querySelectorAll(".risk-item").forEach(b=>b.onclick=()=>selectRisk(Number(b.dataset.index)));
  const r=risks[selected];
  const evidenceDiff=r?(model.draft_diff||[]).filter(d=>d.field===r.field && d.removed.includes(r.excerpt)):[];
  $("review-detail").innerHTML= r ? `<div class="label">${view==="final"?"最终稿":"原文"} · ${r.field==="title"?"标题":"正文"}<span>${selected+1} / ${risks.length}</span></div><div class="current-heading"><span class="num current">${selected+1}</span><h3>${escapeHTML(r.category||"语义风险")}</h3></div><blockquote class="quote">${escapeHTML(r.excerpt)}</blockquote><p class="reason">${escapeHTML(r.reason)}</p><details class="evidence"><summary>查看检测证据</summary><p>${r.source==="rule"?"真实规则检测位置":"按模型返回原文引用精确匹配；不是模型逐词坐标"} · ${escapeHTML(r.severity)}</p></details><div class="diff-section"><div class="diff-title">对应修改证据<small>${view==="final"?"原文 → 最终采用稿":"原文 → AI 建议稿"}</small></div><div class="diff">${view==="final"?'<p class="neutral">中央显示原文与最终采用稿的实际差异；AI 建议稿单独保留，不参与此比较。</p>':evidenceDiff.length?evidenceDiff.map(d=>`<div class="diff-row minus"><span>−</span><del>${escapeHTML(d.removed)}</del></div>${d.added?`<div class="diff-row neutral"><span>＋</span><span>${escapeHTML(d.added)}</span></div>`:'<div class="diff-row neutral">删除此片段 · 无新增替换文本</div>'}`).join(""):'<p class="neutral">该引用未对应完整删除片段，请核对整稿差异。</p>'}</div><button class="view-draft" id="view-full-draft">查看完整 AI 建议稿 →</button></div>` : `<p class="service-status">${view==="final"?escapeHTML(statusText()):review?escapeHTML(review.message):"尚未评测"}</p>${model.draft?'<button class="view-draft" id="view-full-draft">查看完整 AI 建议稿 →</button>':""}`;
  const full=$("view-full-draft");if(full){full.disabled=!model.draft;full.onclick=()=>switchView("draft");}
  $("live-scope").textContent = review?.scope_note || "尚未评测。";
}
function syncFrameHeight() {
  const mobile=typeof window.matchMedia==="function" && window.matchMedia("(max-width: 850px)").matches;
  if(mobile){
    // Mobile is a natural-height vertical document; keep the entire risk and decision panel reachable.
    const shell=document.querySelector(".shell");
    const naturalHeight=Math.ceil(shell?.getBoundingClientRect().height||0);
    send("streamlit:setFrameHeight",{height:Math.max(720,naturalHeight+20)});
    return;
  }
  let height=900;try{height=Math.max(720,window.parent.innerHeight);}catch{}
  send("streamlit:setFrameHeight",{height});
}
window.addEventListener("resize",syncFrameHeight);
function render() {
  if(!model)return;
  if(view==="draft"&&!model.draft||view==="final"&&!model.final)view="original";
  renderRisk();renderPaper();
  $("draft-tab").disabled=!model.draft;$("final-tab").hidden=!model.final;
  ["accept","reject","edit"].forEach(id=>$(id).hidden=!!model.final);
  $("final-actions").hidden=!model.final;
  document.querySelector(".decisions > .scope").textContent=model.final ? "以下操作针对最终采用稿；原文与 AI 建议稿保留。" : "以下操作均针对整份 AI 建议稿";
  ["accept","reject","edit"].forEach(id=>$(id).disabled=!model.draft||model.path!=="needs_decision");
  $("decision-state").textContent=model.error || (model.final ? statusText() : model.path==="rejected"?"已拒绝建议；原文与原风险结果保留。":model.original_review?.status==="partial_failure"?"语义审核未完成，可重新审核。":"");
  $("final-details").hidden=true;
  if(pending)lockButtons(true);
  syncFrameHeight();
}
function switchView(next) {view=next;selected=0;render();}
function openEdit(mode) {
  if(pending)return;
  editMode=mode;const doc=mode==="save_final"?model.final:model.draft;if(!doc)return;
  $("edit-title").value=doc.title;$("edit-body").value=doc.body;$("error").textContent="";
  $("edit-dialog").querySelector("p").textContent=mode==="save_final"?"编辑最终采用稿。保存内容变化后，旧复检结果失效；取消不会改变已保存稿件或复检结果。":"编辑整份 AI 建议稿，确认后保存为独立的最终采用稿并复检。原文与 AI 建议稿均保留。";
  $("edit-dialog").querySelector("h2").textContent=mode==="save_final"?"继续修改最终采用稿":"修改后采用";
  $("confirm").textContent=mode==="save_final"?"保存修改 · 待复检":"确认采用并复检";
  $("edit-dialog").showModal();
}
function openInput() {
  if(!model || pending)return;
  $("input-title").value=model.original?.title||"";$("input-body").value=model.original?.body||"";
  $("input-error").textContent="";$("input-dialog").showModal();
}
document.querySelectorAll(".rail .nav").forEach((nav,i)=>{nav.setAttribute("role","button");nav.setAttribute("tabindex","0");const page=["audit","notes","history","rules"][i];nav.onclick=()=>{if(i===0){switchView("original");return;}dispatch("navigate",{page});};nav.onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();nav.click();}};});
$("original-tab").onclick=()=>switchView("original");$("draft-tab").onclick=()=>switchView("draft");$("final-tab").onclick=()=>switchView("final");
$("new-input").onclick=openInput;
$("input-cancel").onclick=()=>$("input-dialog").close();
$("audit").onclick=()=>{const doc={title:$("input-title").value,body:$("input-body").value};if(!doc.body.trim()){$("input-error").textContent="正文不能为空。";return;}dispatch("audit",{document:doc});};
$("accept").onclick=()=>dispatch("accept");$("reject").onclick=()=>dispatch("reject");$("edit").onclick=()=>openEdit("edit_accept");
$("continue-edit").onclick=()=>openEdit("save_final");$("recheck").onclick=()=>dispatch("recheck");
$("cancel").onclick=()=>$("edit-dialog").close();
$("confirm").onclick=()=>{const doc={title:$("edit-title").value,body:$("edit-body").value};if(!doc.body.trim()){$("error").textContent="正文不能为空。";return;}dispatch(editMode,{document:doc});};
window.addEventListener("message", event=>{
  if(event.source!==window.parent||event.data?.type!=="streamlit:render")return;
  parentOrigin=event.origin;
  const args=event.data.args;if(!args?.model)return;
  transportReady=true;
  $("environment-label").textContent=args.full_app ? "● V2 真实审核" : "● V2 集成实验";
  document.querySelectorAll(".rail .nav")[1].removeAttribute("title");
  if(!restored){
    restored=true;let token=null;try{token=localStorage.getItem(storageKey);}catch{}
    if(token && token!==args.resume_token){pending={id:crypto.randomUUID(),action:"restore"};send("streamlit:setComponentValue",{dataType:"json",value:{...pending,token}});return;}
  }
  if(model && args.model.version<model.version && args.resume_token===resumeToken)return;
  if(pending && args.ack!==pending.id)return;
  if(pending && args.ack===pending.id){const action=pending.action;clearTimeout(responseTimer);pending=null;lockButtons(false);if(!args.model.error){$("input-dialog").close();$("edit-dialog").close();if(["accept","edit_accept","save_final","recheck"].includes(action))view="final";if(action==="audit")view="original";}}
  model=args.model;resumeToken=args.resume_token;
  try{localStorage.setItem(storageKey,resumeToken);}catch{}
  render();if(args.resume_message && !model.original)$("decision-state").textContent=args.resume_message;
});
send("streamlit:componentReady",{apiVersion:1});
