const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const audio = $('#audio');
const state = { dashboard: null, currentBook: null, currentCue: -1, audioContext: null, filters: null, ambience: null, focusTimer: null, focusRemaining: 25 * 60 };

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail || 'Request failed');
  }
  const type = response.headers.get('content-type') || '';
  return type.includes('application/json') ? response.json() : response.text();
}

function formatTime(seconds) {
  if (!Number.isFinite(seconds)) return '0:00';
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, '0')}`;
}

function progressPercent(book) {
  const p = book.progress || {};
  return p.duration > 0 ? Math.min(100, (p.seconds / p.duration) * 100) : 0;
}

function initials(title = 'Book') {
  return title.split(/\s+/).slice(0, 2).map(x => x[0]).join('').toUpperCase();
}

function card(book) {
  return `<article class="book-card" data-book="${book.id}"><div class="cover"><span>${initials(book.title)}</span></div><strong>${escapeHtml(book.title)}</strong><span>${escapeHtml(book.author)}</span><div class="progress-bar"><i style="width:${progressPercent(book)}%"></i></div></article>`;
}

function escapeHtml(value = '') {
  return String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

async function refreshDashboard() {
  state.dashboard = await api('/api/dashboard');
  const { books, continue_listening, playlists, follows, activity, preferences, voice_ready } = state.dashboard;
  $('#bookGrid').innerHTML = books.map(card).join('');
  $('#emptyLibrary').classList.toggle('hidden', books.length > 0);
  $('#libraryCount').textContent = `${books.length} book${books.length === 1 ? '' : 's'}`;
  $('#libraryList').innerHTML = books.map(book => `<div class="library-row" data-book="${book.id}"><div class="cover row-cover"><span>${initials(book.title)}</span></div><div><strong>${escapeHtml(book.title)}</strong><div class="muted">${escapeHtml(book.author)}</div></div><div class="muted">${escapeHtml(book.series || '—')}</div><div class="muted">${book.words.toLocaleString()} words</div><div>${book.has_audio ? '▶ Ready' : 'Text only'}</div></div>`).join('');
  $('#continueSection').classList.toggle('hidden', !continue_listening.length);
  $('#continueGrid').innerHTML = continue_listening.map(card).join('');
  $('#followAuthors').innerHTML = follows.authors.length ? follows.authors.map(x => `<span class="chip">${escapeHtml(x)}</span>`).join('') : '<span class="muted">Follow an author from a book.</span>';
  $('#followSeries').innerHTML = follows.series.length ? follows.series.map(x => `<span class="chip">${escapeHtml(x)}</span>`).join('') : '<span class="muted">Follow a series from a book.</span>';
  $('#activityFeed').innerHTML = activity.length ? activity.map(x => `<div class="activity-item"><strong>${escapeHtml(x.title)}</strong><span>${x.action}</span></div>`).join('') : '<span class="muted">Your private reading activity will appear here.</span>';
  $('#playlistGrid').innerHTML = playlists.length ? playlists.map(p => `<div class="playlist-card"><strong>${escapeHtml(p.name)}</strong><p class="muted">${p.books.length} books</p></div>`).join('') : '<span class="muted">No playlists yet.</span>';
  $('#voiceState').textContent = voice_ready ? '✓ Voice reference is configured locally.' : 'Voice reference has not been configured yet.';
  applyPreferences(preferences);
  wireBookLinks();
}

function wireBookLinks() {
  $$('[data-book]').forEach(el => el.onclick = () => openBook(el.dataset.book));
}

function switchView(name) {
  $$('.view').forEach(v => v.classList.remove('active-view'));
  $$('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.view === name));
  const view = $(`#${name}View`);
  if (view) view.classList.add('active-view');
  $('#pageTitle').textContent = ({home:'Good listening',library:'Your Library',following:'Following',playlists:'Playlists'})[name] || 'ListenLeaf';
}

async function openBook(id) {
  state.currentBook = await api(`/api/books/${id}`);
  const b = state.currentBook;
  $('#readerTitle').textContent = b.title;
  $('#readerAuthor').textContent = b.author;
  $('#readerWords').textContent = b.words.toLocaleString();
  $('#readerFormat').textContent = b.source_format.toUpperCase();
  $('#readerCover span').textContent = initials(b.title);
  $('#generateButton').textContent = b.has_audio ? 'Regenerate audiobook' : 'Generate audiobook';
  $('#generationStatus').textContent = b.has_audio ? 'Audio ready' : 'Text imported';
  renderReadalong(b);
  $$('.view').forEach(v => v.classList.remove('active-view'));
  $('#readerView').classList.add('active-view');
  if (b.has_audio) loadAudioBook(b, false);
}

function renderReadalong(book) {
  const cues = book.cues || [];
  if (cues.length) {
    $('#readalong').innerHTML = cues.map(c => `<div class="cue" data-index="${c.index}" data-start="${c.start}" data-end="${c.end}">${escapeHtml(c.text)}</div>`).join('');
  } else {
    const paragraphs = book.text.split(/\n\s*\n/).filter(Boolean);
    $('#readalong').innerHTML = paragraphs.map(p => `<div class="cue">${escapeHtml(p)}</div>`).join('');
  }
}

function ensureAudioGraph() {
  if (state.audioContext) return;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  state.audioContext = new Ctx();
  const source = state.audioContext.createMediaElementSource(audio);
  const bass = state.audioContext.createBiquadFilter(); bass.type = 'lowshelf'; bass.frequency.value = 180;
  const mids = state.audioContext.createBiquadFilter(); mids.type = 'peaking'; mids.frequency.value = 1200; mids.Q.value = 0.8;
  const treble = state.audioContext.createBiquadFilter(); treble.type = 'highshelf'; treble.frequency.value = 4800;
  source.connect(bass).connect(mids).connect(treble).connect(state.audioContext.destination);
  state.filters = { bass, mids, treble };
}

function setEq(values) {
  ensureAudioGraph();
  state.filters.bass.gain.value = values[0];
  state.filters.mids.gain.value = values[1];
  state.filters.treble.gain.value = values[2];
  $('#bass').value = values[0]; $('#mids').value = values[1]; $('#treble').value = values[2];
}

const eqPresets = { flat:[0,0,0], voice:[-2,4,2], warm:[4,1,-1], bright:[-1,1,4] };

function stopAmbience() {
  if (!state.ambience) return;
  state.ambience.sources.forEach(s => { try { s.stop(); } catch {} });
  state.ambience = null;
}

function startAmbience(kind) {
  stopAmbience();
  if (kind === 'off') return;
  ensureAudioGraph();
  const ctx = state.audioContext;
  const gain = ctx.createGain(); gain.gain.value = Number($('#ambienceLevel').value); gain.connect(ctx.destination);
  const sources = [];
  if (kind === 'brown') {
    const buffer = ctx.createBuffer(1, ctx.sampleRate * 4, ctx.sampleRate); const data = buffer.getChannelData(0); let last = 0;
    for (let i=0;i<data.length;i++){ const white=Math.random()*2-1; last=(last+0.02*white)/1.02; data[i]=last*3.5; }
    const src=ctx.createBufferSource(); src.buffer=buffer; src.loop=true; src.connect(gain); src.start(); sources.push(src);
  } else {
    const buffer = ctx.createBuffer(1, ctx.sampleRate * 3, ctx.sampleRate); const data = buffer.getChannelData(0);
    for (let i=0;i<data.length;i++) data[i]=(Math.random()*2-1)*0.28;
    const src=ctx.createBufferSource(); src.buffer=buffer; src.loop=true; const filter=ctx.createBiquadFilter(); filter.type='lowpass'; filter.frequency.value=1800; src.connect(filter).connect(gain); src.start(); sources.push(src);
  }
  state.ambience={sources,gain};
}

function loadAudioBook(book, autoplay = true) {
  audio.src = `/api/books/${book.id}/audio`;
  $('#player').classList.remove('hidden');
  $('#playerTitle').textContent = book.title;
  $('#playerAuthor').textContent = book.author;
  $('#playerCover span').textContent = initials(book.title);
  audio.onloadedmetadata = () => {
    const saved = book.progress || {};
    if (saved.seconds && saved.seconds < audio.duration - 5) audio.currentTime = saved.seconds;
    $('#duration').textContent = formatTime(audio.duration);
    if (autoplay) playAudio();
  };
}

async function playAudio() {
  ensureAudioGraph();
  if (state.audioContext.state === 'suspended') await state.audioContext.resume();
  await audio.play(); $('#playPause').textContent = '❚❚';
}

function activeCueFor(time) {
  const cues = state.currentBook?.cues || [];
  let lo=0, hi=cues.length-1, result=-1;
  while(lo<=hi){ const mid=(lo+hi)>>1; const c=cues[mid]; if(time<c.start) hi=mid-1; else {result=mid; lo=mid+1;} }
  return result;
}

function syncReadalong() {
  if (!state.currentBook?.cues?.length) return;
  const idx = activeCueFor(audio.currentTime);
  if (idx === state.currentCue) return;
  state.currentCue = idx;
  $$('.cue.active').forEach(el => el.classList.remove('active'));
  const el = $(`.cue[data-index="${idx}"]`);
  if (el) { el.classList.add('active'); el.scrollIntoView({behavior:document.body.classList.contains('reduce-motion')?'auto':'smooth',block:'center'}); }
}

let lastProgressSave = 0;
audio.ontimeupdate = () => {
  $('#currentTime').textContent = formatTime(audio.currentTime);
  $('#seek').value = audio.duration ? Math.round((audio.currentTime/audio.duration)*1000) : 0;
  syncReadalong();
  const now = Date.now();
  if (state.currentBook && now-lastProgressSave>5000) {
    lastProgressSave=now;
    api(`/api/books/${state.currentBook.id}/progress`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({seconds:audio.currentTime,duration:audio.duration||0})}).catch(()=>{});
  }
};
audio.onended = () => { $('#playPause').textContent='▶'; };

async function importSelected(file, title='', author='Unknown author', series='') {
  const fd = new FormData(); fd.append('file',file); fd.append('title',title); fd.append('author',author); fd.append('series',series);
  await api('/api/books/import',{method:'POST',body:fd}); await refreshDashboard();
}

async function startGeneration() {
  if (!state.currentBook) return;
  try {
    const result = await api(`/api/books/${state.currentBook.id}/generate`,{method:'POST'});
    $('#generationStatus').textContent='Queued…'; $('#generateButton').disabled=true;
    const poll=setInterval(async()=>{ try{ const job=await api(`/api/jobs/${result.job_id}`); $('#generationStatus').textContent=job.status==='running'?'Generating audio…':job.status; if(job.status==='completed'){clearInterval(poll);$('#generateButton').disabled=false;state.currentBook=await api(`/api/books/${state.currentBook.id}`);renderReadalong(state.currentBook);loadAudioBook(state.currentBook,false);$('#generationStatus').textContent=`Ready · RTF ${job.aggregate_rtf}`;refreshDashboard();} if(job.status==='failed'){clearInterval(poll);$('#generateButton').disabled=false;$('#generationStatus').textContent=job.error||'Generation failed';} }catch{} },2500);
  } catch (err) { $('#generationStatus').textContent=err.message; }
}

function applyPreferences(p={}) {
  if(p.playback_rate) { audio.playbackRate=Number(p.playback_rate); $('#speedSelect').value=String(p.playback_rate); }
  document.body.classList.toggle('large-text',!!p.large_text); $('#largeText').checked=!!p.large_text;
  document.body.classList.toggle('reduce-motion',!!p.reduce_motion); $('#reduceMotion').checked=!!p.reduce_motion;
  if (p.eq_preset && eqPresets[p.eq_preset]) $$('.preset').forEach(b=>b.classList.toggle('active',b.dataset.eq===p.eq_preset));
}

function savePrefs(extra) { return api('/api/preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(extra)}).catch(()=>{}); }

$$('.nav-item').forEach(n=>n.onclick=()=>switchView(n.dataset.view));
$('#backFromReader').onclick=()=>switchView('library'); $('#readerShortcut').onclick=()=>{ if(state.currentBook) openBook(state.currentBook.id); };
$('#importButton').onclick=()=>$('#importDialog').showModal();
$('#settingsButton').onclick=()=>$('#settingsDialog').showModal();
$('#confirmImport').onclick=async(e)=>{e.preventDefault();const f=$('#dialogBookFile').files[0];if(!f)return;await importSelected(f,$('#importTitle').value,$('#importAuthor').value||'Unknown author',$('#importSeries').value);$('#importDialog').close();$('#importForm').reset();};
$('#bookFile').onchange=async e=>{if(e.target.files[0])await importSelected(e.target.files[0]);e.target.value='';};
$('#saveVoice').onclick=async(e)=>{e.preventDefault();const f=$('#voiceReference').files[0];const t=$('#voiceTranscript').value;if(!f||!t.trim()){ $('#voiceState').textContent='Choose audio and enter the exact transcript.';return;}const fd=new FormData();fd.append('audio',f);fd.append('transcript',t);try{await api('/api/voice-reference',{method:'POST',body:fd});$('#voiceState').textContent='✓ Voice saved locally.';await refreshDashboard();}catch(err){$('#voiceState').textContent=err.message;}};
$('#generateButton').onclick=startGeneration;
$('#playPause').onclick=()=>audio.paused?playAudio():(audio.pause(),$('#playPause').textContent='▶');
$('#rewind').onclick=()=>audio.currentTime=Math.max(0,audio.currentTime-15); $('#forward').onclick=()=>audio.currentTime=Math.min(audio.duration||Infinity,audio.currentTime+15);
$('#seek').oninput=e=>{if(audio.duration)audio.currentTime=(Number(e.target.value)/1000)*audio.duration;}; $('#volume').oninput=e=>audio.volume=Number(e.target.value);
$('#speedSelect').onchange=e=>{audio.playbackRate=Number(e.target.value);savePrefs({playback_rate:audio.playbackRate});};
['bass','mids','treble'].forEach((id,i)=>$(`#${id}`).oninput=()=>{ensureAudioGraph();state.filters[id].gain.value=Number($(`#${id}`).value);$$('.preset').forEach(b=>b.classList.remove('active'));});
$$('.preset').forEach(b=>b.onclick=()=>{$$('.preset').forEach(x=>x.classList.remove('active'));b.classList.add('active');setEq(eqPresets[b.dataset.eq]);savePrefs({eq_preset:b.dataset.eq});});
$$('.ambience').forEach(b=>b.onclick=()=>{$$('.ambience').forEach(x=>x.classList.remove('active'));b.classList.add('active');startAmbience(b.dataset.ambience);savePrefs({ambience:b.dataset.ambience});});
$('#ambienceLevel').oninput=()=>{if(state.ambience)state.ambience.gain.gain.value=Number($('#ambienceLevel').value);};
$('#largeText').onchange=e=>{document.body.classList.toggle('large-text',e.target.checked);savePrefs({large_text:e.target.checked});}; $('#reduceMotion').onchange=e=>{document.body.classList.toggle('reduce-motion',e.target.checked);savePrefs({reduce_motion:e.target.checked});};
$('#focusLine').onclick=()=>$('#readalong').classList.toggle('focus-line-mode');
$('#textPlus').onclick=()=>{const v=parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--reader-size'))||1.2;document.documentElement.style.setProperty('--reader-size',`${Math.min(2,v+.1)}rem`);}; $('#textMinus').onclick=()=>{const v=parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--reader-size'))||1.2;document.documentElement.style.setProperty('--reader-size',`${Math.max(.9,v-.1)}rem`);};
$('#newPlaylist').onclick=async()=>{const name=prompt('Playlist name');if(name){await api('/api/playlists',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});refreshDashboard();}};
$('#addPlaylist').onclick=async()=>{const ps=state.dashboard?.playlists||[];if(!ps.length){alert('Create a playlist first.');return;}const name=prompt(`Add to playlist:\n${ps.map((p,i)=>`${i+1}. ${p.name}`).join('\n')}\nEnter number:`);const p=ps[Number(name)-1];if(p&&state.currentBook){await api(`/api/playlists/${p.id}/books/${state.currentBook.id}`,{method:'POST'});refreshDashboard();}};
$('#followAuthor').onclick=async()=>{if(!state.currentBook)return;await api('/api/follows',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'authors',value:state.currentBook.author,follow:true})});$('#followAuthor').textContent='♥ Following';refreshDashboard();};
$('#sleepButton').onclick=()=>{const mins=Number(prompt('Stop playback after how many minutes?','30'));if(mins>0)setTimeout(()=>audio.pause(),mins*60000);};
$('#focusToggle').onclick=()=>{if(state.focusTimer){clearInterval(state.focusTimer);state.focusTimer=null;$('#focusToggle span').textContent='Resume focus sprint';return;}state.focusTimer=setInterval(()=>{state.focusRemaining--;$('#focusClock').textContent=`${String(Math.floor(state.focusRemaining/60)).padStart(2,'0')}:${String(state.focusRemaining%60).padStart(2,'0')}`;if(state.focusRemaining<=0){clearInterval(state.focusTimer);state.focusTimer=null;state.focusRemaining=5*60;$('#focusToggle span').textContent='Break time';}},1000);$('#focusToggle span').textContent='Pause focus sprint';};

refreshDashboard().catch(err=>{console.error(err);$('#pageTitle').textContent='Could not load local library';});