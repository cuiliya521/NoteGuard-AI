// DOM unit tests. No browser rendering and no online AI assertions.
const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');const {JSDOM}=require('jsdom');
const root=path.join(__dirname,'..','components','forest_paper_v2');
const source=fs.readFileSync(path.join(root,'component.js'),'utf8');
const review={rules:[{field:'body',source:'rule',excerpt:'保证',start:1,end:3,positioning:'detector-offset',category:'效果承诺',reason:'真实规则测试引用',severity:'high'}],semantic:[],semantic_available:false,status:'partial_failure',message:'语义未完成',scope_note:'未发现明显风险不等于保证内容绝对合规'};
function base(){return {version:1,path:'needs_decision',original:{title:'标题',body:'😀保证提分'},draft:{title:'标题',body:'😀陪练',source:'TEST_DOUBLE',reason:'unit',confirmation_items:[]},original_review:review,final:null,final_revision:0,final_status:'not_adopted',final_review:null,error:'',diff:[],draft_diff:[]};}
function harness(model=base(),savedToken){
 const dom=new JSDOM(fs.readFileSync(path.join(root,'index.html'),'utf8'),{url:'https://local-test.invalid/component/',runScripts:'outside-only'}),w=dom.window;
 let n=0;w.crypto.randomUUID=()=>`unit-${++n}`;
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false};
 w.HTMLElement.prototype.scrollIntoView=function(){};
 w.setTimeout=fn=>{w.testTimeout=fn;return 1;};w.clearTimeout=()=>{w.testTimeout=null;};
 const sent=[];w.postMessage=(m)=>sent.push(m);
 if(savedToken)w.localStorage.setItem('noteguard.forest-paper.v2.resume',savedToken);
 w.eval(source);
 function receive(next,ack='',token='token',foreign=false){w.dispatchEvent(new w.MessageEvent('message',{source:foreign?{}:w.parent,origin:'https://local-test.invalid',data:{type:'streamlit:render',args:{model:next,ack,resume_token:token}}}));}
 receive(model);
 return {w,sent,receive,doc:w.document,events:()=>sent.filter(x=>x.type==='streamlit:setComponentValue').map(x=>x.value)};
}
test('tabs preserve independent texts and original risk evidence',()=>{
 const h=harness();h.doc.getElementById('draft-tab').click();assert.match(h.doc.getElementById('paper').textContent,/😀陪练/);assert.equal(h.doc.getElementById('evidence-context').hidden,false);
 h.doc.getElementById('original-tab').click();assert.match(h.doc.getElementById('paper').textContent,/😀保证/);assert.equal(h.events().length,0);
});
test('direct accept emits whole-document decision once and shows recheck pending',()=>{
 const h=harness();h.doc.getElementById('accept').click();h.doc.getElementById('accept').click();assert.equal(h.events().length,1);assert.equal(h.events()[0].action,'accept');assert.match(h.doc.getElementById('decision-state').textContent,/复检中/);
});
test('reject is a real component event',()=>{const h=harness();h.doc.getElementById('reject').click();assert.equal(h.events()[0].action,'reject');});
test('edit confirm emits exact title and body',()=>{const h=harness();h.doc.getElementById('edit').click();h.doc.getElementById('edit-body').value='人工正文';h.doc.getElementById('confirm').click();assert.equal(h.events()[0].document.body,'人工正文');assert.equal(h.events()[0].action,'edit_accept');});
test('empty edit blocks confirmation without sending request',()=>{const h=harness();h.doc.getElementById('edit').click();h.doc.getElementById('edit-body').value=' \n ';h.doc.getElementById('confirm').click();assert.equal(h.events().length,0);assert.match(h.doc.getElementById('error').textContent,/不能为空/);});
test('cancel after changing text keeps valid saved result and sends no mutation',()=>{
 const m=base();m.path='accepted';m.final={title:'标题',body:'已保存'};m.final_status='completed';m.final_revision=2;m.final_review={...review,rules:[],semantic_available:true,status:'completed',message:'未发现明显风险',revision:2};
 const h=harness(m);h.doc.getElementById('continue-edit').click();h.doc.getElementById('edit-body').value='未确认修改';h.doc.getElementById('cancel').click();h.doc.getElementById('final-tab').click();assert.match(h.doc.getElementById('paper').textContent,/已保存/);assert.match(h.doc.getElementById('view-label').textContent,/未发现明显风险/);assert.equal(h.events().length,0);
});
test('old render cannot overwrite newer accepted state',()=>{const h=harness();h.receive({...base(),version:4,original:{title:'new',body:'new'}});h.receive(base());assert.match(h.doc.getElementById('paper').textContent,/new/);});
test('foreign postMessage cannot inject result',()=>{const h=harness();h.receive({...base(),version:8,original:{title:'injected',body:'injected'}},'','token',true);assert.doesNotMatch(h.doc.getElementById('paper').textContent,/injected/);});
test('refresh uses server recovery token instead of trusting browser result data',()=>{const h=harness(base(),'old-token');assert.equal(h.events()[0].action,'restore');assert.equal(h.events()[0].token,'old-token');assert.equal(h.events()[0].document,undefined);});
test('input empty body blocked, populated input sends audit',()=>{const h=harness();h.doc.getElementById('new-input').click();h.doc.getElementById('input-body').value='';h.doc.getElementById('audit').click();assert.equal(h.events().length,0);h.doc.getElementById('input-body').value='真实输入';h.doc.getElementById('audit').click();assert.equal(h.events()[0].action,'audit');});
test('unavailable semantic result never says passed in final status',()=>{const m=base();m.final={title:'标题',body:'确认稿'};m.final_status='failed';m.final_review=review;const h=harness(m);h.doc.getElementById('final-tab').click();assert.match(h.doc.getElementById('view-label').textContent,/未完成/);assert.doesNotMatch(h.doc.getElementById('view-label').textContent,/通过/);h.doc.getElementById('recheck').click();assert.equal(h.events()[0].action,'recheck');});
test('user text is escaped, with no executable inserted HTML',()=>{const m=base();m.original.title='<img src=x onerror=alert(1)>';const h=harness(m);assert.equal(h.doc.getElementById('paper').querySelector('img'),null);});

test('Unicode detector offsets use code points and risk buttons are keyboard accessible',()=>{const h=harness();const mark=h.doc.querySelector('.mark');assert.equal(mark.tagName,'BUTTON');assert.match(mark.textContent,/^保证1$/);});

test('transport timeout unlocks retry and never displays approval',()=>{const h=harness();h.doc.getElementById('accept').click();h.w.testTimeout();assert.equal(h.doc.getElementById('accept').disabled,false);assert.match(h.doc.getElementById('decision-state').textContent,/尚未确认/);});
test('legacy modules emit real navigation events',()=>{const h=harness();h.doc.querySelectorAll('.rail .nav')[1].click();assert.equal(h.events()[0].action,'navigate');assert.equal(h.events()[0].page,'notes');});

test('adopted status stays truthful on original, draft and final views',()=>{
 const m=base();m.path='accepted';m.final={title:'最终标题',body:'最终正文'};m.final_status='completed';m.final_review={...review,rules:[],semantic:[],semantic_available:true,message:'未发现明显风险'};
 const h=harness(m);for(const tab of ['original-tab','draft-tab','final-tab']){h.doc.getElementById(tab).click();assert.doesNotMatch(h.doc.querySelector('.panel-title .warn').textContent,/待人工确认/);}
 assert.match(h.doc.querySelector('.decisions > .scope').textContent,/最终采用稿/);
 assert.match(h.doc.getElementById('paper').textContent,/原文 → 最终采用稿/);
});
test('final risk differences never label AI draft as final comparison',()=>{
 const m=base();m.final={title:'最终',body:'😀保证'};m.final_status='completed';m.final_review=review;
 const h=harness(m);h.doc.getElementById('final-tab').click();assert.match(h.doc.querySelector('.diff-title').textContent,/原文 → 最终采用稿/);assert.match(h.doc.querySelector('.neutral').textContent,/AI 建议稿单独保留/);
 h.doc.getElementById('original-tab').click();assert.match(h.doc.querySelector('.diff-title').textContent,/原文 → AI 建议稿/);
});
test('failed recheck clears final evidence, preserves original and retry recovers',()=>{
 const m=base();m.final={title:'最终',body:'确认稿'};m.final_status='completed';m.final_review={...review,rules:[],semantic_available:true,message:'未发现明显风险'};
 const h=harness(m);h.doc.getElementById('final-tab').click();h.doc.getElementById('recheck').click();
 const ev=h.events()[0];const failed={...m,version:2,final_status:'failed',final_review:null};h.receive(failed,ev.id);
 assert.match(h.doc.querySelector('.panel-title .warn').textContent,/未完成/);assert.doesNotMatch(h.doc.getElementById('paper').textContent,/保证/);assert.match(h.doc.getElementById('decision-state').textContent,/重试/);
 h.doc.getElementById('original-tab').click();assert.match(h.doc.getElementById('paper').textContent,/保证/);
 h.doc.getElementById('final-tab').click();h.doc.getElementById('recheck').click();const retry=h.events()[1];h.receive({...m,version:3},retry.id);assert.match(h.doc.getElementById('decision-state').textContent,/未发现明显风险/);
 h.receive(failed);assert.match(h.doc.getElementById('decision-state').textContent,/未发现明显风险/);
});
