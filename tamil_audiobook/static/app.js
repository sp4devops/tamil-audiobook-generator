const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const audio = $('#audio');

const enhancementLink = document.createElement('link');
enhancementLink.rel = 'stylesheet';
enhancementLink.href = '/static/enhancements.css';
document.head.appendChild(enhancementLink);

const state = {
  dashboard: null,
  currentBook: null,
  currentCue: -1,
  audioContext: null,
  filters: null,
  ambience: null,
  focusTimer: null,
  focusRemaining: 1500,
  repeatMode: 'off',
  shuffle: false,
  mutedVolume: 1,
  sleepTimer: null,
  confirmAction: null,
};

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail || 'Request failed');
  }
  const type = response.headers.get('content-type') || '';
  return type.includes('application/json') ? response.json() : response.text();
}
const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

function esc(value = '') {
  return String(value).replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
}
function clock(seconds) {
  if (!Number.isFinite(Number(seconds))) return '—';
  let value = Math.max(0, Math.round(Number(seconds)));
  const hours = Math.floor(value / 3600);
  value %= 3600;
  const minutes = Math.floor(value / 60);
  const secs = value % 60;
  return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}` : `${minutes}:${String(secs).padStart(2, '0')}`;
}
function durationLabel(seconds) {
  const value = Math.max(0, Math.round(Number(seconds) || 0));
  if (value < 60) return `${value}s`;
  const hours = Math.floor(value / 3600);
  const minutes = Math.round((value % 3600) / 60);
  return hours ? `${hours}h ${minutes}m` : `${minutes} min`;
}
function bytes(n = 0) {
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1073741824) return `${(n / 1048576).toFixed(1)} MB`;
  return `${(n / 1073741824).toFixed(2)} GB`;
}
function initials(title = 'Book') {
  return title.split(/\s+/).slice(0, 2).map(x => x[0]).join('').toUpperCase();
}
function progressPercent(book) {
  const p = book.progress || {};
  return p.duration > 0 ? Math.min(100, p.seconds / p.duration * 100) : 0;
}
function knownDuration(book) {
  const p = book.progress || {};
  return p.duration > 0 ? durationLabel(p.duration) : (book.has_audio ? 'Audio ready' : 'Text only');
}

function card(book) {
  return `<article class="book-card" data-book="${book.id}">
    <div class="cover"><span>${initials(book.title)}</span></div>
    ${book.has_audio ? `<button class="card-play" data-play-book="${book.id}" aria-label="Play ${esc(book.title)}" title="Play audiobook">▶</button>` : ''}
    <strong>${esc(book.title)}</strong>
    <span>${esc(book.author)}</span>
    <span class="book-meta-line"><small>${book.has_audio ? 'Ready' : book.source_format.toUpperCase()}</small><small class="book-duration">${knownDuration(book)}</small></span>
    <div class="progress-bar"><i style="width:${progressPercent(book)}%"></i></div>
  </article>`;
}

function confirmAction(title, message, label = 'Confirm') {
  return new Promise(resolve => {
    state.confirmAction = () => resolve(true);
    $('#confirmTitle').textContent = title;
    $('#confirmMessage').textContent = message;
    $('#confirmYes').textContent = label;
    $('#confirmDialog').showModal();
    $('#confirmCancel').onclick = () => {
      $('#confirmDialog').close();
      state.confirmAction = null;
      resolve(false);
    };
    $('#confirmYes').onclick = () => {
      $('#confirmDialog').close();
      const fn = state.confirmAction;
      state.confirmAction = null;
      if (fn) fn();
    };
  });
}

async function refresh() {
  state.dashboard = await api('/api/dashboard');
  const d = state.dashboard;
  $('#bookGrid').innerHTML = d.books.map(card).join('');
  $('#emptyLibrary').classList.toggle('hidden', d.books.length > 0);
  $('#libraryCount').textContent = `${d.books.length} book${d.books.length === 1 ? '' : 's'}`;
  $('#libraryList').innerHTML = d.books.map(book => `<div class="library-row" data-book="${book.id}">
      <div class="cover row-cover"><span>${initials(book.title)}</span></div>
      <div><strong>${esc(book.title)}</strong><div class="muted">${esc(book.author)}</div></div>
      <div class="muted">${esc(book.series || '—')}</div>
      <div class="muted">${book.words.toLocaleString()} words</div>
      <div>${book.has_audio ? `<button class="row-play" data-play-book="${book.id}" title="Play">▶</button>` : 'Text only'}</div>
    </div>`).join('');
  $('#continueSection').classList.toggle('hidden', !d.continue_listening.length);
  $('#continueGrid').innerHTML = d.continue_listening.map(card).join('');
  $('#followAuthors').innerHTML = d.follows.authors.length ? d.follows.authors.map(x => `<button class="chip" data-unfollow-author="${esc(x)}">${esc(x)} ×</button>`).join('') : '<span class="muted">Follow an author from a book.</span>';
  $('#followSeries').innerHTML = d.follows.series.length ? d.follows.series.map(x => `<button class="chip" data-unfollow-series="${esc(x)}">${esc(x)} ×</button>`).join('') : '<span class="muted">Follow a series from a book.</span>';
  $('#activityFeed').innerHTML = d.activity.length ? d.activity.map(x => `<div class="activity-item"><strong>${esc(x.title)}</strong><span>${esc(x.action)}</span></div>`).join('') : '<span class="muted">No local activity.</span>';
  $('#playlistGrid').innerHTML = d.playlists.length ? d.playlists.map(p => `<article class="playlist-card" data-playlist="${p.id}"><strong>${esc(p.name)}</strong><p class="muted">${p.books.length} books</p><span class="muted">Edit playlist →</span></article>`).join('') : '<span class="muted">No playlists yet.</span>';
  $('#voiceState').textContent = d.voice_source === 'custom' ? '✓ Custom local voice override is active.' : d.voice_source === 'accepted-c-default' ? '✓ Accepted-C generated mixed voice is active by default.' : 'No voice reference is available.';
  $('#storageState').textContent = `Library ${bytes(d.storage.library_bytes)} · Generated audio ${bytes(d.storage.generated_bytes)} · App cache ${bytes(d.storage.app_cache_bytes)}`;
  applyPreferences(d.preferences);
  wireDynamic();
}

function wireDynamic() {
  $$('[data-book]').forEach(el => el.onclick = event => {
    if (event.target.closest('[data-play-book]')) return;
    openBook(el.dataset.book);
  });
  $$('[data-play-book]').forEach(button => button.onclick = async event => {
    event.stopPropagation();
    await openBook(button.dataset.playBook);
    loadBook(state.currentBook, true);
  });
  $$('[data-playlist]').forEach(el => el.onclick = () => openPlaylist(el.dataset.playlist));
  $$('[data-unfollow-author]').forEach(el => el.onclick = async () => {
    await api('/api/follows', json('POST', { kind: 'authors', value: el.dataset.unfollowAuthor, follow: false }));
    await refresh();
  });
  $$('[data-unfollow-series]').forEach(el => el.onclick = async () => {
    await api('/api/follows', json('POST', { kind: 'series', value: el.dataset.unfollowSeries, follow: false }));
    await refresh();
  });
}

function switchView(name) {
  $$('.view').forEach(view => view.classList.remove('active-view'));
  $$('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === name));
  $(`#${name}View`)?.classList.add('active-view');
  $('#pageTitle').textContent = ({ home: 'Good listening', library: 'Your Library', following: 'Following', playlists: 'Playlists' })[name] || 'ListenLeaf';
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
  $('#generationStatus').textContent = b.has_audio ? 'Audio ready' : 'Text imported · ready to generate';
  $('#clearAudio').disabled = !b.has_audio;
  $('#readerPlayButton').classList.toggle('hidden', !b.has_audio);
  const estimate = b.estimate || {};
  $('#estimatedAudioDuration').textContent = durationLabel(estimate.audio_seconds || 0);
  $('#estimatedGenerationTime').textContent = durationLabel(estimate.generation_seconds || 0);
  $('#readerDuration').textContent = durationLabel(b.audio_seconds || estimate.audio_seconds || 0);
  $('#readerChunks').textContent = estimate.chunks || '—';
  hideGenerationProgress();
  renderReadalong(b);
  $$('.view').forEach(view => view.classList.remove('active-view'));
  $('#readerView').classList.add('active-view');
  if (b.has_audio) loadBook(b, false);
  updateFollowButton();
}

function renderReadalong(book) {
  const cues = book.cues || [];
  $('#readalong').innerHTML = cues.length ? cues.map(c => `<div class="cue" data-index="${c.index}" data-start="${c.start}" data-end="${c.end}">${esc(c.text)}</div>`).join('') : book.text.split(/\n\s*\n/).filter(Boolean).map(p => `<div class="cue">${esc(p)}</div>`).join('');
}

function queue() {
  return state.dashboard?.books?.filter(book => book.has_audio) || [];
}
function adjacent(direction) {
  const q = queue();
  if (!q.length) return null;
  let index = q.findIndex(book => book.id === state.currentBook?.id);
  if (index < 0) index = 0;
  if (state.shuffle) {
    let next = index;
    while (q.length > 1 && next === index) next = Math.floor(Math.random() * q.length);
    return q[next];
  }
  return q[(index + direction + q.length) % q.length];
}
async function playAdjacent(direction, autoplay = true) {
  const book = adjacent(direction);
  if (!book) return;
  await openBook(book.id);
  loadBook(state.currentBook, autoplay);
}

function loadBook(book, autoplay = true) {
  audio.src = `/api/books/${book.id}/audio`;
  $('#player').classList.remove('hidden');
  $('#playerTitle').textContent = book.title;
  $('#playerAuthor').textContent = book.author;
  $('#playerCover span').textContent = initials(book.title);
  audio.onloadedmetadata = () => {
    const saved = book.progress || {};
    if (saved.seconds && saved.seconds < audio.duration - 5) audio.currentTime = saved.seconds;
    $('#duration').textContent = clock(audio.duration);
    $('#readerDuration').textContent = durationLabel(audio.duration);
    if (autoplay) playAudio();
  };
}

function ensureAudioGraph() {
  if (state.audioContext) return;
  const Context = window.AudioContext || window.webkitAudioContext;
  state.audioContext = new Context();
  const source = state.audioContext.createMediaElementSource(audio);
  const bass = state.audioContext.createBiquadFilter(); bass.type = 'lowshelf'; bass.frequency.value = 180;
  const mids = state.audioContext.createBiquadFilter(); mids.type = 'peaking'; mids.frequency.value = 1200; mids.Q.value = 0.8;
  const treble = state.audioContext.createBiquadFilter(); treble.type = 'highshelf'; treble.frequency.value = 4800;
  source.connect(bass).connect(mids).connect(treble).connect(state.audioContext.destination);
  state.filters = { bass, mids, treble };
}
async function playAudio() {
  ensureAudioGraph();
  if (state.audioContext.state === 'suspended') await state.audioContext.resume();
  await audio.play();
  $('#playPause').textContent = '❚❚';
}
function setEq(values) {
  ensureAudioGraph();
  state.filters.bass.gain.value = values[0];
  state.filters.mids.gain.value = values[1];
  state.filters.treble.gain.value = values[2];
  $('#bass').value = values[0]; $('#mids').value = values[1]; $('#treble').value = values[2];
}
const eq = { flat: [0, 0, 0], voice: [-2, 4, 2], warm: [4, 1, -1], bright: [-1, 1, 4] };

function stopAmbience() {
  if (!state.ambience) return;
  state.ambience.sources.forEach(source => { try { source.stop(); } catch {} });
  state.ambience = null;
}
function startAmbience(kind) {
  stopAmbience();
  if (kind === 'off') return;
  ensureAudioGraph();
  const context = state.audioContext;
  const gain = context.createGain();
  gain.gain.value = Number($('#ambienceLevel').value);
  gain.connect(context.destination);
  const buffer = context.createBuffer(1, context.sampleRate * 4, context.sampleRate);
  const data = buffer.getChannelData(0);
  let last = 0;
  for (let i = 0; i < data.length; i++) {
    if (kind === 'brown') {
      const white = Math.random() * 2 - 1;
      last = (last + 0.02 * white) / 1.02;
      data[i] = last * 3.5;
    } else data[i] = (Math.random() * 2 - 1) * 0.2;
  }
  const source = context.createBufferSource();
  source.buffer = buffer; source.loop = true;
  if (kind === 'rain') {
    const filter = context.createBiquadFilter(); filter.type = 'lowpass'; filter.frequency.value = 1800;
    source.connect(filter).connect(gain);
  } else source.connect(gain);
  source.start();
  state.ambience = { sources: [source], gain };
}

function cueIndex(time) {
  const cues = state.currentBook?.cues || [];
  let low = 0, high = cues.length - 1, result = -1;
  while (low <= high) {
    const mid = (low + high) >> 1;
    if (time < cues[mid].start) high = mid - 1;
    else { result = mid; low = mid + 1; }
  }
  return result;
}
function syncReadalong() {
  if (!state.currentBook?.cues?.length) return;
  const index = cueIndex(audio.currentTime);
  if (index === state.currentCue) return;
  state.currentCue = index;
  $$('.cue.active').forEach(el => el.classList.remove('active'));
  const active = $(`.cue[data-index="${index}"]`);
  if (active) {
    active.classList.add('active');
    active.scrollIntoView({ behavior: document.body.classList.contains('reduce-motion') ? 'auto' : 'smooth', block: 'center' });
  }
}

let lastSave = 0;
audio.ontimeupdate = () => {
  $('#currentTime').textContent = clock(audio.currentTime);
  $('#seek').value = audio.duration ? Math.round(audio.currentTime / audio.duration * 1000) : 0;
  syncReadalong();
  if (state.currentBook && Date.now() - lastSave > 5000) {
    lastSave = Date.now();
    api(`/api/books/${state.currentBook.id}/progress`, json('POST', { seconds: audio.currentTime, duration: audio.duration || 0 })).catch(() => {});
  }
};
audio.onended = async () => {
  $('#playPause').textContent = '▶';
  if (state.repeatMode === 'one') { audio.currentTime = 0; playAudio(); }
  else if (state.repeatMode === 'all' || state.shuffle) await playAdjacent(1, true);
};

function generationStage(stage) {
  return ({ queued: 'Queued', loading_model: 'Loading voice model', encoding_voice: 'Preparing accepted voice', synthesizing: 'Generating audio', exporting: 'Exporting MP3', ready: 'Ready' })[stage] || stage || 'Working';
}
function showGenerationProgress(job) {
  $('#generationProgress').classList.remove('hidden');
  const percent = Math.max(0, Math.min(100, Number(job.percent || 0)));
  $('#generationBar').value = percent;
  $('#generationPercent').textContent = `${Math.round(percent)}%`;
  const chunkText = job.total_chunks ? `${generationStage(job.stage)} · chunk ${job.completed_chunks || 0}/${job.total_chunks}` : generationStage(job.stage);
  $('#generationChunk').textContent = chunkText;
  $('#generationElapsed').textContent = `Elapsed ${clock(job.elapsed_seconds || 0)}`;
  $('#generationEta').textContent = `ETA ${job.estimated_remaining_seconds == null ? '—' : clock(job.estimated_remaining_seconds)}`;
  $('#generationStatus').textContent = chunkText;
}
function hideGenerationProgress() {
  $('#generationProgress').classList.add('hidden');
  $('#generationBar').value = 0;
}

async function generate() {
  if (!state.currentBook) return;
  try {
    const result = await api(`/api/books/${state.currentBook.id}/generate`, { method: 'POST' });
    $('#generateButton').disabled = true;
    showGenerationProgress({ ...result.estimate, stage: 'queued', percent: 0, completed_chunks: 0, total_chunks: result.estimate.chunks, estimated_remaining_seconds: result.estimate.generation_seconds, elapsed_seconds: 0 });
    const poll = setInterval(async () => {
      try {
        const job = await api(`/api/jobs/${result.job_id}`);
        showGenerationProgress(job);
        if (job.status === 'completed') {
          clearInterval(poll);
          $('#generateButton').disabled = false;
          state.currentBook = await api(`/api/books/${state.currentBook.id}`);
          renderReadalong(state.currentBook);
          loadBook(state.currentBook, false);
          $('#readerPlayButton').classList.remove('hidden');
          $('#clearAudio').disabled = false;
          $('#readerDuration').textContent = durationLabel(job.audio_seconds);
          $('#generationStatus').textContent = `Ready · ${durationLabel(job.audio_seconds)} · RTF ${job.aggregate_rtf}`;
          showGenerationProgress({ ...job, percent: 100, estimated_remaining_seconds: 0 });
          await refresh();
        } else if (job.status === 'failed') {
          clearInterval(poll);
          $('#generateButton').disabled = false;
          $('#generationStatus').textContent = job.error || 'Generation failed';
          $('#generationChunk').textContent = 'Generation failed';
        }
      } catch {}
    }, 1000);
  } catch (error) {
    $('#generateButton').disabled = false;
    $('#generationStatus').textContent = error.message;
  }
}

function applyTheme(value) {
  document.documentElement.dataset.theme = value || 'midnight';
  $('#themeSelect').value = value || 'midnight';
}
function applyPreferences(p = {}) {
  if (p.playback_rate) {
    audio.playbackRate = Number(p.playback_rate);
    $('#speedSelect').value = String(p.playback_rate);
    $('#speedButton').textContent = `${p.playback_rate}×`;
  }
  state.repeatMode = p.repeat_mode || 'off';
  state.shuffle = !!p.shuffle;
  $('#repeatButton').classList.toggle('active', state.repeatMode !== 'off');
  $('#repeatButton').textContent = state.repeatMode === 'one' ? '↻1' : '↻';
  $('#shuffleButton').classList.toggle('active', state.shuffle);
  $('#skipSelect').value = String(p.skip_seconds || 15);
  document.body.classList.toggle('large-text', !!p.large_text);
  $('#largeText').checked = !!p.large_text;
  document.body.classList.toggle('reduce-motion', !!p.reduce_motion);
  $('#reduceMotion').checked = !!p.reduce_motion;
  applyTheme(p.theme || 'midnight');
  if (p.eq_preset && eq[p.eq_preset]) $$('.preset').forEach(button => button.classList.toggle('active', button.dataset.eq === p.eq_preset));
}
function savePreferences(payload) { return api('/api/preferences', json('POST', payload)).catch(() => {}); }

function updateFollowButton() {
  const author = state.currentBook?.author || '';
  const following = state.dashboard?.follows?.authors?.includes(author);
  $('#followAuthor').textContent = following ? '♥ Following' : '♡ Follow author';
  $('#favoriteButton').textContent = following ? '♥' : '♡';
}
async function toggleFollow() {
  if (!state.currentBook) return;
  const author = state.currentBook.author;
  const following = state.dashboard.follows.authors.includes(author);
  await api('/api/follows', json('POST', { kind: 'authors', value: author, follow: !following }));
  await refresh(); updateFollowButton();
}

async function openPlaylist(id = '', includeCurrent = false) {
  const playlist = id ? state.dashboard.playlists.find(x => x.id === id) : null;
  $('#playlistDialogTitle').textContent = playlist ? 'Edit playlist' : 'New playlist';
  $('#playlistId').value = playlist?.id || '';
  $('#playlistName').value = playlist?.name || '';
  $('#deletePlaylist').classList.toggle('hidden', !playlist);
  const selected = new Set(playlist?.books || []);
  if (!playlist && includeCurrent && state.currentBook) selected.add(state.currentBook.id);
  $('#playlistBooks').innerHTML = state.dashboard.books.length ? state.dashboard.books.map(book => `<label><input type="checkbox" value="${book.id}" ${selected.has(book.id) ? 'checked' : ''}> <span>${esc(book.title)} · ${esc(book.author)}</span></label>`).join('') : '<span class="muted">Import books first.</span>';
  $('#playlistDialog').showModal();
}
function editBookDialog() {
  const book = state.currentBook;
  if (!book) return;
  $('#editBookTitle').value = book.title;
  $('#editBookAuthor').value = book.author;
  $('#editBookSeries').value = book.series || '';
  $('#editBookDialog').showModal();
}
async function refreshCurrent() {
  if (state.currentBook) {
    const id = state.currentBook.id;
    await refresh();
    await openBook(id);
  } else await refresh();
}

function cycleSpeed() {
  const values = [.75, .9, 1, 1.1, 1.25, 1.5, 1.75, 2];
  let index = values.findIndex(v => Math.abs(v - audio.playbackRate) < .001);
  index = (index + 1) % values.length;
  audio.playbackRate = values[index];
  $('#speedSelect').value = String(values[index]);
  $('#speedButton').textContent = `${values[index]}×`;
  savePreferences({ playback_rate: values[index] });
}
function cycleSleep() {
  const label = $('#sleepButton').textContent;
  const minutes = label.includes('Off') ? 15 : label.includes('15') ? 30 : label.includes('30') ? 60 : 0;
  clearTimeout(state.sleepTimer);
  state.sleepTimer = null;
  $('#sleepButton').textContent = minutes ? `☾ ${minutes}m` : '☾ Off';
  if (minutes) state.sleepTimer = setTimeout(() => {
    audio.pause(); $('#playPause').textContent = '▶'; $('#sleepButton').textContent = '☾ Off';
  }, minutes * 60000);
}

function setNavCollapsed(collapsed) {
  document.body.classList.toggle('nav-collapsed', collapsed);
  localStorage.setItem('listenleaf-nav-collapsed', collapsed ? '1' : '0');
  $('#toggleNav').textContent = collapsed ? '☰ Show' : '☰';
}
function toggleNav() { setNavCollapsed(!document.body.classList.contains('nav-collapsed')); }
function setSoundCollapsed(collapsed) {
  document.body.classList.toggle('sound-collapsed', collapsed);
  localStorage.setItem('listenleaf-sound-collapsed', collapsed ? '1' : '0');
  $('#toggleSoundPanel').textContent = collapsed ? '◧ Show sound' : '◧ Sound';
}
function toggleSound() { setSoundCollapsed(!document.body.classList.contains('sound-collapsed')); }
async function toggleFullscreen() {
  try {
    if (!document.fullscreenElement) await document.documentElement.requestFullscreen();
    else await document.exitFullscreen();
  } catch {
    document.body.classList.toggle('fullscreen-reading');
  }
}
document.addEventListener('fullscreenchange', () => {
  const active = !!document.fullscreenElement;
  document.body.classList.toggle('fullscreen-reading', active);
  $('#fullscreenButton').textContent = active ? '⛶ Exit fullscreen' : '⛶ Fullscreen';
});

function startFocusTimer() {
  if (state.focusTimer) {
    clearInterval(state.focusTimer); state.focusTimer = null;
    $('#focusToggle span').textContent = 'Resume focus sprint';
    return;
  }
  if (state.focusRemaining <= 0) state.focusRemaining = 1500;
  $('#focusToggle span').textContent = 'Pause focus sprint';
  state.focusTimer = setInterval(() => {
    state.focusRemaining--;
    $('#focusClock').textContent = clock(state.focusRemaining);
    if (state.focusRemaining <= 0) {
      clearInterval(state.focusTimer); state.focusTimer = null;
      $('#focusToggle span').textContent = 'Focus sprint complete';
    }
  }, 1000);
}

$$('.nav-item').forEach(item => item.onclick = () => switchView(item.dataset.view));
$$('[data-close]').forEach(button => button.onclick = () => document.getElementById(button.dataset.close)?.close());
$('#toggleNav').onclick = toggleNav;
$('#settingsToggleNav').onclick = toggleNav;
$('#toggleSoundPanel').onclick = toggleSound;
$('#settingsToggleSound').onclick = toggleSound;
$('#fullscreenButton').onclick = toggleFullscreen;
$('#fullscreenToolbar').onclick = toggleFullscreen;
$('#playerFullscreen').onclick = toggleFullscreen;
$('#backFromReader').onclick = () => switchView('library');
$('#readerShortcut').onclick = () => { if (state.currentBook) openBook(state.currentBook.id); };
$('#importButton').onclick = () => $('#importDialog').showModal();
$('#settingsButton').onclick = () => $('#settingsDialog').showModal();
$('#focusToggle').onclick = startFocusTimer;
$('#generateButton').onclick = generate;
$('#readerPlayButton').onclick = () => { if (state.currentBook?.has_audio) loadBook(state.currentBook, true); };
$('#followAuthor').onclick = toggleFollow;
$('#favoriteButton').onclick = toggleFollow;
$('#addPlaylist').onclick = () => openPlaylist('', true);
$('#editBook').onclick = editBookDialog;

$('#importForm').onsubmit = async event => {
  event.preventDefault();
  const file = $('#dialogBookFile').files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file); fd.append('title', $('#importTitle').value); fd.append('author', $('#importAuthor').value || 'Unknown author'); fd.append('series', $('#importSeries').value);
  await api('/api/books/import', { method: 'POST', body: fd });
  $('#importDialog').close(); $('#importForm').reset(); await refresh();
};
$('#editBookForm').onsubmit = async event => {
  event.preventDefault();
  if (!state.currentBook) return;
  await api(`/api/books/${state.currentBook.id}`, json('PATCH', { title: $('#editBookTitle').value, author: $('#editBookAuthor').value, series: $('#editBookSeries').value }));
  $('#editBookDialog').close(); await refreshCurrent();
};
$('#newPlaylist').onclick = () => openPlaylist();
$('#playlistForm').onsubmit = async event => {
  event.preventDefault();
  const id = $('#playlistId').value;
  const books = $$('#playlistBooks input:checked').map(input => input.value);
  const body = { name: $('#playlistName').value, books };
  if (id) await api(`/api/playlists/${id}`, json('PATCH', body));
  else {
    const created = await api('/api/playlists', json('POST', { name: body.name }));
    await api(`/api/playlists/${created.id}`, json('PATCH', { books }));
  }
  $('#playlistDialog').close(); await refresh();
};
$('#deletePlaylist').onclick = async () => {
  const id = $('#playlistId').value;
  if (!id || !(await confirmAction('Delete playlist?', 'Books stay in your library.', 'Delete playlist'))) return;
  await api(`/api/playlists/${id}`, { method: 'DELETE' }); $('#playlistDialog').close(); await refresh();
};

$('#clearAudio').onclick = async () => {
  if (!state.currentBook || !(await confirmAction('Clear generated audio?', 'The imported book text will be kept.', 'Clear audio'))) return;
  audio.pause(); audio.removeAttribute('src'); $('#player').classList.add('hidden');
  await api(`/api/books/${state.currentBook.id}/audio`, { method: 'DELETE' }); await refreshCurrent();
};
$('#resetBookProgress').onclick = async () => {
  if (!state.currentBook) return;
  await api(`/api/books/${state.currentBook.id}/progress`, { method: 'DELETE' }); await refreshCurrent();
};
$('#deleteBook').onclick = async () => {
  if (!state.currentBook || !(await confirmAction('Delete book?', 'This deletes its imported source copy, text, generated audio and progress.', 'Delete book'))) return;
  const id = state.currentBook.id; audio.pause();
  await api(`/api/books/${id}`, { method: 'DELETE' }); state.currentBook = null; $('#player').classList.add('hidden'); await refresh(); switchView('library');
};

$('#playPause').onclick = () => audio.paused ? playAudio() : (audio.pause(), $('#playPause').textContent = '▶');
$('#previousButton').onclick = () => playAdjacent(-1, true);
$('#nextButton').onclick = () => playAdjacent(1, true);
$('#rewind').onclick = () => audio.currentTime = Math.max(0, audio.currentTime - Number($('#skipSelect').value || 15));
$('#forward').onclick = () => audio.currentTime = Math.min(audio.duration || Infinity, audio.currentTime + Number($('#skipSelect').value || 15));
$('#seek').oninput = event => { if (audio.duration) audio.currentTime = Number(event.target.value) / 1000 * audio.duration; };
$('#volume').oninput = event => { audio.volume = Number(event.target.value); if (audio.volume > 0) state.mutedVolume = audio.volume; $('#muteButton').textContent = audio.volume ? '🔊' : '🔇'; };
$('#muteButton').onclick = () => {
  if (audio.volume > 0) { state.mutedVolume = audio.volume; audio.volume = 0; $('#volume').value = 0; $('#muteButton').textContent = '🔇'; }
  else { audio.volume = state.mutedVolume || 1; $('#volume').value = audio.volume; $('#muteButton').textContent = '🔊'; }
};
$('#speedButton').onclick = cycleSpeed;
$('#sleepButton').onclick = cycleSleep;
$('#speedSelect').onchange = event => { audio.playbackRate = Number(event.target.value); $('#speedButton').textContent = `${event.target.value}×`; savePreferences({ playback_rate: audio.playbackRate }); };
$('#skipSelect').onchange = event => { const seconds = Number(event.target.value); $('#rewind').textContent = `↶${seconds}`; $('#forward').textContent = `${seconds}↷`; savePreferences({ skip_seconds: seconds }); };
$('#shuffleButton').onclick = () => { state.shuffle = !state.shuffle; $('#shuffleButton').classList.toggle('active', state.shuffle); savePreferences({ shuffle: state.shuffle }); };
$('#repeatButton').onclick = () => { state.repeatMode = state.repeatMode === 'off' ? 'all' : state.repeatMode === 'all' ? 'one' : 'off'; $('#repeatButton').classList.toggle('active', state.repeatMode !== 'off'); $('#repeatButton').textContent = state.repeatMode === 'one' ? '↻1' : '↻'; savePreferences({ repeat_mode: state.repeatMode }); };

['bass', 'mids', 'treble'].forEach(id => $(`#${id}`).oninput = () => { ensureAudioGraph(); state.filters[id].gain.value = Number($(`#${id}`).value); $$('.preset').forEach(b => b.classList.remove('active')); });
$$('.preset').forEach(button => button.onclick = () => { $$('.preset').forEach(b => b.classList.remove('active')); button.classList.add('active'); setEq(eq[button.dataset.eq]); savePreferences({ eq_preset: button.dataset.eq }); });
$$('.ambience').forEach(button => button.onclick = () => { $$('.ambience').forEach(b => b.classList.remove('active')); button.classList.add('active'); startAmbience(button.dataset.ambience); savePreferences({ ambience: button.dataset.ambience }); });
$('#ambienceLevel').oninput = event => { if (state.ambience) state.ambience.gain.gain.value = Number(event.target.value); };
$('#largeText').onchange = event => { document.body.classList.toggle('large-text', event.target.checked); savePreferences({ large_text: event.target.checked }); };
$('#reduceMotion').onchange = event => { document.body.classList.toggle('reduce-motion', event.target.checked); savePreferences({ reduce_motion: event.target.checked }); };
$('#textMinus').onclick = () => { const current = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--reader-size')) || 1.2; document.documentElement.style.setProperty('--reader-size', `${Math.max(.9, current - .1)}rem`); };
$('#textPlus').onclick = () => { const current = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--reader-size')) || 1.2; document.documentElement.style.setProperty('--reader-size', `${Math.min(2.2, current + .1)}rem`); };
$('#focusLine').onclick = () => $('#readalong').classList.toggle('focus-line-mode');
$('#themeSelect').onchange = event => { applyTheme(event.target.value); savePreferences({ theme: event.target.value }); };

$('#saveVoice').onclick = async () => {
  const file = $('#voiceReference').files[0], transcript = $('#voiceTranscript').value;
  if (!file || !transcript.trim()) { $('#voiceState').textContent = 'Choose reference audio and enter its exact transcript.'; return; }
  const fd = new FormData(); fd.append('audio', file); fd.append('transcript', transcript);
  await api('/api/voice-reference', { method: 'POST', body: fd }); $('#voiceState').textContent = '✓ Custom voice override saved locally.'; await refresh();
};
$('#deleteVoice').onclick = async () => {
  if (!(await confirmAction('Return to accepted-C default voice?', 'Your custom local override will be removed. The built-in tested voice remains available.', 'Use default'))) return;
  await api('/api/voice-reference', { method: 'DELETE' }); await refresh();
};
$('#clearCache').onclick = async () => { await api('/api/cache', { method: 'DELETE' }); await refresh(); };
$('#clearProgress').onclick = async () => { if (await confirmAction('Clear all listening progress?', 'Books and audio will be kept.', 'Clear progress')) { await api('/api/progress', { method: 'DELETE' }); await refresh(); } };
const clearActivity = async () => { await api('/api/activity', { method: 'DELETE' }); await refresh(); };
$('#clearActivity').onclick = clearActivity; $('#clearAllActivity').onclick = clearActivity;
$('#resetAllData').onclick = async () => {
  if (!(await confirmAction('Delete all local library data?', 'Imported books, audio, playlists, progress and custom voice data will be deleted. The packaged accepted-C default voice remains.', 'Delete all local data'))) return;
  await api('/api/reset', json('POST', { confirmation: 'DELETE ALL LOCAL DATA' })); state.currentBook = null; audio.pause(); $('#player').classList.add('hidden'); $('#settingsDialog').close(); await refresh(); switchView('home');
};

setNavCollapsed(localStorage.getItem('listenleaf-nav-collapsed') === '1');
setSoundCollapsed(localStorage.getItem('listenleaf-sound-collapsed') === '1');
refresh().catch(error => { console.error(error); $('#pageTitle').textContent = 'ListenLeaf could not load'; });
