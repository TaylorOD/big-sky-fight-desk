const escape=(text)=>String(text??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const $=id=>document.getElementById(id);
let episodes=[], activeEpisode;
const duration=seconds=>`${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;
const date=text=>new Date(text+'T12:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
function select(){
 const id=new URLSearchParams(location.hash.slice(1)).get('episode');
 const e=episodes.find(e=>e.id===id)||episodes[0]; if(!e)return;
 if(e.id===activeEpisode)return;
 activeEpisode=e.id;
 $('archive').innerHTML=episodes.map((item,i)=>`<a class="episode-link ${item.id===e.id?'active':''}" href="#episode=${encodeURIComponent(item.id)}" ${item.id===e.id?'aria-current="true"':''}><span class="eyebrow orange">DISPATCH ${String(episodes.length-i).padStart(2,'0')}</span><br>${escape(item.title)}<small>${escape(date(item.as_of))} · ${duration(item.duration_seconds)}</small></a>`).join('');
 $('episode').innerHTML=`<p class="eyebrow orange">Field notes / ${escape(date(e.as_of))}</p><h2>${escape(e.title)}</h2><p>${escape(e.description)}</p><div class="audio-panel"><div class="meta">${duration(e.duration_seconds)} / AI GENERATED VOICE</div><audio controls preload="metadata" src="${escape(e.audio)}"><a href="${escape(e.audio)}">Download this episode</a></audio></div><div class="actions"><a href="${escape(e.audio)}" download>Download MP3 ↓</a><a href="${escape(e.transcript)}" download>Transcript ↓</a><a href="${escape(e.cover)}" download>Cover ↓</a></div><p class="quiet">Reporting as of ${escape(date(e.as_of))}. Event details can change. Check the linked sources for updates.</p><details open><summary>Show notes & sources</summary><ol class="source-list">${e.sources.map(s=>`<li><a href="${escape(s.url)}" target="_blank" rel="noopener noreferrer">${escape(s.title)}</a></li>`).join('')}</ol>${e.uncertainties.length?`<div class="notice"><strong>What we could not confirm</strong>${e.uncertainties.map(u=>`<p>${escape(u)}</p>`).join('')}</div>`:''}</details><details><summary>Read the transcript</summary><div class="prose">${e.segments.map(s=>`<h3>${escape(s.heading)}</h3><p>${escape(s.text).replace(/\n/g,'<br>')}</p>`).join('')}</div></details>`;
}
fetch('episodes.json').then(response=>{if(!response.ok)throw new Error();return response.json();}).then(data=>{episodes=data;$('episode-count').textContent=`${episodes.length} ${episodes.length===1?'DISPATCH':'DISPATCHES'}`;if(!episodes.length){$('episode').innerHTML='<div class="empty">The first dispatch is in production. Check back soon.</div>';return;}const img=document.createElement('img');img.src=episodes[0].cover;img.alt='Big Sky Fight Desk. Montana MMA podcast cover.';img.width=1024;img.height=1024;$('hero-art').replaceChildren(img);$('feature-title').textContent=episodes[0].title;$('feature-date').textContent=date(episodes[0].as_of);$('feature-duration').textContent=duration(episodes[0].duration_seconds)+' / AUDIO DISPATCH';select();}).catch(()=>{$('load-message').textContent='Episodes could not load. Please refresh to try again.';$('load-message').className='notice error';$('episode').textContent='';});
window.addEventListener('hashchange',select);


// The same directory guides the studio's research and the reader's source browsing.
fetch('sources.json')
  .then(response => {
    if (!response.ok) throw new Error('Sources unavailable');
    return response.json();
  })
  .then(directory => {
    $('source-date').textContent = `Directory checked ${date(directory.checked_at)}. Entries are research leads, not confirmation of a current card.`;
    const filters = document.querySelector('.source-filters');
    const categories = ['All', ...new Set(directory.sources.map(source => source.category))];
    const labels = {readable: 'Public page', manual: 'Manual check needed', historical: 'Historical lead', lead: 'Direct feed unverified'};
    function show(category) {
      const sources = directory.sources.filter(source => category === 'All' || source.category === category);
      for (const button of filters.querySelectorAll('button')) {
        button.setAttribute('aria-pressed', String(button.textContent === category));
      }
      $('source-count').textContent = `${sources.length} ${sources.length === 1 ? 'source' : 'sources'}`;
      $('source-directory').innerHTML = sources.map(source => `
        <article class="source-card">
          <span class="meta">${escape(source.category)} / ${escape(source.area)}</span>
          <h3><a href="${escape(source.url)}" target="_blank" rel="noopener noreferrer">${escape(source.name)} ↗</a></h3>
          <p>${escape(source.use)}</p>
          <span class="source-access">${escape(labels[source.access] || 'Check before use')}</span>
        </article>`).join('');
    }
    for (const category of categories) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = category;
      button.setAttribute('aria-pressed', 'false');
      button.addEventListener('click', () => show(category));
      filters.append(button);
    }
    show('All');
  })
  .catch(() => {
    $('source-directory').textContent = 'The source directory could not load. Refresh to try again.';
  });
