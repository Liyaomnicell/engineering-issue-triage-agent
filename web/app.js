const $ = id => document.getElementById(id);
const state = { caseId: null, cases: [], results: [], packet: '', history: [], index: {}, searching: false, selected: -1 };
const escape = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Triage-Request':'1'}, body:JSON.stringify(body)});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || 'Request failed');
  return value;
}
function notice(message, error=false) { $('notice').textContent=message; $('notice').className='notice'+(error?' error':''); }
function fields() { return {id:state.caseId,title:$('case-title').value.trim() || $('question').value.trim().slice(0,100) || 'Untitled investigation',question:$('question').value,description:$('description').value,version:$('version').value,sourceUrl:$('source-url').value,history:state.history}; }
async function refreshCases() {
  state.cases=await api('/api/investigations'); $('case-count').textContent=state.cases.length;
  $('case-list').innerHTML=state.cases.length ? state.cases.map(c=>`<button class="case-item ${c.id===state.caseId?'selected':''}" data-case="${escape(c.id)}">${escape(c.title)}<small>${escape(new Date(c.updated).toLocaleDateString())}</small></button>`).join('') : '<p class="muted empty-list">Your investigations will appear here.</p>';
}
async function save(silent=false) {
  const saved=await api('/api/investigation',fields()); state.caseId=saved.id;
  $('breadcrumb-title').textContent=saved.title; await refreshCases();
  if(!silent) notice('Investigation saved locally. You can return to it from the sidebar.');
  return saved;
}
function renderHistory() {
  $('history').innerHTML=state.history.length?'<div class="section-label history-heading">PREVIOUS SEARCHES</div>'+state.history.slice().reverse().map((h,i)=>`<div class="history-entry"><button data-history="${state.history.length-1-i}">${escape(h.question)}</button><small>${escape(new Date(h.time).toLocaleString())} · ${Number(h.count)} retrieved excerpts</small></div>`).join(''):'';
}
function renderLogs(logs=[]) {
  $('log-list').innerHTML=logs.map(l=>`<div class="log-item">≋ ${escape(l.file)} <span class="muted">· ${(l.bytes/1024).toFixed(1)} KB</span></div>`).join('');
  $('logs-coverage').textContent=logs.length?`${logs.length} uploaded files · isolated to this case`:'No logs added to this case';
}
async function loadCase(id) {
  const c=await api('/api/investigation?id='+encodeURIComponent(id));
  state.caseId=c.id; state.history=c.history || []; state.results=[]; state.packet='';
  $('case-title').value=c.title; $('question').value=c.question; $('description').value=c.description; $('version').value=c.version; $('source-url').value=c.sourceUrl;
  $('breadcrumb-title').textContent=c.title; $('results-section').classList.add('hidden'); $('welcome').classList.remove('hidden');
  renderLogs(c.logs);renderHistory();await refreshCases();notice('Investigation loaded. Search again to retrieve evidence from the current index.');
}
function newCase() {
  if(state.searching) return;
  if(($('question').value || $('description').value || $('case-title').value) && !window.confirm('Start a new investigation? Save any unsaved changes first.')) return;
  state.caseId=null;state.history=[];state.results=[];state.packet='';
  for(const id of ['case-title','question','description','version','source-url']) $(id).value='';
  $('breadcrumb-title').textContent='New investigation'; $('notice').classList.add('hidden');$('results-section').classList.add('hidden');$('welcome').classList.remove('hidden');renderLogs();renderHistory();refreshCases().catch(e=>notice(e.message,true));$('question').focus();
}
function renderResults() {
  $('welcome').classList.add('hidden');$('results-section').classList.remove('hidden');
  $('result-count').textContent=state.results.length;
  $('search-summary').textContent='Ranked by matching words and identifiers · no generated answer';
  $('version-note').textContent=$('version').value?`Affected version: ${$('version').value}. Retrieved code is from indexed checkouts; release compatibility has not been verified.`:'No affected version specified. Code reflects indexed checkouts; verify the release before drawing conclusions.';
  $('results').innerHTML=state.results.length?state.results.map((r,i)=>`<button class="result" data-result="${i}"><div class="result-top"><span>${escape(r.kind==='code'?'Source code':r.kind==='confluence'?'Confluence export':r.kind==='error'?'Log read error':'Case log')} · E${i+1}</span><span>${escape(r.citation || '')} ↗</span></div><div class="result-title">${escape(r.title)}</div><pre>${escape(r.text.slice(0,550))}</pre><div class="result-meta">${escape(r.repo?`${r.repo} · ${r.branch} · ${r.commit_sha.slice(0,8)}`:r.path || '')}</div></button>`).join(''):'<div class="notice">No matching evidence found. Try an exact error, symbol, endpoint, or a shorter phrase. Case descriptions are context and are not automatically added to the search query.</div>';
  if(state.results.length) selectResult(0);
}
function selectResult(index) {
  const r=state.results[index];state.selected=index;
  document.querySelectorAll('.result').forEach((el,i)=>el.classList.toggle('selected',index===i));
  const sourceUrl=r.url && /^https:\/\/(bitbucket\.org|omnicell-eng\.atlassian\.net)\//.test(r.url) ? r.url : null;
  $('evidence-detail').innerHTML=`<div class="section-label">SELECTED EVIDENCE · E${index+1}</div><h3>${escape(r.title)}</h3><div class="detail-meta">${escape(r.citation || '')}<br>${escape(r.path || '')}${r.repo?`<br>Branch: ${escape(r.branch)}<br>Commit: ${escape(r.commit_sha)}`:''}</div>${sourceUrl?`<a class="detail-link" target="_blank" rel="noopener noreferrer" href="${escape(sourceUrl)}">Open original source ↗</a>`:''}<pre>${escape(r.text)}</pre><div class="detail-meta">${r.kind==='confluence'?'Extracted PDF text. Images are not indexed; the live page may have changed.':r.kind==='code'?'Indexed text snapshot. Verify the branch, release, and surrounding code before making a conclusion.':'Uploaded evidence for this investigation only.'}</div>`;
}
async function search() {
  if(state.searching) return;
  if(!$('question').value.trim()) return notice('Enter a question or exact phrase to search.',true);
  if(!state.index.ready && $('kind').value!=='log') return notice('Build the knowledge index first using the button in the sources panel.',true);
  state.searching=true;$('search').disabled=true;$('search').textContent='Searching…';
  try {
    await save(true);
    const result=await api('/api/search',{question:$('question').value,kind:$('kind').value,repo:$('repo').value,caseId:state.caseId});
    state.results=result.results;state.packet=result.packet;renderResults();
    state.history.push({question:$('question').value,time:new Date().toISOString(),count:state.results.length});state.history=state.history.slice(-100);
    await save(true);renderHistory();$('notice').classList.add('hidden');
  } catch(e) {notice(e.message,true);} finally {state.searching=false;$('search').disabled=false;$('search').innerHTML='Search evidence <span>↗</span>';}
}
async function refreshStatus() {
  const {index}=await api('/api/status');state.index=index;
  $('index-title').textContent=index.running?'Updating knowledge index':index.ready?'Knowledge index available':'Build your knowledge base';
  $('index-detail').textContent=index.running?`${index.phase} · ${Number(index.files).toLocaleString()} text units read` : index.ready?`${Number(index.chunks).toLocaleString()} excerpts · ${Number(index.files).toLocaleString()} indexed text units${index.completed?' · '+new Date(index.completed).toLocaleDateString():''}`:'Index the local Confluence PDFs and repositories to enable search.';
  if(index.phase.startsWith('Index failed')) $('index-detail').textContent=index.phase;
  $('index-dot').classList.toggle('busy',index.running);$('build-index').disabled=index.running;$('build-index').textContent=index.running?'Indexing…':index.ready?'Refresh knowledge index':'Build knowledge index';
  const repos=index.repositories || [];$('repo-count').textContent=repos.length || '—';$('code-coverage').textContent=repos.length?`${repos.length} repositories · indexed checkouts`:'Repositories waiting for index';
  const selected=$('repo').value;
  $('repo').innerHTML='<option value="">All repositories</option>'+repos.map(r=>`<option value="${escape(r.name)}">${escape(r.name)}</option>`).join('');$('repo').value=selected;
  $('knowledge-detail').innerHTML=`<p>${Number(index.chunks).toLocaleString()} excerpts · ${Number(index.skipped).toLocaleString()} oversized or symbolic-link files skipped. ${index.completed?'Completed '+escape(new Date(index.completed).toLocaleString()):escape(index.phase)}</p><table><thead><tr><th>REPOSITORY</th><th>BRANCH</th><th>COMMIT</th></tr></thead><tbody>${repos.map(r=>`<tr><td>${escape(r.name)}</td><td>${escape(r.branch)}</td><td><code>${escape(r.commit.slice(0,10))}</code></td></tr>`).join('')}</tbody></table>${(index.errors || []).map(e=>`<p class="index-error">${escape(e.path)}: ${escape(e.error)}</p>`).join('')}`;
}
async function upload() {
  const input=$('logs');
  try{
    await save(true);
    for(const file of input.files){
      if(file.size>20*1024*1024) throw new Error(`${file.name} exceeds 20 MB.`);
      notice('Adding '+file.name+'…');
      const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});
      await api('/api/log',{id:state.caseId,name:file.name,data});
    }
    const c=await api('/api/investigation?id='+encodeURIComponent(state.caseId));renderLogs(c.logs);notice('Logs saved locally. Choose “Case logs” or “All sources” to search their contents.');
  }catch(e){notice(e.message,true);}finally{input.value='';}
}
$('search').addEventListener('click',search);$('save-case').addEventListener('click',()=>save().catch(e=>notice(e.message,true)));$('new-case').addEventListener('click',newCase);
$('build-index').addEventListener('click',async()=>{try{await api('/api/index',{});await refreshStatus();notice('Indexing started in the background. Source files are read only. You can continue using the previous index while it rebuilds.');}catch(e){notice(e.message,true);}});
$('knowledge-nav').addEventListener('click',()=>$('knowledge-dialog').showModal());$('close-knowledge').addEventListener('click',()=>$('knowledge-dialog').close());$('investigate-nav').addEventListener('click',()=>$('question').focus());
$('logs').addEventListener('change',upload);
$('export').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([state.packet],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`investigation-${state.caseId || 'new'}-evidence.md`;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);});
document.addEventListener('click',event=>{const result=event.target.closest('[data-result]');if(result)selectResult(Number(result.dataset.result));const c=event.target.closest('[data-case]');if(c&&!state.searching)loadCase(c.dataset.case).catch(e=>notice(e.message,true));const suggested=event.target.closest('[data-question]');if(suggested){$('question').value=suggested.dataset.question;$('question').focus();}const h=event.target.closest('[data-history]');if(h){$('question').value=state.history[Number(h.dataset.history)].question;search();}});
document.addEventListener('keydown',event=>{if(event.ctrlKey&&event.key==='Enter'){event.preventDefault();search();}if(event.key.toLowerCase()==='n'&&!event.ctrlKey&&!event.metaKey&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){newCase();}});
Promise.all([refreshStatus(),refreshCases()]).catch(e=>notice('Could not connect to the local server: '+e.message,true));
setInterval(()=>refreshStatus().catch(()=>{}),5000);
