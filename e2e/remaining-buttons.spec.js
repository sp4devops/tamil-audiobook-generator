const { test, expect } = require('@playwright/test');

const baseBook = {
  id: 'book-1', title: 'Tamil Button Book', author: 'Local Author', series: 'Series A',
  source_format: 'txt', words: 20, characters: 120, has_audio: true, has_cues: true,
  audio_bytes: 2048, audio_seconds: 120, playable_chunks: 2,
  progress: { seconds: 60, duration: 120 }, text: 'வணக்கம் உலகம். Button audit.',
  cues: [{ index: 0, start: 0, end: 120, text: 'வணக்கம் உலகம். Button audit.' }],
  estimate: { chunks: 2, audio_seconds: 120, generation_seconds: 45, generation_mode: 'cool' },
};

function makeDashboard(overrides = {}) {
  return {
    books: [baseBook], continue_listening: [baseBook],
    playlists: [{ id: 'playlist-1', name: 'Tamil', books: ['book-1'] }],
    follows: { authors: [], series: [] }, activity: [{ title: baseBook.title, action: 'Imported' }],
    preferences: { playback_rate: 1, focus_mode: false, focus_minutes: 25, break_minutes: 5,
      reduce_motion: false, large_text: false, eq_preset: 'flat', ambience: 'off', theme: 'midnight',
      repeat_mode: 'off', shuffle: false, skip_seconds: 15, generation_mode: 'cool' },
    voice_ready: true, voice_source: 'original-source-local',
    storage: { library_bytes: 1024, generated_bytes: 2048, app_cache_bytes: 0 }, generation: null,
    ...overrides,
  };
}

const json = (route, body = { ok: true }) => route.fulfill({
  status: 200, contentType: 'application/json', body: JSON.stringify(body),
});

async function mockBase(page, overrides = {}) {
  await page.route('**/api/dashboard', route => json(route, makeDashboard(overrides)));
  await page.route('**/api/books/book-1', route => json(route, baseBook));
  await page.route('**/api/books/book-1/generation', route => json(route, { active: false }));
  await page.route('**/api/preferences', route => json(route));
  await page.route('**/api/books/book-1/audio', route => route.fulfill({ status: 200, contentType: 'audio/mpeg', body: '' }));
}

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

    HTMLElement.prototype.requestFullscreen = function() { return Promise.reject(new Error('headless fallback')); };
  });
}

test('play, pause, skip, adjacent and favorite transport controls execute', async ({ page }) => {
  await installBrowserStubs(page);
  const calls = [];
  await mockBase(page);
  await page.route('**/api/follows', route => { calls.push(route.request().postDataJSON()); return json(route); });
  await page.goto('/');
  await page.locator('[data-book="book-1"]').first().click();
  await expect(page.locator('#player')).not.toHaveClass(/hidden/);

  await page.locator('#playPause').click();
  await expect(page.locator('#playPause')).toHaveText('❚❚');
  await page.locator('#playPause').click();
  await expect(page.locator('#playPause')).toHaveText('▶');

  await page.locator('#audio').evaluate(audio => { audio.currentTime = 60; });
  await page.locator('#rewind').click();
  expect(await page.locator('#audio').evaluate(audio => audio.currentTime)).toBe(45);
  await page.locator('#forward').click();
  expect(await page.locator('#audio').evaluate(audio => audio.currentTime)).toBe(60);

  await page.locator('#previousButton').click();
  await expect(page.locator('#readerTitle')).toHaveText(baseBook.title);
  await page.locator('#nextButton').click();
  await expect(page.locator('#readerTitle')).toHaveText(baseBook.title);

  await page.locator('#favoriteButton').click();
  await expect.poll(() => calls.length).toBe(1);
  expect(calls[0]).toMatchObject({ kind: 'authors', value: 'Local Author', follow: true });
});

test('fullscreen, settings toggles, home voice action and reader back buttons remain functional', async ({ page }) => {
  await installBrowserStubs(page);
  await mockBase(page);
  await page.goto('/');

  await page.locator('#homeVoiceAction').click();
  await expect(page.locator('#settingsDialog')).toHaveAttribute('open', '');
  await page.locator('#settingsToggleNav').click();
  await expect(page.locator('body')).toHaveClass(/nav-collapsed/);
  await page.locator('#settingsToggleSound').click();
  await expect(page.locator('body')).toHaveClass(/sound-collapsed/);
  await page.locator('[data-close="settingsDialog"]').first().click();

  await page.locator('[data-book="book-1"]').first().click();
  await page.locator('#backFromReader').click();
  await expect(page.locator('#libraryView')).toHaveClass(/active-view/);

  await page.locator('[data-book="book-1"]').first().click();
  await page.locator('#fullscreenButton').click();
  await expect(page.locator('body')).toHaveClass(/fullscreen-reading/);
  await page.locator('#fullscreenToolbar').click();
  await expect(page.locator('body')).not.toHaveClass(/fullscreen-reading/);
  await page.locator('#playerFullscreen').click();
  await expect(page.locator('body')).toHaveClass(/fullscreen-reading/);
  await page.locator('#playerFullscreen').click();
  await expect(page.locator('body')).not.toHaveClass(/fullscreen-reading/);
});

test('equalizer and ambience preset buttons activate and persist their choices', async ({ page }) => {
  await installBrowserStubs(page);
  const preferences = [];
  await page.route('**/api/dashboard', route => json(route, makeDashboard()));
  await page.route('**/api/books/book-1', route => json(route, baseBook));
  await page.route('**/api/preferences', route => { preferences.push(route.request().postDataJSON()); return json(route); });
  await page.route('**/api/books/book-1/audio', route => route.fulfill({ status: 200, contentType: 'audio/mpeg', body: '' }));
  await page.goto('/');
  await page.locator('[data-book="book-1"]').first().click();
  await page.locator('#advancedSound').evaluate(node => { node.open = true; });

  await page.locator('[data-eq="warm"]').click();
  await expect(page.locator('[data-eq="warm"]')).toHaveClass(/active/);
  await page.locator('[data-ambience="rain"]').click();
  await expect(page.locator('[data-ambience="rain"]')).toHaveClass(/active/);
  await page.locator('[data-ambience="off"]').click();
  await expect(page.locator('[data-ambience="off"]')).toHaveClass(/active/);

  await expect.poll(() => preferences.length).toBeGreaterThanOrEqual(3);
  expect(preferences).toEqual(expect.arrayContaining([
    { eq_preset: 'warm' }, { ambience: 'rain' }, { ambience: 'off' },
  ]));
});

test('clear audio, delete book, clear activity and delete playlist buttons call destructive APIs only after confirmation', async ({ page }) => {
  await installBrowserStubs(page);
  const calls = [];
  await mockBase(page);
  for (const pattern of ['**/api/books/book-1/audio', '**/api/books/book-1', '**/api/activity', '**/api/playlists/playlist-1']) {
    await page.route(pattern, route => {
      if (route.request().method() !== 'GET') calls.push({ url: route.request().url(), method: route.request().method() });
      if (route.request().url().endsWith('/audio') && route.request().method() === 'GET') return route.fulfill({ status: 200, contentType: 'audio/mpeg', body: '' });
      if (route.request().url().endsWith('/book-1') && route.request().method() === 'GET') return json(route, baseBook);
      return json(route);
    });
  }
  await page.goto('/');
  await page.locator('[data-book="book-1"]').first().click();
  await page.locator('.book-management').evaluate(node => { node.open = true; });

  await page.locator('#clearAudio').click();
  await page.locator('#confirmYes').click();
  await expect.poll(() => calls.some(c => c.url.endsWith('/api/books/book-1/audio') && c.method === 'DELETE')).toBeTruthy();

  await page.locator('.book-management').evaluate(node => { node.open = true; });
  await page.locator('#deleteBook').click();
  await page.locator('#confirmYes').click();
  await expect.poll(() => calls.some(c => c.url.endsWith('/api/books/book-1') && c.method === 'DELETE')).toBeTruthy();

  await page.getByRole('button', { name: 'Following' }).click();
  await page.locator('#clearActivity').click();
  await expect.poll(() => calls.some(c => c.url.endsWith('/api/activity') && c.method === 'DELETE')).toBeTruthy();

  await page.getByRole('button', { name: 'Playlists' }).click();
  await page.locator('[data-playlist="playlist-1"]').click();
  await page.locator('#deletePlaylist').click();
  await page.locator('#confirmYes').click();
  await expect.poll(() => calls.some(c => c.url.endsWith('/api/playlists/playlist-1') && c.method === 'DELETE')).toBeTruthy();
});