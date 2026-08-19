(() => {
  const productLink = document.createElement('link');
  productLink.rel = 'stylesheet';
  productLink.href = '/static/product-ui.css';
  document.head.appendChild(productLink);

  const productState = {
    dashboard: null,
    statusTimer: null,
    noticeTimer: null,
  };

  const el = id => document.getElementById(id);

  function showNotice(message, kind = 'info', timeout = 4200) {
    const notice = el('appNotice');
    if (!notice) return;
    window.clearTimeout(productState.noticeTimer);
    notice.textContent = message;
    notice.dataset.kind = kind;
    notice.classList.remove('hidden');
    productState.noticeTimer = window.setTimeout(() => notice.classList.add('hidden'), timeout);
  }

  function statusClass(target, value) {
    if (!target) return;
    target.classList.remove('is-ready', 'is-warning', 'is-active');
    if (value) target.classList.add(value);
  }

  function updateVoiceStatus(dashboard) {
    const ready = !!dashboard?.voice_ready;
    const homeStatus = el('homeVoiceStatus');
    const homeMeta = el('homeVoiceMeta');
    const action = el('homeVoiceAction');
    const readerState = el('readerVoiceState');

    if (homeStatus) homeStatus.textContent = ready ? 'Voice ready' : 'Voice setup required';
    if (homeMeta) homeMeta.textContent = ready
      ? 'Original reference is configured locally.'
      : 'Add your reference audio before generating.';
    if (action) action.textContent = ready ? 'Manage' : 'Set up voice';
    statusClass(homeStatus?.closest('.status-card'), ready ? 'is-ready' : 'is-warning');

    if (readerState) {
      const strong = readerState.querySelector('strong');
      const detail = readerState.querySelector('span:last-child');
      if (strong) strong.textContent = ready ? 'Voice ready' : 'Voice setup required';
      if (detail) detail.textContent = ready
        ? 'Your local reference will be used for this audiobook.'
        : 'Configure your original reference before generation.';
      statusClass(readerState, ready ? 'is-ready' : 'is-warning');
    }
  }

  function updateGenerationStatus(dashboard) {
    const generation = dashboard?.generation;
    const card = el('homeGenerationStatus')?.closest('.status-card');
    const status = el('homeGenerationStatus');
    const meta = el('homeGenerationMeta');
    const bar = el('homeGenerationBar');

    if (!status || !meta || !bar) return;
    if (!generation) {
      status.textContent = 'Generation idle';
      meta.textContent = 'Ready for one local audiobook job';
      bar.value = 0;
      bar.classList.add('hidden');
      statusClass(card, dashboard?.voice_ready ? 'is-ready' : '');
      return;
    }

    const percent = Math.max(0, Math.min(100, Number(generation.percent || 0)));
    const title = generation.title || 'Current book';
    const stage = typeof generationStage === 'function' ? generationStage(generation.stage) : (generation.stage || 'Working');
    status.textContent = `${stage} · ${Math.round(percent)}%`;
    meta.textContent = `${title} · ${generation.completed_chunks || 0}/${generation.total_chunks || '—'} chunks`;
    bar.value = percent;
    bar.classList.remove('hidden');
    statusClass(card, 'is-active');
  }

  function updateReaderGenerationGate(dashboard) {
    const button = el('generateButton');
    if (!button || !state?.currentBook) return;

    const generation = dashboard?.generation;
    const voiceMissing = !dashboard?.voice_ready;
    const anotherBookActive = !!(generation && generation.book_id && generation.book_id !== state.currentBook.id);

    if (voiceMissing) {
      button.disabled = true;
      button.title = 'Configure your original voice before generation';
    } else if (anotherBookActive) {
      button.disabled = true;
      button.title = `${generation.title || 'Another book'} is currently generating`;
      const status = el('generationStatus');
      if (status) status.textContent = `${generation.title || 'Another book'} is generating. This Mac runs one generation job at a time.`;
    } else if (!generation) {
      button.disabled = false;
      button.title = '';
    }
  }

  function applyProductDashboard(dashboard) {
    productState.dashboard = dashboard;
    updateVoiceStatus(dashboard);
    updateGenerationStatus(dashboard);
    updateReaderGenerationGate(dashboard);
  }

  async function refreshProductStatus() {
    try {
      const dashboard = await api('/api/dashboard');
      applyProductDashboard(dashboard);
      return dashboard;
    } catch (error) {
      const generation = el('homeGenerationStatus');
      if (generation) generation.textContent = 'Engine status unavailable';
      console.warn('product status refresh failed', error);
      return null;
    }
  }

  function openVoiceSettings() {
    const dialog = el('settingsDialog');
    if (!dialog) return;
    if (!dialog.open) dialog.showModal();
    requestAnimationFrame(() => el('voiceSettingsSection')?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  }

  el('homeVoiceAction')?.addEventListener('click', openVoiceSettings);
  el('readerVoiceSettings')?.addEventListener('click', openVoiceSettings);

  const fileInput = el('dialogBookFile');
  fileInput?.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    const hint = el('importFileHint');
    const title = el('importTitle');
    const status = el('importStatus');
    if (status) status.classList.add('hidden');
    if (!file) {
      if (hint) hint.textContent = 'PDF, TXT or Markdown';
      return;
    }
    const mb = file.size / (1024 * 1024);
    if (hint) hint.textContent = `${file.name} · ${mb < 1 ? `${Math.max(1, Math.round(file.size / 1024))} KB` : `${mb.toFixed(1)} MB`}`;
    if (title && !title.value.trim()) title.value = file.name.replace(/\.(pdf|txt|md)$/i, '').replace(/[_-]+/g, ' ');
  });

  const importForm = el('importForm');
  if (importForm) {
    importForm.onsubmit = async event => {
      event.preventDefault();
      const file = fileInput?.files?.[0];
      if (!file) return;

      const status = el('importStatus');
      const button = el('confirmImport');
      const originalLabel = button?.textContent || 'Import locally';
      if (status) {
        status.textContent = 'Importing and extracting text locally…';
        status.dataset.kind = 'working';
        status.classList.remove('hidden');
      }
      if (button) {
        button.disabled = true;
        button.textContent = 'Importing…';
      }

      const fd = new FormData();
      fd.append('file', file);
      fd.append('title', el('importTitle')?.value || '');
      fd.append('author', el('importAuthor')?.value || 'Unknown author');
      fd.append('series', el('importSeries')?.value || '');

      try {
        await api('/api/books/import', { method: 'POST', body: fd });
        importForm.reset();
        if (status) status.classList.add('hidden');
        el('importDialog')?.close();
        await refresh();
        await refreshProductStatus();
        switchView('library');
        showNotice('Book imported locally and added to your library.', 'success');
      } catch (error) {
        if (status) {
          status.textContent = error.message || 'Import failed. Check the file and try again.';
          status.dataset.kind = 'error';
          status.classList.remove('hidden');
        }
      } finally {
        if (button) {
          button.disabled = false;
          button.textContent = originalLabel;
        }
      }
    };
  }

  const readerObserver = el('readerView') ? new MutationObserver(() => {
    if (el('readerView')?.classList.contains('active-view') && productState.dashboard) {
      updateVoiceStatus(productState.dashboard);
      updateReaderGenerationGate(productState.dashboard);
    }
  }) : null;
  readerObserver?.observe(el('readerView'), { attributes: true, attributeFilter: ['class'] });

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) refreshProductStatus();
  });

  window.addEventListener('unhandledrejection', event => {
    const message = event.reason?.message;
    if (message) showNotice(message, 'error', 6000);
  });

  refreshProductStatus();
  productState.statusTimer = window.setInterval(() => {
    if (!document.hidden) refreshProductStatus();
  }, 3000);
})();
