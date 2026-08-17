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

  async function playPartialChunk(index) {
    if (!state.currentBook) return;
    const book = state.currentBook;
    generationState.partial = {
      bookId: book.id,
      jobId: generationState.jobId,
      index,
    };
    setPlayerForBook(book);
    audio.src = `/api/books/${book.id}/chunks/${index}?v=${Date.now()}`;
    $('#currentTime').textContent = '0:00';
    $('#duration').textContent = '—';
    $('#playPause').textContent = '▶';
    audio.onloadedmetadata = () => {
      $('#duration').textContent = clock(audio.duration);
      playAudio().catch(error => {
        $('#generationStatus').textContent = `Audio ready but browser playback failed: ${error.message}`;
      });
    };
  }

  async function advancePartialPlayback() {
    const partial = generationState.partial;
    if (!partial) return;
    const next = partial.index + 1;

    while (generationState.partial && generationState.partial.bookId === partial.bookId) {
      let job = await fetchCurrentJob();
      let available = Number(job?.playable_chunks ?? state.currentBook?.playable_chunks ?? 0);
      const total = Number(job?.total_chunks ?? state.currentBook?.estimate?.chunks ?? available);

      if (next < available) {
        await playPartialChunk(next);
        return;
      }

      if (job?.status === 'completed' || (!job && next >= available)) {
        generationState.partial = null;
        $('#playPause').textContent = '▶';
        if (job?.status === 'completed') {
          state.currentBook = await api(`/api/books/${partial.bookId}`);
          loadBook(state.currentBook, true);
        } else {
          $('#generationStatus').textContent = `Played all ${available} currently generated chunk${available === 1 ? '' : 's'}. Press Generate to resume.`;
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
    await playPartialChunk(0);
  }

  async function applyJob(job) {
    generationState.lastJob = job;
    showGenerationProgress(job);
    enablePartialPlayback(job);

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
    if (playable) {
      const suffix = resumed ? ` · ${resumed} resumed` : '';
      $('#generationStatus').textContent = `${generationStage(job.stage)} · ${playable}/${job.total_chunks} playable${suffix}`;
    } else if (job.stage === 'loading_model') {
      $('#generationStatus').textContent = `Loading voice model · elapsed ${clock(job.elapsed_seconds || 0)}`;
    } else if (job.stage === 'encoding_voice') {
      $('#generationStatus').textContent = `Preparing accepted voice · elapsed ${clock(job.elapsed_seconds || 0)}`;
    }
  }

  async function watchGeneration(jobId, immediateJob = null) {
    stopGenerationPoll();
    generationState.jobId = jobId;
    generationState.bookId = state.currentBook?.id || immediateJob?.book_id || null;
    if (immediateJob) await applyJob(immediateJob);

    const poll = async () => {
      try {
        const job = await api(`/api/jobs/${jobId}`);
        await applyJob(job);
      } catch (error) {
        console.warn('generation poll failed', error);
      }
    };
    await poll();
    if (generationState.lastJob?.status !== 'completed' && generationState.lastJob?.status !== 'failed') {
      generationState.pollTimer = setInterval(poll, 1000);
    }
  }

  async function progressiveGenerate() {
    if (!state.currentBook) return;
    try {
      const result = await api(`/api/books/${state.currentBook.id}/generate`, { method: 'POST' });
      $('#generateButton').disabled = true;
      showGenerationProgress({
        ...result.estimate,
        status: result.status,
        stage: 'queued',
        percent: 0,
        completed_chunks: 0,
        playable_chunks: Number(state.currentBook.playable_chunks || 0),
        total_chunks: result.estimate.chunks,
        estimated_remaining_seconds: result.estimate.generation_seconds,
        elapsed_seconds: 0,
      });
      await watchGeneration(result.job_id);
    } catch (error) {
      $('#generateButton').disabled = false;
      $('#generationStatus').textContent = error.message;
    }
  }

  const originalOpenBook = openBook;
  openBook = async function progressiveOpenBook(id) {
    await originalOpenBook(id);
    if (Number(state.currentBook?.playable_chunks || 0) > 0 && !state.currentBook.has_audio) {
      enablePartialPlayback({
        book_id: id,
        playable_chunks: state.currentBook.playable_chunks,
      });
    }
    try {
      const active = await api(`/api/books/${id}/generation`);
      if (active.active) {
        $('#generateButton').disabled = true;
        await watchGeneration(active.job_id, active);
      }
    } catch (error) {
      console.warn('could not reconnect generation job', error);
    }
  };

  const originalLoadBook = loadBook;
  loadBook = function progressiveLoadBook(book, autoplay = true) {
    generationState.partial = null;
    return originalLoadBook(book, autoplay);
  };

  const originalTimeUpdate = audio.ontimeupdate;
  audio.ontimeupdate = () => {
    if (!generationState.partial) {
      if (originalTimeUpdate) originalTimeUpdate();
      return;
    }
    $('#currentTime').textContent = clock(audio.currentTime);
    $('#seek').value = audio.duration ? Math.round(audio.currentTime / audio.duration * 1000) : 0;
  };

  const originalEnded = audio.onended;
  audio.onended = async () => {
    if (generationState.partial) {
      await advancePartialPlayback();
      return;
    }
    if (originalEnded) await originalEnded();
  };

  $('#generateButton').onclick = progressiveGenerate;
  $('#readerPlayButton').onclick = playAvailable;
})();
