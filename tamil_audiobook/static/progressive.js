(() => {
  const generationState = {
    jobId: null,
    bookId: null,
    pollTimer: null,
    partial: null,
    lastJob: null,
    lastProgressSave: 0,
  };
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const baseTimeUpdate = audio.ontimeupdate;

  function stopGenerationPoll() {
    if (generationState.pollTimer) clearInterval(generationState.pollTimer);
    generationState.pollTimer = null;
  }

  function bookDuration() {
    const book = state.currentBook || {};
    const persisted = Number(book.progress?.duration || 0);
    const reported = Number(book.audio_seconds || 0);
    const estimated = Number(book.estimate?.audio_seconds || 0);
    const cues = book.cues || [];
    const cueEnd = cues.length ? Number(cues[cues.length - 1].end || 0) : 0;
    return Math.max(persisted, reported, cueEnd, estimated, 0);
  }

  function chunkOffset(index) {
    const cues = state.currentBook?.cues || [];
    const cue = cues.find(item => Number(item.index) === Number(index));
    if (cue && Number.isFinite(Number(cue.start))) return Number(cue.start);
    const partial = generationState.partial;
    if (!partial) return 0;
    if (Number.isFinite(Number(partial.offsets?.[index]))) return Number(partial.offsets[index]);
    let offset = 0;
    for (let i = 0; i < index; i++) offset += Number(partial.durations?.[i] || 0);
    return offset;
  }

  function canonicalPlaybackPosition() {
    const partial = generationState.partial;
    if (partial) {
      return {
        seconds: Math.max(0, chunkOffset(partial.index) + Number(audio.currentTime || 0)),
        duration: bookDuration(),
        progressive: true,
        chunk: partial.index,
      };
    }
    return {
      seconds: Math.max(0, Number(audio.currentTime || 0)),
      duration: Math.max(0, Number(audio.duration || bookDuration() || 0)),
      progressive: false,
      chunk: null,
    };
  }
  state.playbackPosition = canonicalPlaybackPosition;

  function persistCanonicalProgress() {
    if (!state.currentBook) return;
    const position = canonicalPlaybackPosition();
    if (!position.duration || !Number.isFinite(position.duration)) return;
    if (Date.now() - generationState.lastProgressSave < 5000) return;
    generationState.lastProgressSave = Date.now();
    api(`/api/books/${state.currentBook.id}/progress`, json('POST', {
      seconds: position.seconds,
      duration: position.duration,
    })).catch(() => {});
  }

  function setPlayerForBook(book) {
    $('#player').classList.remove('hidden');
    $('#playerTitle').textContent = book.title;
    $('#playerAuthor').textContent = book.author;
    $('#playerCover span').textContent = initials(book.title);
  }

  function activateCue(index) {
    state.currentCue = index;
    $$('.cue.active').forEach(el => el.classList.remove('active'));
    const active = $(`.cue[data-index="${index}"]`);
    if (active) active.classList.add('active');
  }

  function refreshTransportLabels() {
    const seconds = Number($('#skipSelect')?.value || 15);
    $('#rewind').textContent = `↶${seconds}`;
    $('#forward').textContent = `${seconds}↷`;
    $('#rewind').title = `Back ${seconds} seconds`;
    $('#forward').title = `Forward ${seconds} seconds`;
  }

  function ensureExportButton() {
    if ($('#exportAudio')) return;
    const button = document.createElement('button');
    button.id = 'exportAudio'; button.className = 'secondary wide'; button.textContent = '⇩ Export MP3'; button.disabled = true;
    button.addEventListener('click', () => {
      const book = state.currentBook;
      if (!book?.has_audio) { $('#generationStatus').textContent = 'MP3 export becomes available when the complete audiobook is ready.'; return; }
      const a = document.createElement('a');
      a.href = `/api/books/${book.id}/audio`; a.download = `${(book.title || 'audiobook').replace(/[^\p{L}\p{N}._ -]+/gu, '_')}.mp3`;
      document.body.appendChild(a); a.click(); a.remove();
    });
    $('#readerPlayButton')?.insertAdjacentElement('afterend', button);
  }

  function ensureCancelButton() {
    if ($('#cancelGeneration')) return;
    const button = document.createElement('button');
    button.id = 'cancelGeneration'; button.className = 'secondary wide hidden'; button.textContent = 'Cancel generation';
    button.addEventListener('click', async () => {
      if (!generationState.jobId) return;
      button.disabled = true; button.textContent = 'Cancelling…';
      try {
        const job = await api(`/api/jobs/${generationState.jobId}/cancel`, { method: 'POST' });
        await applyJob(job);
      } catch (error) { $('#generationStatus').textContent = error.message; }
    });
    $('#generateButton')?.insertAdjacentElement('afterend', button);
  }

  function setGenerationControls(active) {
    ensureCancelButton();
    $('#generateButton').disabled = !!active;
    $('#clearAudio').disabled = !!active || !state.currentBook?.has_audio;
    const cancel = $('#cancelGeneration');
    if (cancel) {
      cancel.classList.toggle('hidden', !active);
      cancel.disabled = false;
      cancel.textContent = 'Cancel generation';
    }
  }

  function updateExportButton() {
    ensureExportButton();
    const button = $('#exportAudio');
    if (button) {
      button.disabled = !state.currentBook?.has_audio;
      button.title = state.currentBook?.has_audio ? 'Export completed audiobook as MP3' : 'Complete generation first';
    }
  }

  function enablePartialPlayback(job) {
    const count = Number(job.playable_chunks || 0);
    if (!count || !state.currentBook || job.book_id !== state.currentBook.id) return;
    state.currentBook.playable_chunks = Math.max(Number(state.currentBook.playable_chunks || 0), count);
    const button = $('#readerPlayButton');
    button.classList.remove('hidden');
    if (!state.currentBook.has_audio) button.textContent = `▶ Play available audio (${count} chunk${count === 1 ? '' : 's'})`;
    // Backend contract rejects Clear Audio while generation owns the lease.
    $('#clearAudio').disabled = true;
  }

  async function fetchCurrentJob() {
    if (!generationState.jobId) return null;
    try { return await api(`/api/jobs/${generationState.jobId}`); } catch { return null; }
  }

  async function playPartialChunk(index, startAt = 0, autoplay = true) {
    if (!state.currentBook) return;
    const book = state.currentBook;
    const previous = generationState.partial?.bookId === book.id ? generationState.partial : {};
    const durations = previous.durations || {};
    const offsets = previous.offsets || {};
    if (!Number.isFinite(Number(offsets[index]))) {
      if (book.cues?.[index]) offsets[index] = Number(book.cues[index].start || 0);
      else if (index === 0) offsets[index] = 0;
      else offsets[index] = chunkOffset(index);
    }
    generationState.partial = { bookId: book.id, jobId: generationState.jobId, index, durations, offsets };
    setPlayerForBook(book);
    audio.src = `/api/books/${book.id}/chunks/${index}?v=${Date.now()}`;
    $('#currentTime').textContent = clock(canonicalPlaybackPosition().seconds);
    $('#duration').textContent = clock(bookDuration());
    $('#playPause').textContent = '▶'; activateCue(index);
    audio.onloadedmetadata = () => {
      if (!generationState.partial) return;
      generationState.partial.durations[index] = audio.duration;
      if (!Number.isFinite(Number(generationState.partial.offsets[index + 1]))) {
        generationState.partial.offsets[index + 1] = chunkOffset(index) + Number(audio.duration || 0);
      }
      audio.currentTime = Math.max(0, Math.min(Number(startAt || 0), Math.max(0, audio.duration - 0.05)));
      const position = canonicalPlaybackPosition();
      $('#currentTime').textContent = clock(position.seconds); $('#duration').textContent = clock(position.duration);
      if (autoplay) playAudio().catch(error => { $('#generationStatus').textContent = `Audio ready but browser playback failed: ${error.message}`; });
    };
  }

  async function advancePartialPlayback() {
    const partial = generationState.partial;
    if (!partial) return;
    const next = partial.index + 1;
    while (generationState.partial && generationState.partial.bookId === partial.bookId) {
      const job = await fetchCurrentJob();
      const available = Number(job?.playable_chunks ?? state.currentBook?.playable_chunks ?? 0);
      const total = Number(job?.total_chunks ?? state.currentBook?.estimate?.chunks ?? available);
      if (next < available) { await playPartialChunk(next, 0, true); return; }
      if (['cancelled', 'interrupted', 'failed'].includes(job?.status) || (!job && next >= available)) {
        generationState.partial = null; $('#playPause').textContent = '▶';
        $('#generationStatus').textContent = `Played all ${available} currently generated chunks. Press Generate to resume.`;
        return;
      }
      if (job?.status === 'completed') {
        generationState.partial = null; state.currentBook = await api(`/api/books/${partial.bookId}`); loadBook(state.currentBook, true); updateExportButton(); return;
      }
      $('#playPause').textContent = '…'; $('#generationStatus').textContent = `Playback caught up with generation · waiting for chunk ${next + 1}/${total}`; await sleep(1000);
    }
  }

  async function playAvailable() {
    if (!state.currentBook) return;
    if (state.currentBook.has_audio) { generationState.partial = null; loadBook(state.currentBook, true); return; }
    const available = Number(generationState.lastJob?.playable_chunks ?? state.currentBook.playable_chunks ?? 0);
    if (!available) { $('#generationStatus').textContent = 'No audio chunk is ready yet. Playback unlocks after chunk 1.'; return; }
    const saved = Number(state.currentBook.progress?.seconds || 0);
    let index = 0; let local = saved;
    if (state.currentBook.cues?.length) {
      const cue = state.currentBook.cues.find(item => saved >= Number(item.start) && saved < Number(item.end));
      if (cue && Number(cue.index) < available) { index = Number(cue.index); local = Math.max(0, saved - Number(cue.start)); }
    }
    await playPartialChunk(index, local, true);
  }

  async function seekPartial(deltaSeconds) {
    const partial = generationState.partial;
    if (!partial) return false;
    const available = Number(generationState.lastJob?.playable_chunks ?? state.currentBook?.playable_chunks ?? 0);
    const targetAbsolute = Math.max(0, canonicalPlaybackPosition().seconds + Number(deltaSeconds || 0));
    let index = partial.index;
    // Prefer true cue offsets; fall back to measured chunk offsets while generation is incomplete.
    const cues = state.currentBook?.cues || [];
    if (cues.length) {
      const cue = cues.slice(0, available).find(item => targetAbsolute >= Number(item.start) && targetAbsolute < Number(item.end));
      if (cue) index = Number(cue.index);
    } else {
      for (let i = 0; i < available; i++) {
        const start = Number(partial.offsets?.[i] ?? chunkOffset(i));
        const end = start + Number(partial.durations?.[i] || (i === partial.index ? audio.duration : 0));
        if (targetAbsolute >= start && (targetAbsolute < end || i === available - 1)) { index = i; break; }
      }
    }
    const local = Math.max(0, targetAbsolute - (cues[index]?.start ?? chunkOffset(index)));
    if (index !== partial.index) await playPartialChunk(index, local, true);
    else {
      audio.currentTime = Math.max(0, Math.min(local, Math.max(0, (audio.duration || local) - 0.05)));
      activateCue(index); if (audio.paused) await playAudio().catch(() => {});
    }
    return true;
  }

  async function applyJob(job) {
    generationState.lastJob = job; showGenerationProgress(job); enablePartialPlayback(job);
    const active = ['queued', 'running', 'cancelling'].includes(job.status);
    setGenerationControls(active);
    if (job.stage === 'cooling') $('#generationStatus').textContent = `Cooling Mac · ${job.cooling_seconds || 5}s pause · ${job.playable_chunks || 0}/${job.total_chunks} playable`;
    if (job.status === 'completed') {
      stopGenerationPoll(); setGenerationControls(false);
      if (state.currentBook?.id === job.book_id) {
        state.currentBook = await api(`/api/books/${job.book_id}`); renderReadalong(state.currentBook);
        $('#readerPlayButton').classList.remove('hidden'); $('#readerPlayButton').textContent = '▶ Play audiobook';
        $('#clearAudio').disabled = false; $('#readerDuration').textContent = durationLabel(job.audio_seconds);
        $('#generationStatus').textContent = `Ready · ${durationLabel(job.audio_seconds)} · RTF ${job.aggregate_rtf}`; updateExportButton();
      }
      await refresh(); return;
    }
    if (['failed', 'cancelled', 'interrupted'].includes(job.status)) {
      stopGenerationPoll(); setGenerationControls(false);
      $('#generationStatus').textContent = job.error || (job.status === 'cancelled' ? 'Generation cancelled · ready to resume' : 'Generation interrupted · ready to resume');
      $('#generationChunk').textContent = job.status === 'failed' ? 'Generation failed' : 'Completed chunks kept · press Generate to resume';
      return;
    }
    if (job.status === 'cancelling') { $('#generationStatus').textContent = 'Cancelling safely after the current chunk…'; return; }
    const playable = Number(job.playable_chunks || 0), resumed = Number(job.resumed_chunks || 0);
    if (playable && job.stage !== 'cooling') $('#generationStatus').textContent = `${generationStage(job.stage)} · ${playable}/${job.total_chunks} playable${resumed ? ` · ${resumed} resumed` : ''}`;
  }

  async function watchGeneration(jobId, immediateJob = null) {
    stopGenerationPoll(); generationState.jobId = jobId; generationState.bookId = state.currentBook?.id || immediateJob?.book_id || null;
    if (immediateJob) await applyJob(immediateJob);
    const poll = async () => {
      try { await applyJob(await api(`/api/jobs/${jobId}`)); }
      catch (error) { console.warn('generation poll failed', error); }
    };
    await poll();
    if (!['completed', 'failed', 'cancelled', 'interrupted'].includes(generationState.lastJob?.status)) generationState.pollTimer = setInterval(poll, 1000);
  }

  async function progressiveGenerate() {
    if (!state.currentBook) return;
    try {
      const result = await api(`/api/books/${state.currentBook.id}/generate`, { method: 'POST' });
      setGenerationControls(true);
      showGenerationProgress({ ...result.estimate, status: result.status, stage: 'queued', percent: 0, completed_chunks: 0, playable_chunks: Number(state.currentBook.playable_chunks || 0), total_chunks: result.estimate.chunks, estimated_remaining_seconds: result.estimate.generation_seconds, elapsed_seconds: 0 });
      await watchGeneration(result.job_id);
    } catch (error) { setGenerationControls(false); $('#generationStatus').textContent = error.message; }
  }

  async function enhanceCurrentBook() {
    const book = state.currentBook;
    if (!book || !$('#readerView')?.classList.contains('active-view')) return;
    updateExportButton(); refreshTransportLabels(); ensureCancelButton();
    if (Number(book.playable_chunks || 0) > 0 && !book.has_audio) enablePartialPlayback({ book_id: book.id, playable_chunks: book.playable_chunks });
    try {
      const current = await api(`/api/books/${book.id}/generation`);
      if (current.active) await watchGeneration(current.job_id, current);
      else if (current.status === 'interrupted') {
        setGenerationControls(false); $('#generationStatus').textContent = current.error || 'Generation was interrupted. Press Generate to resume from checkpoints.';
      }
    } catch (error) { console.warn('could not reconnect generation job', error); }
  }

  // Replace the base custom confirmation helper so every native dialog close path resolves exactly once.
  window.confirmAction = function robustConfirmAction(title, message, label = 'Confirm') {
    return new Promise(resolve => {
      const dialog = $('#confirmDialog');
      let settled = false;
      const settle = value => {
        if (settled) return;
        settled = true;
        cleanup();
        state.confirmAction = null;
        resolve(value);
      };
      const onCancel = event => { event.preventDefault(); if (dialog.open) dialog.close(); settle(false); };
      const onClose = () => settle(false);
      const cleanup = () => { dialog.removeEventListener('cancel', onCancel); dialog.removeEventListener('close', onClose); };
      $('#confirmTitle').textContent = title; $('#confirmMessage').textContent = message; $('#confirmYes').textContent = label;
      state.confirmAction = () => settle(true);
      $('#confirmCancel').onclick = () => { if (dialog.open) dialog.close(); settle(false); };
      $('#confirmYes').onclick = () => { settle(true); if (dialog.open) dialog.close(); };
      dialog.addEventListener('cancel', onCancel); dialog.addEventListener('close', onClose); dialog.showModal();
    });
  };

  const readerObserver = new MutationObserver(() => { queueMicrotask(enhanceCurrentBook); });
  readerObserver.observe($('#readerView'), { attributes: true, attributeFilter: ['class'] });

  audio.addEventListener('loadstart', () => { if (!String(audio.src || '').includes('/chunks/')) generationState.partial = null; });
  // Canonical playback saver: while a chunk is mounted, do not invoke app.js's chunk-local saver.
  audio.ontimeupdate = () => {
    if (!generationState.partial) { if (typeof baseTimeUpdate === 'function') baseTimeUpdate.call(audio); return; }
    const position = canonicalPlaybackPosition();
    $('#currentTime').textContent = clock(position.seconds);
    $('#duration').textContent = clock(position.duration);
    $('#seek').value = position.duration > 0 ? Math.round(position.seconds / position.duration * 1000) : 0;
    activateCue(generationState.partial.index);
    persistCanonicalProgress();
  };
  audio.addEventListener('ended', async event => {
    if (!generationState.partial) return;
    event.stopImmediatePropagation(); await advancePartialPlayback();
  }, true);

  $('#rewind').addEventListener('click', async event => { if (!generationState.partial) return; event.preventDefault(); event.stopImmediatePropagation(); await seekPartial(-Number($('#skipSelect').value || 15)); }, true);
  $('#forward').addEventListener('click', async event => { if (!generationState.partial) return; event.preventDefault(); event.stopImmediatePropagation(); await seekPartial(Number($('#skipSelect').value || 15)); }, true);
  $('#seek').addEventListener('input', async event => {
    if (!generationState.partial) return;
    event.preventDefault(); event.stopImmediatePropagation();
    const duration = bookDuration();
    const target = duration * Number(event.target.value) / 1000;
    await seekPartial(target - canonicalPlaybackPosition().seconds);
  }, true);
  $('#skipSelect').addEventListener('change', refreshTransportLabels);

  let focusLineEnabled = document.body.classList.contains('focus-line-mode');
  $('#focusLine').addEventListener('click', () => {
    focusLineEnabled = !focusLineEnabled; document.body.classList.toggle('focus-line-mode', focusLineEnabled); $('#focusLine').classList.toggle('active', focusLineEnabled); $('#focusLine').textContent = focusLineEnabled ? 'Focus line ✓' : 'Focus line';
    if (focusLineEnabled && generationState.partial) activateCue(generationState.partial.index); else if (focusLineEnabled) syncReadalong();
  });

  $('#generateButton').onclick = progressiveGenerate;
  $('#readerPlayButton').onclick = playAvailable;
  ensureExportButton(); ensureCancelButton(); refreshTransportLabels();
})();
