const { test, expect } = require('@playwright/test');

const audioBook = {
  id: 'book-1',
  title: 'Tamil Audio Book',
  author: 'Local Author',
  series: 'Series A',
  source_format: 'txt',
  words: 20,
  characters: 120,
  has_audio: true,
  has_cues: true,
  audio_bytes: 2048,
  audio_seconds: 120,
  playable_chunks: 2,
  progress: { seconds: 20, duration: 120 },
  text: 'வணக்கம் உலகம். Audio ready.',
  cues: [{ index: 0, start: 0, end: 120, text: 'வணக்கம் உலகம். Audio ready.' }],
  estimate: { chunks: 2, audio_seconds: 120, generation_seconds: 45, generation_mode: 'cool' },
};

function dashboard(overrides = {}) {
  return {
    books: [audioBook],
    continue_listening: [audioBook],
    playlists: [{ id: 'playlist-1', name: 'Tamil', books: ['book-1'] }],
    follows: { authors: [], series: [] },
    activity: [{ title: 'Tamil Audio Book', action: 'Imported' }],
    preferences: {
      playback_rate: 1,
      focus_mode: false,
      focus_minutes: 25,
      break_minutes: 5,
      reduce_motion: false,
      large_text: false,
      eq_preset: 'flat',
      ambience: 'off',
      theme: 'midnight',
      repeat_mode: 'off',
      shuffle: false,
      skip_seconds: 15,
      generation_mode: 'cool',
    },
    voice_ready: true,
    voice_source: 'original-source-local',
    storage: { library_bytes: 1024, generated_bytes: 2048, app_cache_bytes: 256 },
    generation: null,
    ...overrides,
  };
}

function fulfillJson(route, body = { ok: true }) {
  return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
}

async function bootstrap(page, overrides = {}) {
  await page.route('**/api/dashboard', route => fulfillJson(route, dashboard(overrides)));
  await page.route('**/api/books/book-1', route => fulfillJson(route, audioBook));
  await page.route('**/api/books/book-1/generation', route => fulfillJson(route, { active: false }));
  await page.route('**/api/preferences', route => fulfillJson(route));
}

test('settings destructive buttons respect confirmation and call the intended APIs', async ({ page }) => {
  const calls = [];
  await bootstrap(page);
  for (const pattern of ['**/api/cache', '**/api/progress', '**/api/activity', '**/api/reset', '**/api/voice-reference']) {
    await page.route(pattern, route => {
      calls.push({ url: route.request().url(), method: route.request().method(), body: route.request().postData() });
      return fulfillJson(route);
    });
  }
  await page.goto('/');
  await page.locator('#settingsButton').click();

  await page.locator('#clearCache').click();
  await expect.poll(() => calls.some(c => c.url.endsWith('/api/cache') && c.method === 'DELETE')).toBeTruthy();

  await page.locator('#clearProgress').click();
  await expect(page.locator('#confirmDialog')).toHaveAttribute('open', '');
  await page.locator('#confirmCancel').click();
  expect(calls.some(c => c.url.endsWith('/api/progress'))).toBeFalsy();
  await page.locator('#clearProgress').click();
  await page.locator('#confirmYes').click();
  await expect.poll(() => calls.some(c => c.url.endsWith('/api/progress') && c.method === 'DELETE')).toBeTruthy();

  await page.locator('#clearAllActivity').click();
  await expect.poll(() => calls.some(c => c.url.endsWith('/api/activity') && c.method === 'DELETE')).toBeTruthy();

  await page.locator('#deleteVoice').click();
  await page.locator('#confirmCancel').click();
  expect(calls.some(c => c.url.endsWith('/api/voice-reference'))).toBeFalsy();
  await page.locator('#deleteVoice').click();
  await page.locator('#confirmYes').click();
  await expect.poll(() => calls.some(c => c.url.endsWith('/api/voice-reference') && c.method === 'DELETE')).toBeTruthy();

  await page.locator('#resetAllData').click();
  await expect(page.locator('#confirmDialog')).toHaveAttribute('open', '');
  await page.locator('#confirmCancel').click();
  expect(calls.some(c => c.url.endsWith('/api/reset'))).toBeFalsy();
});

test('voice save validates required input and submits a local reference when complete', async ({ page }) => {
  let saved = null;
  await bootstrap(page, { voice_ready: false, voice_source: null });
  await page.route('**/api/voice-reference', async route => {
    if (route.request().method() === 'POST') saved = route.request().postDataBuffer();
    return fulfillJson(route);
  });
  await page.goto('/');
  await page.locator('#settingsButton').click();

  await page.locator('#saveVoice').click();
  await expect(page.locator('#voiceState')).toContainText('Choose reference audio');

  await page.locator('#voiceTranscript').fill('Exact reference transcript');
  await page.locator('#voiceReference').setInputFiles({
    name: 'voice.wav',
    mimeType: 'audio/wav',
    buffer: Buffer.from('RIFF-local-test'),
  });
  await page.locator('#saveVoice').click();
  await expect.poll(() => saved !== null).toBeTruthy();
  await expect(page.locator('#voiceState')).toContainText('saved and normalized locally');
});

test('reader mutation buttons call follow, progress, edit and playlist APIs', async ({ page }) => {
  const calls = [];
  await bootstrap(page);
  const capture = pattern => page.route(pattern, route => {
    calls.push({ url: route.request().url(), method: route.request().method(), body: route.request().postData() });
    if (route.request().url().endsWith('/api/playlists') && route.request().method() === 'POST') {
      return fulfillJson(route, { id: 'playlist-new', name: 'New list', books: [] });
    }
    return fulfillJson(route);
  });
  await capture('**/api/follows');
  await capture('**/api/books/book-1/progress');
  await capture('**/api/playlists');
  await capture('**/api/playlists/*');
  await page.route('**/api/books/book-1', route => {
    if (route.request().method() === 'PATCH') {
      calls.push({ url: route.request().url(), method: 'PATCH', body: route.request().postData() });
      return fulfillJson(route, { ...audioBook, title: 'Edited title' });
    }
    return fulfillJson(route, audioBook);
  });

  await page.goto('/');
  await page.locator('[data-book="book-1"]').first().click();

  await page.locator('#followAuthor').click();
  await expect.poll(() => calls.some(c => c.url.endsWith('/api/follows') && c.method === 'POST')).toBeTruthy();

  await page.locator('#resetBookProgress').click();
  await expect.poll(() => calls.some(c => c.url.endsWith('/api/books/book-1/progress') && c.method === 'DELETE')).toBeTruthy();

  await page.locator('#editBook').click();
  await page.locator('#editBookTitle').fill('Edited title');
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect.poll(() => calls.some(c => c.url.endsWith('/api/books/book-1') && c.method === 'PATCH')).toBeTruthy();

  await page.locator('#addPlaylist').click();
  await page.locator('#playlistName').fill('New list');
  await page.getByRole('button', { name: 'Save playlist' }).click();
  await expect.poll(() => calls.some(c => c.url.endsWith('/api/playlists') && c.method === 'POST')).toBeTruthy();
  await expect.poll(() => calls.some(c => c.url.endsWith('/api/playlists/playlist-new') && c.method === 'PATCH')).toBeTruthy();
});

test('player transport buttons change playback UI state and settings', async ({ page }) => {
  const preferences = [];
  await page.route('**/api/dashboard', route => fulfillJson(route, dashboard()));
  await page.route('**/api/books/book-1', route => fulfillJson(route, audioBook));
  await page.route('**/api/preferences', route => {
    preferences.push(route.request().postDataJSON());
    return fulfillJson(route);
  });
  await page.route('**/api/books/book-1/audio', route => route.fulfill({
    status: 200,
    contentType: 'audio/mpeg',
    body: '',
  }));

  await page.goto('/');
  await page.locator('[data-book="book-1"]').first().click();
  await expect(page.locator('#player')).not.toHaveClass(/hidden/);

  await page.locator('#muteButton').click();
  await expect(page.locator('#muteButton')).toHaveText('🔇');
  await expect(page.locator('#volume')).toHaveValue('0');
  await page.locator('#muteButton').click();
  await expect(page.locator('#muteButton')).toHaveText('🔊');

  await page.locator('#speedButton').click();
  await expect(page.locator('#speedButton')).toHaveText('1.1×');
  await page.locator('#sleepButton').click();
  await expect(page.locator('#sleepButton')).toHaveText('☾ 15m');
  await page.locator('#shuffleButton').click();
  await expect(page.locator('#shuffleButton')).toHaveClass(/active/);
  await page.locator('#repeatButton').click();
  await expect(page.locator('#repeatButton')).toHaveClass(/active/);

  await page.locator('#readerShortcut').click();
  await expect(page.locator('#readerView')).toHaveClass(/active-view/);

  await expect.poll(() => preferences.length).toBeGreaterThanOrEqual(3);
  expect(preferences).toEqual(expect.arrayContaining([
    { playback_rate: 1.1 },
    { shuffle: true },
    { repeat_mode: 'all' },
  ]));
});