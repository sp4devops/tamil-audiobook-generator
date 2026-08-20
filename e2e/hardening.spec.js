const { test, expect } = require('@playwright/test');

const cues = Array.from({ length: 5 }, (_, index) => ({
  index,
  start: index * 10,
  end: index * 10 + 9,
  text: `chunk ${index + 1}`,
  language: 'tamil',
}));
const book = {
  id: 'book-hardening',
  title: 'Hardening Book',
  author: 'Local',
  series: '',
  source_format: 'txt',
  words: 20,
  characters: 100,
  has_audio: false,
  has_cues: true,
  audio_bytes: 0,
  playable_chunks: 5,
  progress: { seconds: 40, duration: 90 },
  text: cues.map(item => item.text).join('. '),
  cues,
  estimate: { chunks: 5, audio_seconds: 90, generation_seconds: 120, generation_mode: 'cool' },
};
const dashboard = {
  books: [book],
  continue_listening: [book],
  playlists: [],
  follows: { authors: [], series: [] },
  activity: [],
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
  storage: { library_bytes: 1000, generated_bytes: 0, app_cache_bytes: 0 },
  generation: null,
};

function respond(route, body) {
  return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockBook(page, progressPosts = []) {
  await page.route('**/api/dashboard', route => respond(route, dashboard));
  await page.route('**/api/books/book-hardening/generation', route => respond(route, { active: false }));
  await page.route('**/api/books/book-hardening/progress', async route => {
    if (route.request().method() === 'POST') progressPosts.push(route.request().postDataJSON());
    await respond(route, { ok: true });
  });
  await page.route('**/api/books/book-hardening', route => respond(route, book));
  await page.route('**/api/preferences', route => respond(route, { ok: true }));
  await page.route('**/api/books/book-hardening/chunks/**', route => route.fulfill({
    status: 200,
    contentType: 'audio/flac',
    body: Buffer.from('not-needed-for-metadata-test'),
  }));
}

test('chunk 5 progress persists absolute book position and whole-book duration', async ({ page }) => {
  const posts = [];
  await mockBook(page, posts);
  await page.goto('/');
  await page.locator('[data-book="book-hardening"]').first().click();
  await page.locator('#readerPlayButton').click();

  await page.evaluate(() => {
    const media = document.querySelector('#audio');
    Object.defineProperty(media, 'duration', { configurable: true, value: 9 });
    Object.defineProperty(media, 'currentTime', { configurable: true, writable: true, value: 3 });
    if (typeof media.onloadedmetadata === 'function') media.onloadedmetadata();
    media.currentTime = 3;
  });
  // The saver is intentionally throttled; make the first canonical save eligible.
  await page.waitForTimeout(5100);
  await page.evaluate(() => {
    const media = document.querySelector('#audio');
    media.currentTime = 3;
    if (typeof media.ontimeupdate === 'function') media.ontimeupdate();
    else media.dispatchEvent(new Event('timeupdate'));
  });

  await expect.poll(() => posts.length).toBeGreaterThan(0);
  const saved = posts.at(-1);
  expect(saved.seconds).toBe(43);
  expect(saved.duration).toBe(90);
  expect(saved).not.toEqual({ seconds: 3, duration: 9 });
});

test('confirmation resolves false on Escape and programmatic close without hanging', async ({ page }) => {
  await mockBook(page);
  await page.goto('/');

  await page.evaluate(() => {
    window.__confirmResults = [];
    confirmAction('Escape?', 'Close me', 'Yes').then(value => window.__confirmResults.push(value));
  });
  await expect(page.locator('#confirmDialog')).toHaveAttribute('open', '');
  await page.keyboard.press('Escape');
  await expect.poll(() => page.evaluate(() => window.__confirmResults.length)).toBe(1);
  expect(await page.evaluate(() => window.__confirmResults[0])).toBe(false);

  await page.evaluate(() => {
    confirmAction('Programmatic?', 'Close me too', 'Yes').then(value => window.__confirmResults.push(value));
  });
  await expect(page.locator('#confirmDialog')).toHaveAttribute('open', '');
  await page.evaluate(() => document.querySelector('#confirmDialog').close());
  await expect.poll(() => page.evaluate(() => window.__confirmResults.length)).toBe(2);
  expect(await page.evaluate(() => window.__confirmResults[1])).toBe(false);
});

test('clear audio remains disabled while generation is active', async ({ page }) => {
  await mockBook(page);
  await page.unroute('**/api/books/book-hardening/generation');
  await page.route('**/api/books/book-hardening/generation', route => respond(route, {
    active: true,
    job_id: 'abc123',
    book_id: 'book-hardening',
    status: 'running',
    stage: 'synthesizing',
    playable_chunks: 5,
    total_chunks: 10,
    percent: 50,
  }));
  await page.route('**/api/jobs/abc123', route => respond(route, {
    job_id: 'abc123',
    book_id: 'book-hardening',
    status: 'running',
    stage: 'synthesizing',
    playable_chunks: 5,
    total_chunks: 10,
    percent: 50,
  }));
  await page.goto('/');
  await page.locator('[data-book="book-hardening"]').first().click();
  await expect(page.locator('#clearAudio')).toBeDisabled();
  await expect(page.locator('#cancelGeneration')).toBeVisible();
});
