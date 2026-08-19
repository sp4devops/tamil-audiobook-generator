const { test, expect } = require('@playwright/test');

const readyBook = {
  id: 'book-1', title: 'Tamil Button Book', author: 'Local Author', series: 'Series A',
  source_format: 'txt', words: 20, characters: 120, has_audio: true, has_cues: true,
  audio_bytes: 2048, audio_seconds: 120, playable_chunks: 2,
  progress: { seconds: 60, duration: 120 }, text: 'வணக்கம் உலகம். Button audit.',
  cues: [{ index: 0, start: 0, end: 120, text: 'வணக்கம் உலகம். Button audit.' }],
  estimate: { chunks: 2, audio_seconds: 120, generation_seconds: 45, generation_mode: 'cool' },
};

const textBook = {
  ...readyBook,
  has_audio: false,
  has_cues: false,
  audio_bytes: 0,
  audio_seconds: 0,
  playable_chunks: 0,
  progress: { seconds: 0, duration: 0 },
  cues: [],
  estimate: { chunks: 1, audio_seconds: 6, generation_seconds: 1, generation_mode: 'cool' },
};

function dashboard({ book = readyBook, books = null, follows = null, playlists = null } = {}) {
  const list = books ?? [book];
  return {
    books: list,
    continue_listening: list.filter(item => item.has_audio),
    playlists: playlists ?? [{ id: 'playlist-1', name: 'Tamil', books: list.map(item => item.id) }],
    follows: follows ?? { authors: [], series: [] },
    activity: list.length ? [{ title: list[0].title, action: 'Imported' }] : [],
    preferences: {
      playback_rate: 1, focus_mode: false, focus_minutes: 25, break_minutes: 5,
      reduce_motion: false, large_text: false, eq_preset: 'flat', ambience: 'off', theme: 'midnight',
      repeat_mode: 'off', shuffle: false, skip_seconds: 15, generation_mode: 'cool',
    },
    voice_ready: true,
    voice_source: 'original-source-local',
    storage: { library_bytes: list.length ? 1024 : 0, generated_bytes: list.some(item => item.has_audio) ? 2048 : 0, app_cache_bytes: 0 },
    generation: null,
  };
}

const json = (route, body = { ok: true }) => route.fulfill({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify(body),
});

async function installBrowserStubs(page) {
  await page.addInitScript(() => {
    class NodeStub {
      constructor() {
        this.gain = { value: 0 };
        this.frequency = { value: 0 };
        this.Q = { value: 0 };
      }
      connect(target) { return target; }
      stop() {}
      start() {}
    }
    class AudioContextStub {
      constructor() { this.state = 'running'; this.sampleRate = 8000; this.destination = new NodeStub(); }
      createMediaElementSource() { return new NodeStub(); }
      createBiquadFilter() { return new NodeStub(); }
      createGain() { return new NodeStub(); }
      createBuffer() { return { getChannelData: () => new Float32Array(16) }; }
      createBufferSource() { return new NodeStub(); }
      resume() { this.state = 'running'; return Promise.resolve(); }
    }
    window.AudioContext = AudioContextStub;
    window.webkitAudioContext = AudioContextStub;

    Object.defineProperty(HTMLMediaElement.prototype, 'paused', { configurable: true, get() { return this.__paused !== false; } });
    Object.defineProperty(HTMLMediaElement.prototype, 'duration', { configurable: true, get() { return 120; } });
    Object.defineProperty(HTMLMediaElement.prototype, 'currentTime', {
      configurable: true,
      get() { return this.__currentTime || 0; },
      set(value) { this.__currentTime = Number(value) || 0; },
    });
    HTMLMediaElement.prototype.play = function() { this.__paused = false; return Promise.resolve(); };
    HTMLMediaElement.prototype.pause = function() { this.__paused = true; };

    window.__downloads = [];
    HTMLAnchorElement.prototype.click = function() {
      window.__downloads.push({ href: this.href, download: this.download });
    };
  });
}

async function mockReadyBook(page, customDashboard = dashboard()) {
  await page.route('**/api/dashboard', route => json(route, customDashboard));
  await page.route('**/api/books/book-1', route => json(route, readyBook));
  await page.route('**/api/books/book-1/generation', route => json(route, { active: false }));
  await page.route('**/api/books/book-1/audio', route => route.fulfill({ status: 200, contentType: 'audio/mpeg', body: '' }));
  await page.route('**/api/preferences', route => json(route));
}

test('generate, reader play and export MP3 buttons complete the audiobook lifecycle', async ({ page }) => {
  await installBrowserStubs(page);
  let generated = false;
  const currentBook = () => generated ? readyBook : textBook;

  await page.route('**/api/dashboard', route => json(route, dashboard({ book: currentBook() })));
  await page.route('**/api/books/book-1/generation', route => json(route, { active: false }));
  await page.route('**/api/books/book-1/generate', route => {
    generated = true;
    return json(route, {
      job_id: 'job-1', status: 'queued',
      estimate: { chunks: 1, audio_seconds: 6, generation_seconds: 1, generation_mode: 'cool' },
    });
  });
  await page.route('**/api/jobs/job-1', route => json(route, {
    job_id: 'job-1', book_id: 'book-1', status: 'completed', stage: 'completed', percent: 100,
    completed_chunks: 1, playable_chunks: 1, total_chunks: 1, audio_seconds: 6,
    aggregate_rtf: 0.5, elapsed_seconds: 1, estimated_remaining_seconds: 0,
  }));
  await page.route('**/api/books/book-1', route => json(route, currentBook()));
  await page.route('**/api/books/book-1/audio', route => route.fulfill({ status: 200, contentType: 'audio/mpeg', body: '' }));
  await page.route('**/api/preferences', route => json(route));

  await page.goto('/');
  await page.locator('[data-book="book-1"]').first().click();
  await expect(page.locator('#generateButton')).toHaveText('Generate audiobook');
  await page.locator('#generateButton').click();

  await expect(page.locator('#generationStatus')).toContainText('Ready');
  await expect(page.locator('#readerPlayButton')).toBeVisible();
  await expect(page.locator('#exportAudio')).toBeEnabled();

  await page.locator('#readerPlayButton').click();
  await expect(page.locator('#player')).not.toHaveClass(/hidden/);

  await page.locator('#exportAudio').click();
  await expect.poll(() => page.evaluate(() => window.__downloads.length)).toBe(1);
  const download = await page.evaluate(() => window.__downloads[0]);
  expect(download.href).toContain('/api/books/book-1/audio');
  expect(download.download).toBe('Tamil Button Book.mp3');
});

test('direct card play, row play and both library mode buttons work', async ({ page }) => {
  await installBrowserStubs(page);
  await mockReadyBook(page);
  await page.goto('/');

  await page.locator('#bookGrid [data-play-book="book-1"]').click();
  await expect(page.locator('#readerView')).toHaveClass(/active-view/);
  await expect(page.locator('#player')).not.toHaveClass(/hidden/);

  await page.locator('#backFromReader').click();
  await page.locator('#libraryGridMode').click();
  await expect(page.locator('#premiumLibraryGrid')).toHaveClass(/active/);
  await page.locator('#libraryListMode').click();
  await expect(page.locator('#libraryListMode')).toHaveClass(/active/);
  await expect(page.locator('#premiumLibraryGrid')).not.toHaveClass(/active/);

  await page.locator('#libraryList [data-play-book="book-1"]').click();
  await expect(page.locator('#readerView')).toHaveClass(/active-view/);
  await expect(page.locator('#player')).not.toHaveClass(/hidden/);
});

test('every appearance, equalizer and ambience preset button selects its own state', async ({ page }) => {
  await installBrowserStubs(page);
  const preferences = [];
  await page.route('**/api/dashboard', route => json(route, dashboard()));
  await page.route('**/api/books/book-1', route => json(route, readyBook));
  await page.route('**/api/books/book-1/generation', route => json(route, { active: false }));
  await page.route('**/api/books/book-1/audio', route => route.fulfill({ status: 200, contentType: 'audio/mpeg', body: '' }));
  await page.route('**/api/preferences', route => { preferences.push(route.request().postDataJSON()); return json(route); });
  await page.goto('/');

  await page.locator('#settingsButton').click();
  for (const accent of ['emerald', 'azure', 'violet', 'amber']) {
    await page.locator(`.accent-swatch[data-accent="${accent}"]`).click();
    await expect(page.locator('html')).toHaveAttribute('data-accent', accent);
  }
  await page.locator('#densityCompact').click();
  await expect(page.locator('body')).toHaveAttribute('data-density', 'compact');
  await page.locator('#densityComfortable').click();
  await expect(page.locator('body')).toHaveAttribute('data-density', 'comfortable');
  await page.locator('[data-close="settingsDialog"]').first().click();

  await page.locator('[data-book="book-1"]').first().click();
  await page.locator('#advancedSound').evaluate(node => { node.open = true; });
  for (const preset of ['flat', 'voice', 'warm', 'bright']) {
    await page.locator(`[data-eq="${preset}"]`).click();
    await expect(page.locator(`[data-eq="${preset}"]`)).toHaveClass(/active/);
  }
  for (const ambience of ['off', 'rain', 'brown']) {
    await page.locator(`[data-ambience="${ambience}"]`).click();
    await expect(page.locator(`[data-ambience="${ambience}"]`)).toHaveClass(/active/);
  }

  await expect.poll(() => preferences.length).toBeGreaterThanOrEqual(7);
  expect(preferences).toEqual(expect.arrayContaining([
    { eq_preset: 'flat' }, { eq_preset: 'voice' }, { eq_preset: 'warm' }, { eq_preset: 'bright' },
    { ambience: 'off' }, { ambience: 'rain' }, { ambience: 'brown' },
  ]));
});

test('new playlist and author and series unfollow buttons execute their contracts', async ({ page }) => {
  const calls = [];
  const d = dashboard({ follows: { authors: ['Local Author'], series: ['Series A'] }, playlists: [] });
  await page.route('**/api/dashboard', route => json(route, d));
  await page.route('**/api/follows', route => { calls.push(route.request().postDataJSON()); return json(route); });
  await page.route('**/api/preferences', route => json(route));
  await page.goto('/');

  await page.getByRole('button', { name: 'Following' }).click();
  await page.locator('[data-unfollow-author="Local Author"]').click();
  await expect.poll(() => calls.some(call => call.kind === 'authors' && call.follow === false)).toBeTruthy();
  await page.locator('[data-unfollow-series="Series A"]').click();
  await expect.poll(() => calls.some(call => call.kind === 'series' && call.follow === false)).toBeTruthy();

  await page.getByRole('button', { name: 'Playlists' }).click();
  await page.locator('#newPlaylist').click();
  await expect(page.locator('#playlistDialog')).toHaveAttribute('open', '');
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.locator('#playlistDialog')).not.toHaveAttribute('open', '');
});

test('empty-library import button and successful local import submit work', async ({ page }) => {
  let imported = false;
  let importCalled = false;
  await page.route('**/api/dashboard', route => json(route, dashboard({ books: imported ? [textBook] : [], playlists: [] })));
  await page.route('**/api/books/import', route => {
    importCalled = true;
    imported = true;
    return json(route, { id: 'book-1' });
  });
  await page.route('**/api/preferences', route => json(route));
  await page.goto('/');

  await expect(page.locator('#emptyLibrary')).not.toHaveClass(/hidden/);
  await page.locator('#emptyLibrary button').click();
  await expect(page.locator('#importDialog')).toHaveAttribute('open', '');
  await page.locator('#dialogBookFile').setInputFiles({
    name: 'local-book.txt', mimeType: 'text/plain', buffer: Buffer.from('வணக்கம் local import'),
  });
  await page.locator('#confirmImport').click();

  await expect.poll(() => importCalled).toBeTruthy();
  await expect(page.locator('#importDialog')).not.toHaveAttribute('open', '');
  await expect(page.locator('#libraryView')).toHaveClass(/active-view/);
  await expect(page.locator('#libraryList [data-book="book-1"]')).toBeVisible();
});

test('all dialog close and cancel buttons close the dialog they belong to', async ({ page }) => {
  await mockReadyBook(page);
  await page.goto('/');

  const exerciseTwoClosers = async (open, dialogId) => {
    await open();
    await expect(page.locator(`#${dialogId}`)).toHaveAttribute('open', '');
    await page.locator(`[data-close="${dialogId}"]`).nth(0).click();
    await expect(page.locator(`#${dialogId}`)).not.toHaveAttribute('open', '');
    await open();
    await page.locator(`[data-close="${dialogId}"]`).nth(1).click();
    await expect(page.locator(`#${dialogId}`)).not.toHaveAttribute('open', '');
  };

  await exerciseTwoClosers(() => page.locator('#importButton').click(), 'importDialog');
  await exerciseTwoClosers(() => page.locator('#settingsButton').click(), 'settingsDialog');

  await page.locator('[data-book="book-1"]').first().click();
  await exerciseTwoClosers(() => page.locator('#editBook').click(), 'editBookDialog');
  await exerciseTwoClosers(() => page.locator('#addPlaylist').click(), 'playlistDialog');
});

test('confirmed delete-all-data button calls reset API and returns home', async ({ page }) => {
  let resetBody = null;
  let reset = false;
  await page.route('**/api/dashboard', route => json(route, dashboard({ books: reset ? [] : [readyBook], playlists: reset ? [] : undefined })));
  await page.route('**/api/reset', route => {
    resetBody = route.request().postDataJSON();
    reset = true;
    return json(route);
  });
  await page.route('**/api/preferences', route => json(route));
  await page.goto('/');

  await page.locator('#settingsButton').click();
  await page.locator('#resetAllData').click();
  await expect(page.locator('#confirmDialog')).toHaveAttribute('open', '');
  await page.locator('#confirmYes').click();

  await expect.poll(() => resetBody !== null).toBeTruthy();
  expect(resetBody).toEqual({ confirmation: 'DELETE ALL LOCAL DATA' });
  await expect(page.locator('#settingsDialog')).not.toHaveAttribute('open', '');
  await expect(page.locator('#homeView')).toHaveClass(/active-view/);
});