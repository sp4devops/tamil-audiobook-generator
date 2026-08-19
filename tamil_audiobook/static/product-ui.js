(() => {
  const productLink = document.createElement('link');
  productLink.rel = 'stylesheet';
  productLink.href = '/static/product-ui.css';
  document.head.appendChild(productLink);

  const productState = {
    dashboard: null,
    statusTimer: null,
    noticeTimer: null,
    libraryQuery: '',
    libraryMode: localStorage.getItem('listenleaf-library-mode') || 'list',
    density: localStorage.getItem('listenleaf-density') || 'comfortable',
    accent: localStorage.getItem('listenleaf-accent') || 'emerald',
  };

  const el = id => document.getElementById(id);
  const icon = id => `<svg class="icon" aria-hidden="true"><use href="#${id}"></use></svg>`;

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

  function hashHue(text = '') {
    let hash = 17;
    for (const char of String(text)) hash = ((hash * 31) + char.codePointAt(0)) >>> 0;
    return 125 + (hash % 190);
  }

  function progressFor(book) {
    const p = book?.progress || {};
    if (!Number(p.duration)) return 0;
    return Math.max(0, Math.min(100, Number(p.seconds || 0) / Number(p.duration) * 100));
  }

  function enhanceBookSurfaces() {
    const books = new Map((state?.dashboard?.books || productState.dashboard?.books || []).map(book => [String(book.id), book]));

    document.querySelectorAll('.book-card[data-book]').forEach(card => {
      const book = books.get(String(card.dataset.book));
      if (!book) return;
      card.dataset.ready = book.has_audio ? 'true' : 'false';
      card.style.setProperty('--cover-hue', hashHue(book.title));
      const cover = card.querySelector('.cover');
      if (cover) cover.style.setProperty('--cover-hue', hashHue(book.title));
      if (!card.querySelector('.book-badge')) {
        const badge = document.createElement('span');
        badge.className = 'book-badge';
        badge.textContent = book.has_audio ? 'AUDIO READY' : String(book.source_format || 'TEXT').toUpperCase();
        cover?.appendChild(badge);
      } else {
        card.querySelector('.book-badge').textContent = book.has_audio ? 'AUDIO READY' : String(book.source_format || 'TEXT').toUpperCase();
      }
      let label = card.querySelector('.book-progress-label');
      if (!label) {
        label = document.createElement('span');
        label.className = 'book-progress-label';
        card.appendChild(label);
      }
      const pct = progressFor(book);
      label.textContent = pct > 0 ? `${Math.round(pct)}% listened` : (book.has_audio ? 'Ready to play' : 'Ready to generate');
    });

    document.querySelectorAll('.library-row[data-book]').forEach(row => {
      const book = books.get(String(row.dataset.book));
      if (!book) return;
      row.dataset.ready = book.has_audio ? 'true' : 'false';
      row.dataset.search = `${book.title || ''} ${book.author || ''} ${book.series || ''}`.toLowerCase();
      const cover = row.querySelector('.row-cover');
      cover?.style.setProperty('--cover-hue', hashHue(book.title));
      const last = row.lastElementChild;
      if (last && !last.querySelector('[data-play-book]')) last.innerHTML = `<span class="row-status">${book.has_audio ? 'Audio ready' : 'Text only'}</span>`;
    });
    applyLibraryFilter();
    rebuildPremiumGrid();
  }

  function createHero() {
    const home = el('homeView');
    if (!home || el('premiumHero')) return;
    const hero = document.createElement('section');
    hero.id = 'premiumHero';
    hero.className = 'premium-hero';
    hero.innerHTML = `
      <div class="hero-copy">
        <span class="hero-chip"><i class="hero-chip-dot"></i>PRIVATE AUDIOBOOK STUDIO</span>
        <h2>Turn reading into <em>listening.</em></h2>
        <p>Import a book, generate it in your own local voice, and listen with synchronized read-along — without sending your library to the cloud.</p>
        <div class="hero-actions">
          <button id="heroImport" class="premium-action primary-action" type="button">${icon('icon-plus')}<span>Import a book</span></button>
          <button id="heroLibrary" class="premium-action secondary-action" type="button">${icon('icon-library')}<span>Open library</span></button>
        </div>
      </div>
      <div class="hero-visual" aria-hidden="true">
        <div class="hero-orbit"><div class="waveform">${'<i></i>'.repeat(8)}</div></div>
        <div class="hero-metrics">
          <div class="hero-metric"><strong id="heroBookCount">0</strong><span>books</span></div>
          <div class="hero-metric"><strong id="heroAudioCount">0</strong><span>audio ready</span></div>
          <div class="hero-metric"><strong id="heroPrivacy">Local</strong><span>processing</span></div>
        </div>
      </div>`;
    home.prepend(hero);
    el('heroImport')?.addEventListener('click', () => el('importDialog')?.showModal());
    el('heroLibrary')?.addEventListener('click', () => switchView('library'));
  }

  function createLibraryToolbar() {
    const view = el('libraryView');
    const list = el('libraryList');
    if (!view || !list || el('libraryToolbar')) return;
    const toolbar = document.createElement('div');
    toolbar.id = 'libraryToolbar';
    toolbar.className = 'library-toolbar';
    toolbar.innerHTML = `
      <label class="library-search" for="librarySearch"><span aria-hidden="true">⌕</span><input id="librarySearch" type="search" placeholder="Search title, author or series" autocomplete="off"></label>
      <div class="segmented" aria-label="Library view">
        <button id="libraryListMode" type="button" title="List view">${icon('icon-library')}<span>List</span></button>
        <button id="libraryGridMode" type="button" title="Grid view">▦<span>Grid</span></button>
      </div>`;
    list.before(toolbar);
    const grid = document.createElement('div');
    grid.id = 'premiumLibraryGrid';
    grid.className = 'premium-library-grid card-grid';
    list.after(grid);
    el('librarySearch')?.addEventListener('input', event => {
      productState.libraryQuery = event.target.value.trim().toLowerCase();
      applyLibraryFilter();
    });
    el('libraryListMode')?.addEventListener('click', () => setLibraryMode('list'));
    el('libraryGridMode')?.addEventListener('click', () => setLibraryMode('grid'));
    setLibraryMode(productState.libraryMode, false);
  }

  function rebuildPremiumGrid() {
    const grid = el('premiumLibraryGrid');
    if (!grid || productState.libraryMode !== 'grid') return;
    const source = state?.dashboard?.books || productState.dashboard?.books || [];
    const query = productState.libraryQuery;
    grid.innerHTML = source
      .filter(book => !query || `${book.title || ''} ${book.author || ''} ${book.series || ''}`.toLowerCase().includes(query))
      .map(card)
      .join('');
    wireDynamic();
    queueMicrotask(enhanceBookSurfaces);
  }

  function setLibraryMode(mode, persist = true) {
    productState.libraryMode = mode === 'grid' ? 'grid' : 'list';
    if (persist) localStorage.setItem('listenleaf-library-mode', productState.libraryMode);
    el('libraryListMode')?.classList.toggle('active', productState.libraryMode === 'list');
    el('libraryGridMode')?.classList.toggle('active', productState.libraryMode === 'grid');
    el('libraryList')?.classList.toggle('view-hidden', productState.libraryMode !== 'list');
    el('premiumLibraryGrid')?.classList.toggle('active', productState.libraryMode === 'grid');
    if (productState.libraryMode === 'grid') rebuildPremiumGrid();
    else applyLibraryFilter();
  }

  function applyLibraryFilter() {
    const query = productState.libraryQuery;
    document.querySelectorAll('#libraryList .library-row').forEach(row => {
      row.classList.toggle('hidden', !!query && !(row.dataset.search || row.textContent.toLowerCase()).includes(query));
    });
    if (productState.libraryMode === 'grid') rebuildPremiumGrid();
  }

  function createAppearanceEnhancer() {
    const themeSelect = el('themeSelect');
    const section = themeSelect?.closest('section');
    if (!section || section.querySelector('.appearance-enhancer')) return;
    const enhancer = document.createElement('div');
    enhancer.className = 'appearance-enhancer';
    enhancer.innerHTML = `
      <div class="appearance-row"><span>Accent</span><div class="accent-picker" role="group" aria-label="Accent color">
        <button class="accent-swatch" data-accent="emerald" type="button" title="Emerald"></button>
        <button class="accent-swatch" data-accent="azure" type="button" title="Azure"></button>
        <button class="accent-swatch" data-accent="violet" type="button" title="Violet"></button>
        <button class="accent-swatch" data-accent="amber" type="button" title="Amber"></button>
      </div></div>
      <div class="appearance-row"><span>Density</span><div class="segmented" role="group" aria-label="Interface density"><button id="densityComfortable" type="button">Comfortable</button><button id="densityCompact" type="button">Compact</button></div></div>`;
    themeSelect.closest('label')?.insertAdjacentElement('afterend', enhancer);
    enhancer.querySelectorAll('.accent-swatch').forEach(button => button.addEventListener('click', () => setAccent(button.dataset.accent)));
    el('densityComfortable')?.addEventListener('click', () => setDensity('comfortable'));
    el('densityCompact')?.addEventListener('click', () => setDensity('compact'));
    setAccent(productState.accent, false);
    setDensity(productState.density, false);
  }

  function setAccent(accent, persist = true) {
    const allowed = new Set(['emerald', 'azure', 'violet', 'amber']);
    productState.accent = allowed.has(accent) ? accent : 'emerald';
    document.documentElement.dataset.accent = productState.accent;
    document.querySelectorAll('.accent-swatch').forEach(button => button.classList.toggle('active', button.dataset.accent === productState.accent));
    if (persist) localStorage.setItem('listenleaf-accent', productState.accent);
  }

  function setDensity(density, persist = true) {
    productState.density = density === 'compact' ? 'compact' : 'comfortable';
    document.body.dataset.density = productState.density;
    el('densityComfortable')?.classList.toggle('active', productState.density === 'comfortable');
    el('densityCompact')?.classList.toggle('active', productState.density === 'compact');
    if (persist) localStorage.setItem('listenleaf-density', productState.density);
  }

  function updateHeroMetrics(dashboard) {
    const books = dashboard?.books || [];
    if (el('heroBookCount')) el('heroBookCount').textContent = books.length.toLocaleString();
    if (el('heroAudioCount')) el('heroAudioCount').textContent = books.filter(book => book.has_audio).length.toLocaleString();
    if (el('heroPrivacy')) el('heroPrivacy').textContent = dashboard?.generation ? 'Active' : 'Local';
  }

  function updateVoiceStatus(dashboard) {
    const ready = !!dashboard?.voice_ready;
    const homeStatus = el('homeVoiceStatus');
    const homeMeta = el('homeVoiceMeta');
    const action = el('homeVoiceAction');
    const readerState = el('readerVoiceState');
    if (homeStatus) homeStatus.textContent = ready ? 'Voice ready' : 'Voice setup required';
    if (homeMeta) homeMeta.textContent = ready ? 'Original reference is configured locally.' : 'Add your reference audio before generating.';
    if (action) action.textContent = ready ? 'Manage' : 'Set up voice';
    statusClass(homeStatus?.closest('.status-card'), ready ? 'is-ready' : 'is-warning');
    if (readerState) {
      const strong = readerState.querySelector('strong');
      const detail = readerState.querySelector('span:last-child');
      if (strong) strong.textContent = ready ? 'Voice ready' : 'Voice setup required';
      if (detail) detail.textContent = ready ? 'Your local reference will be used for this audiobook.' : 'Configure your original reference before generation.';
      statusClass(readerState, ready ? 'is-ready' : 'is-warning');
    }
  }

  function updateGenerationStatus(dashboard) {
    const generation = dashboard?.generation;
    const cardEl = el('homeGenerationStatus')?.closest('.status-card');
    const status = el('homeGenerationStatus');
    const meta = el('homeGenerationMeta');
    const bar = el('homeGenerationBar');
    if (!status || !meta || !bar) return;
    if (!generation) {
      status.textContent = 'Generation idle';
      meta.textContent = 'Ready for one local audiobook job';
      bar.value = 0;
      bar.classList.add('hidden');
      statusClass(cardEl, dashboard?.voice_ready ? 'is-ready' : '');
      return;
    }
    const percent = Math.max(0, Math.min(100, Number(generation.percent || 0)));
    const title = generation.title || 'Current book';
    const stage = typeof generationStage === 'function' ? generationStage(generation.stage) : (generation.stage || 'Working');
    status.textContent = `${stage} · ${Math.round(percent)}%`;
    meta.textContent = `${title} · ${generation.completed_chunks || 0}/${generation.total_chunks || '—'} chunks`;
    bar.value = percent;
    bar.classList.remove('hidden');
    statusClass(cardEl, 'is-active');
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
    updateHeroMetrics(dashboard);
    updateVoiceStatus(dashboard);
    updateGenerationStatus(dashboard);
    updateReaderGenerationGate(dashboard);
    enhanceBookSurfaces();
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

  createHero();
  createLibraryToolbar();
  createAppearanceEnhancer();
  setAccent(productState.accent, false);
  setDensity(productState.density, false);

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

  const booksObserver = new MutationObserver(() => queueMicrotask(enhanceBookSurfaces));
  if (el('bookGrid')) booksObserver.observe(el('bookGrid'), { childList: true });
  if (el('continueGrid')) booksObserver.observe(el('continueGrid'), { childList: true });
  if (el('libraryList')) booksObserver.observe(el('libraryList'), { childList: true });

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
