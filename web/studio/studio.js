const $ = (id) => document.getElementById(id);
const escape = (text) => String(text ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state, selected, dirty = false, pending = false, rendered = '';
function message(text, error=false) { $('message').className = text ? `notice ${error?'error':''}` : ''; $('message').textContent=text; }
async function api(path, method='GET', data) {
  const response=await fetch(path,{method,headers:{'Content-Type':'application/json','X-Desk-Token':state?.token ?? ''},body:data===undefined?undefined:JSON.stringify(data)});
  const result=await response.json();
  if(!response.ok) throw new Error(typeof result.detail==='string'?result.detail:'Check the topic, date and script fields.');
  return result;
}
function links(sources){return sources.map(s=>`<li><a href="${escape(s.url)}" target="_blank" rel="noopener noreferrer">${escape(s.title)}</a></li>`).join('');}
async function refresh(force=false) {
  state=await api('/api/state');
  $('budget').textContent=`APP ALLOWANCE RESERVED\n$${state.budget.daily.toFixed(2)} / $${state.budget.daily_limit.toFixed(2)} today · $${state.budget.monthly.toFixed(2)} / $${state.budget.monthly_limit.toFixed(2)} this month`;
  if(!$('as-of').value) $('as-of').value=state.today;
  $('as-of').max=state.today;
  if(!state.configured) message('Add your OpenAI API key to the local .env file, then restart the studio.',true);
  selected ||= state.episodes[0]?.id;
  $('library').innerHTML=state.episodes.map(e=>`<button class="episode-link ${e.id===selected?'active':''}" data-id="${e.id}">${escape(e.script?.title||e.brief.topic.slice(0,70))}<small>${escape(e.brief.as_of)} / ${escape(state.busy.includes(e.id)?'working':e.status)}</small></button>`).join('')||'<p class="quiet">No episodes yet.</p>';
  for(const button of $('library').querySelectorAll('button')) button.onclick=()=>{if(dirty&&!confirm('Discard your unsaved script edits?'))return;selected=button.dataset.id;dirty=false;rendered='';render();};
  $('new').querySelector('button').disabled=pending||state.busy.length>0||!state.configured;
  if(!dirty||force) render();
}
function render(){
  const e=state.episodes.find(e=>e.id===selected); if(!e)return;
  const busy=state.busy.includes(e.id), signature=JSON.stringify([e,busy,pending]);
  if(signature===rendered)return; rendered=signature;
  const valid=e.review?.passed, media=!!(e.audio_hash&&e.cover_hash);
  $('workspace').innerHTML=`<div class="steps"><span class="step ${e.research?'done':''}">01 RESEARCH</span><span class="step ${e.script?'done':''}">02 SCRIPT</span><span class="step ${valid?'done':''}">03 CHECK</span><span class="step ${media?'done':''}">04 MEDIA</span></div>
    <p class="eyebrow orange ${busy?'progress':''}">${escape(busy?'Working: '+e.status:e.status)}</p><h2>${escape(e.script?.title||'Your next episode')}</h2><p class="quiet">As of ${escape(e.brief.as_of)} · ${escape(e.brief.minutes)} minute target</p>
    ${e.error?`<div class="notice error" role="alert">${escape(e.error)}</div>`:''}
    ${e.review?`<div class="notice ${valid?'':'error'}"><strong>${valid?'Evidence check passed':'Needs another look'}</strong><p>${valid?'No unsupported claims were found in this check.':'Review the issues below, then revise the script or edit it yourself.'}</p><details><summary>Full check notes</summary><p>${escape(e.review.notes)}</p></details>${e.review.issues.map(i=>`<p>${escape(i)}</p>`).join('')}<span class="quiet">This model check can miss mistakes. Read the sources before approving.</span></div>`:''}
    <div class="actions"><button data-action="draft" ${e.script?'class="secondary"':''}>${e.script?'Resume draft checks':'Research & draft'}</button>${e.script?'<button data-action="review" class="secondary">Check script again</button>':''}${e.review&&!valid?'<button data-action="revise" class="secondary">Revise from feedback</button>':''}${valid?'<button data-action="media">Generate audio & cover</button>':''}</div>
    ${valid?'<p class="quiet">Media reserves up to $0.45. Finished files are reused when you resume.</p>':''}
    ${e.audio_hash?`<audio controls preload="metadata" src="/media/${e.id}/episode.mp3"><a href="/media/${e.id}/episode.mp3">Download MP3</a></audio>`:''}
    ${media?'<button data-action="listen" class="secondary">Review the audio</button><p class="quiet">An audio model checks the actual recording. Reserves $1.10. Listen yourself before approving.</p>':''}
    ${e.listening_review?`<div class="notice ${e.listening_review.passed?'':'error'}"><strong>${e.listening_review.passed?'Audio check passed':'Audio needs another look'}</strong><p>${escape(e.listening_review.notes)}</p>${e.listening_review.issues.map(i=>`<p>${escape(i)}</p>`).join('')}</div>`:''}
    ${e.cover_hash?`<img class="studio-cover" src="/media/${e.id}/cover.png" alt="Big Sky Fight Desk episode cover">`:''}
    ${e.script?`<details open><summary>Read & edit the script</summary><form id="editor" class="editor"><label class="field" for="edit-title">Episode title</label><input id="edit-title" maxlength="140" value="${escape(e.script.title)}"><label class="field" for="edit-description">Episode description</label><textarea id="edit-description" maxlength="600">${escape(e.script.description)}</textarea>${e.script.segments.map((s,i)=>`<h3>${escape(s.heading)}</h3><label class="field" for="segment-${i}">Segment ${i+1}</label><textarea id="segment-${i}">${escape(s.text)}</textarea><label class="field" for="facts-${i}">Supporting fact numbers</label><input id="facts-${i}" value="${s.fact_ids.map(n=>n+1).join(', ')}" placeholder="1, 2 or leave blank for the intro"><p class="quiet">Match the numbered facts below. Separate numbers with commas.</p>`).join('')}<button type="submit" class="secondary">Save edits</button><p class="quiet">Saving edits requires a new check and new media before export.</p></form></details>`:''}
    ${e.evidence?`<details><summary>Facts & sources (${e.evidence.facts.length})</summary><ol class="fact-list">${e.evidence.facts.map(f=>`<li>${escape(f.text)}${f.source_urls.map(u=>`<a href="${escape(u)}" target="_blank" rel="noopener noreferrer">${escape(u)}</a>`).join('')}</li>`).join('')}</ol>${e.evidence.uncertainties.length?`<h3>Still unconfirmed</h3>${e.evidence.uncertainties.map(u=>`<p>${escape(u)}</p>`).join('')}`:''}</details>`:''}
    ${e.research?`<details><summary>Research notes</summary><div class="prose"><p>${escape(e.research.text).replace(/\n/g,'<br>')}</p><ol class="source-list">${links(e.research.sources)}</ol></div></details>`:''}
    ${valid?`<details ${media?'open':''}><summary>Approve & export</summary><p>Read the script and its sources, then listen to the audio and check the cover. Export prepares the public page on this computer. Publishing still happens through a separate GitHub PR.</p><div class="actions"><button data-action="approve" class="secondary">${e.approved?'Approved ✓':'I reviewed this episode'}</button><button data-action="export" ${!e.approved||!media||!e.listening_review?.passed?'disabled':''}>Export public episode</button></div>${e.exported_at?'<p class="notice">Exported locally. <a href="/preview/" target="_blank" rel="noopener">Open the public page preview ↗</a></p>':''}</details>`:''}`;
  for(const button of $('workspace').querySelectorAll('[data-action]')){
    button.disabled ||= busy||pending;
    button.onclick=()=>perform(button.dataset.action);
  }
  const editor=$('editor');if(editor){editor.oninput=()=>{dirty=true;};editor.onsubmit=saveEdits;for(const input of editor.querySelectorAll('input,textarea,button'))input.disabled=busy||pending;}
}
async function perform(action){
  if(dirty){message('Save your script edits first.',true);return;}
  pending=true;rendered='';render();message('');
  try{await api(`/api/episodes/${selected}/${action}`,'POST',{});message(action==='export'?'Episode exported locally. Open the preview to check it.':action==='approve'?'This script version is approved.':'Working on your episode. You can leave this page open.');}
  catch(error){message(error.message,true);}finally{pending=false;await refresh(true);}
}
async function saveEdits(event){event.preventDefault();const e=state.episodes.find(e=>e.id===selected);const script=structuredClone(e.script);script.title=$('edit-title').value;script.description=$('edit-description').value;script.segments.forEach((s,i)=>{s.text=$(`segment-${i}`).value;s.fact_ids=$(`facts-${i}`).value.split(',').map(n=>n.trim()).filter(Boolean).map(n=>Number(n)-1);});try{await api(`/api/episodes/${selected}`,'PUT',{script});dirty=false;message('Edits saved. Run the evidence check again.');await refresh(true);}catch(error){message(error.message,true);}}
$('new').onsubmit=async(event)=>{event.preventDefault();if(dirty&&!confirm('Discard your unsaved script edits?'))return;pending=true;try{const e=await api('/api/episodes','POST',{topic:$('topic').value,as_of:$('as-of').value,minutes:Number($('minutes').value)});selected=e.id;dirty=false;await api(`/api/episodes/${selected}/draft`,'POST',{});message('Research started. This usually takes a minute or two.');}catch(error){message(error.message,true);}finally{pending=false;await refresh(true);}};
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
refresh().catch(error=>message(error.message,true));
setInterval(()=>{if(!pending)refresh().catch(()=>message('The studio is disconnected. Reopen start-studio.cmd to reconnect.',true));},3000);
