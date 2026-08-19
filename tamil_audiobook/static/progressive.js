(() => {
  const generationState = {
    jobId: null,
    bookId: null,
    pollTimer: null,
    partial: null,
    lastJob: null,
  };

  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  function stopGenerationPoll() {
    if (generationState.pollTimer) clearInterval(generationState.pollTimer);
    generationState.pollTimer = null;
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
    if (active) {
      active.classList.add('active');
      active.scrollIntoView({
        behavior: document.body.classList.contains('reduce-motion') ? 'auto' : 'smooth',
        block: 'center',
      });
    }
  }

  function partialGlobalSeconds() {
    const partial = generationState.partial;
    if (!partial) return audio.currentTime || 0;
    let offset = 0;
    for (let i = 0; i < partial.index; i++) offset += Number(partial.durations?.[i] || 0);
    return offset + (audio.currentTime || 0);
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
    button.id = 'exportAudio';
    button.className = 'secondary wide';
    button.textContent = '⇩ Export MP3';
    button.disabled = true;
    button.addEventListener('click', () => {
      const book = state.currentBook;
      if (!book?.has_audio) {
        $('#generationStatus').textContent = 'MP3 export becomes available when the complete audiobook is ready.';
        return;
      }
      const a = document.createElement('a');
      a.href = `/api/books/${book.id}/audio`;
      a.download = `${(book.title || 'audiobook').replace(/[^\p{L}\p{N}._ -]+/gu, '_')}.mp3`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    });
    $('#readerPlayButton')?.insertAdjacentElement('afterend', button);
  }

  function updateExportButton() {
    ensureExportButton();
    const button = $('#exportAudio');
    if (!button) return;
    button.disabled = !state.currentBook?.has_audio;
    button.title = state.currentBook?.has_audio ? 'Export completed audiobook as MP3' : 'Complete generation first';
  }

  function enablePartialPlayback(job) {
    const count = Number(job.playable_chunks || 0);
    if (!count || !state.currentBook || job.book_id !== state.currentBook.id) return;
    state.currentBook.playable_chunks = Math.max(Number(state.currentBook.playable_chunks || 0), count);
    const button = $('#readerPlayButton');
    button.classList.remove('hidden');
    if (!state.currentBook.has_audio) button.textContent = `▶ Play available audio (${count} chunk${count === 1 ? '' : 's'})`;
    $('#clearAudio').disabled = false;
  }

  async function fetchCurrentJob() {
    if (!generationState.jobId) return null;
    try {
      return await api(`/api/jobs/${generationState.jobId}`);
    } catch {
      return null;
    }
  }

  async function playPartialChunk(index, startAt = 0, autoplay = true) {
    if (!state.currentBook) return;
    const book = state.currentBook;
    const durations = generationState.partial?.bookId === book.id ? generationState.partial.durations || {} : {};
    generationState.partial = { bookId: book.id, jobId: generationState.jobId, index, durations };
    setPlayerForBook(book);
    audio.src = `/api/books/${book.id}/chunks/${index}?v=${Date.now()}`;
    $('#currentTime').textContent = clock(partialGlobalSeconds());
    $('#duration').textContent = `chunk ${index + 1}`;
    $('#playPause').textContent = '▶';
    activateCue(index);
    audio.onloadedmetadata = () => {
      if (generationState.partial) generationState.partial.durations[index] = audio.duration;
      audio.currentTime = Math.max(0, Math.min(Number(startAt || 0), Math.max(0, audio.duration - 0.05)));
      $('#currentTime').textContent = clock(partialGlobalSeconds());
      $('#duration').textContent = `${clock(audio.duration)} · chunk ${index + 1}`;
      if (autoplay) playAudio().catch(error => {
        $('#generationStatus').textContent = `Audio ready but browser playback failed: ${error.message}`;
      });
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
      if (next < available) {
        await playPartialChunk(next, 0, true);
        return;
      }
      if (job?.status === 'completed' || (!job && next >= available)) {
        generationState.partial = null;
        $('#playPause').textContent = '▶';
        if (job?.status === 'completed') {
          state.currentBook = await api(`/api/books/${partial.bookId}`);
          loadBook(state.currentBook, true);
          updateExportButton();
        } else {
          $('#generationStatus').textContent = `Played all ${available} currently generated chunks. Press Generate to resume.`;
        }
        return;
      }
      $('#playPause').textContent = '…';
      $('#generationStatus').textContent = `Playback caught up with generation · waiting for chunk ${next + 1}/${total}`;
      await sleep(1000);
    }
  }

  async function playAvailable() {
    if (!state.currentBook) return;
    if (state.currentBook.has_audio) {
      generationState.partial = null;
      loadBook(state.currentBook, true);
      return;
    }
    const available = Number(generationState.lastJob?.playable_chunks ?? state.currentBook.playable_chunks ?? 0);
    if (!available) {
      $('#generationStatus').textContent = 'No audio chunk is ready yet. Playback unlocks after chunk 1.';
      return;
    }
    await playPartialChunk(0, 0, true);
  }

  async function seekPartial(deltaSeconds) {
    const partial = generationState.partial;
    if (!partial) return false;
    let target = (audio.currentTime || 0) + Number(deltaSeconds || 0);
    let index = partial.index;
    const available = Number(generationState.lastJob?.playable_chunks ?? state.currentBook?.playable_chunks ?? 0);
    while (target < 0 && index > 0) {
      index -= 1;
      let duration = Number(partial.durations?.[index] || 0);
      if (!duration) {
        await playPartialChunk(index, 0, false);
        await new Promise(resolve => audio.addEventListener('loadedmetadata', resolve, { once: true }));
        duration = audio.duration || 0;
      }
      target += duration;
    }
    while (target >= (audio.duration || 0) && index < available - 1) {
      target -= Number(audio.duration || partial.durations?.[index] || 0);
      index += 1;
      await playPartialChunk(index, 0, false);
      await new Promise(resolve => audio.addEventListener('loadedmetadata', resolve, { once: true }));
    }
    if (index !== generationState.partial?.index) await playPartialChunk(index, target, true);
    else {
      audio.currentTime = Math.max(0, Math.min(target, Math.max(0, (audio.duration || target) - 0.05)));
      activateCue(index);
      if (audio.paused) await playAudio().catch(() => {});
    }
    return true;
  }

  async function applyJob(job) {
    generationState.lastJob = job;
    showGenerationProgress(job);
    enablePartialPlayback(job);
    if (job.stage === 'cooling') $('#generationStatus').textContent = `Cooling Mac · ${job.cooling_seconds || 5}s pause · ${job.playable_chunks || 0}/${job.total_chunks} playable`;
    if (job.status === 'completed') {
      stopGenerationPoll();
      $('#generateButton').disabled = false;
      if (state.currentBook?.id === job.book_id) {
        state.currentBook = await api(`/api/books/${job.book_id}`);
        renderReadalong(state.currentBook);
        $('#readerPlayButton').classList.remove('hidden');
        $('#readerPlayButton').textContent = '▶ Play audiobook';
        $('#clearAudio').disabled = false;
        $('#readerDuration').textContent = durationLabel(job.audio_seconds);
        $('#generationStatus').textContent = `Ready · ${durationLabel(job.audio_seconds)} · RTF ${job.aggregate_rtf}`;
        updateExportButton();
      }
      await refresh();
      return;
    }
    if (job.status === 'failed') {
      stopGenerationPoll();
      $('#generateButton').disabled = false;
      $('#generationStatus').textContent = job.error || 'Generation failed';
      $('#generationChunk').textContent = 'Generation failed';
      return;
    }
    const playable = Number(job.playable_chunks || 0);
    const resumed = Number(job.resumed_chunks || 0);
    if (playable && job.stage !== 'cooling') {
      const suffix = resumed ? ` · ${resumed} resumed` : '';
      $('#generationStatus').textContent = `${generationStage(job.stage)} · ${playable}/${job.total_chunks} playable${suffix}`;
    } else if (job.stage === 'loading_model') $('#generationStatus').textContent = `Loading voice model · elapsed ${clock(job.elapsed_seconds || 0)}`;
    else if (job.stage === 'encoding_voice') $('#generationStatus').textContent = `Preparing original voice · elapsed ${clock(job.elapsed_seconds || 0)}`;
  }

  async function watchGeneration(jobId, immediateJob = null) {
    stopGenerationPoll();
    generationState.jobId = jobId;
    generationState.bookId = state.currentBook?.id || immediateJob?.book_id || null;
    if (immediateJob) await applyJob(immediateJob);
    const poll = async () => {
      try { await applyJob(await api(`/api/jobs/${jobId}`)); }
      catch (error) { console.warn('generation poll failed', error); }
    };
    await poll();
    if (!['completed', 'failed'].includes(generationState.lastJob?.status)) generationState.pollTimer = setInterval(poll, 1000);
  }

  async function progressiveGenerate() {
    if (!state.currentBook) return;
    try {
      const result = await api(`/api/books/${state.currentBook.id}/generate`, { method: 'POST' });
      $('#generateButton').disabled = true;
      showGenerationProgress({ ...result.estimate, status: result.status, stage: 'queued', percent: 0, completed_chunks: 0, playable_chunks: Number(state.currentBook.playable_chunks || 0), total_chunks: result.estimate.chunks, estimated_remaining_seconds: result.estimate.generation_seconds, elapsed_seconds: 0 });
      await watchGeneration(result.job_id);
    } catch (error) {
      $('#generateButton').disabled = false;
      $('#generationStatus').textContent = error.message;
    }
  }

  async function enhanceCurrentBook() {
    const book = state.currentBook;
    if (!book || !$('#readerView')?.classList.contains('active-view')) return;
    updateExportButton();
    refreshTransportLabels();
    if (Number(book.playable_chunks || 0) > 0 && !book.has_audio) enablePartialPlayback({ book_id: book.id, playable_chunks: book.playable_chunks });
    try {
      const active = await api(`/api/books/${book.id}/generation`);
      if (active.active) {
        $('#generateButton').disabled = true;
        await watchGeneration(active.job_id, active);
      }
    } catch (error) {
      console.warn('could not reconnect generation job', error);
    }
  }

  const readerObserver = new MutationObserver(() => { queueMicrotask(enhanceCurrentBook); });
  readerObserver.observe($('#readerView'), { attributes: true, attributeFilter: ['class'] });

  audio.addEventListener('loadstart', () => {
    if (!String(audio.src || '').includes('/chunks/')) generationState.partial = null;
  });
  audio.addEventListener('timeupdate', () => {
    if (!generationState.partial) return;
    $('#currentTime').textContent = clock(partialGlobalSeconds());
    $('#seek').value = audio.duration ? Math.round(audio.currentTime / audio.duration * 1000) : 0;
    activateCue(generationState.partial.index);
  });
  audio.addEventListener('ended', async event => {
    if (!generationState.partial) return;
    event.stopImmediatePropagation();
    await advancePartialPlayback();
  }, true);

  $('#rewind').addEventListener('click', async event => {
    if (!generationState.partial) return;
    event.preventDefault(); event.stopImmediatePropagation();
    await seekPartial(-Number($('#skipSelect').value || 15));
  }, true);
  $('#forward').addEventListener('click', async event => {
    if (!generationState.partial) return;
    event.preventDefault(); event.stopImmediatePropagation();
    await seekPartial(Number($('#skipSelect').value || 15));
  }, true);
  $('#skipSelect').addEventListener('change', refreshTransportLabels);

  let focusLineEnabled = document.body.classList.contains('focus-line-mode');
  $('#focusLine').addEventListener('click', () => {
    focusLineEnabled = !focusLineEnabled;
    document.body.classList.toggle('focus-line-mode', focusLineEnabled);
    $('#focusLine').classList.toggle('active', focusLineEnabled);
    $('#focusLine').textContent = focusLineEnabled ? 'Focus line ✓' : 'Focus line';
    if (focusLineEnabled && generationState.partial) activateCue(generationState.partial.index);
    else if (focusLineEnabled) syncReadalong();
  });

  $('#generateButton').onclick = progressiveGenerate;
  $('#readerPlayButton').onclick = playAvailable;
  ensureExportButton();
  refreshTransportLabels();
})();
