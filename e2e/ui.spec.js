const { test, expect } = require('@playwright/test');

const book = {
  id: 'book-1',
  title: 'Tamil E2E Book',
  author: 'Local Author',
  series: '',
  source_format: 'txt',
  words: 8,
  characters: 55,
  has_audio: false,
  has_cues: false,
  audio_bytes: 0,
  playable_chunks: 0,
  progress: { seconds: 0, duration: 0 },
  text: 'வணக்கம் உலகம். This is a browser lifecycle smoke test.',
  cues: [],
  estimate: {
    chunks: 1,
    audio_seconds: 6,
    generation_seconds: 30,
    generation_mode: 'cool',
  },
};

const dashboard = {
  books: [book],
  continue_listening: [],
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
  storage: { library_bytes: 1024, generated_bytes: 0, app_cache_bytes: 0 },
  generation: null,
};

function json(route, body) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

test('library opens reader and progressive lifecycle without browser errors', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));

  await page.route('**/api/dashboard', route => json(route, dashboard));
  await page.route('**/api/books/book-1/generation', route => json(route, { active: false }));
  await page.route('**/api/books/book-1', route => json(route, book));

  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Good listening' })).toBeVisible();
  await expect(page.locator('#premiumHero')).toBeVisible();
  await expect(page.locator('#premiumHero')).toContainText('Turn reading into');
  await expect(page.locator('#heroBookCount')).toHaveText('1');
  await expect(page.getByText('Tamil E2E Book').first()).toBeVisible();
  await expect(page.getByText('✓ Original source voice is configured locally.')).toBeAttached();
  await expect(page.locator('#homeVoiceStatus')).toHaveText('Voice ready');
  await expect(page.locator('#homeGenerationStatus')).toHaveText('Generation idle');

  await page.locator('[data-book="book-1"]').first().click();
  await expect(page.locator('#readerView')).toHaveClass(/active-view/);
  await expect(page.locator('#readerTitle')).toHaveText('Tamil E2E Book');
  await expect(page.locator('#readalong')).toContainText('browser lifecycle smoke test');
  await expect(page.locator('#readerVoiceState')).toContainText('Voice ready');
  await expect(page.locator('#advancedSound')).not.toHaveAttribute('open', '');
  await expect(page.locator('#exportAudio')).toBeDisabled();

  await page.locator('#settingsButton').click();
  await expect(page.locator('#settingsDialog')).toHaveAttribute('open', '');
  await expect(page.locator('.appearance-enhancer')).toBeVisible();

  expect(pageErrors).toEqual([]);
});

test('premium library controls filter, switch views and persist appearance choices', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));

  await page.route('**/api/dashboard', route => json(route, dashboard));
  await page.goto('/');

  await page.getByRole('button', { name: 'Your Library' }).click();
  await expect(page.locator('#libraryToolbar')).toBeVisible();
  await expect(page.locator('#libraryList .library-row')).toHaveCount(1);

  await page.locator('#librarySearch').fill('not present');
  await expect(page.locator('#libraryList .library-row')).toHaveClass(/hidden/);
  await page.locator('#librarySearch').fill('Tamil');
  await expect(page.locator('#libraryList .library-row')).not.toHaveClass(/hidden/);

  await page.locator('#libraryGridMode').click();
  await expect(page.locator('#premiumLibraryGrid')).toHaveClass(/active/);
  await expect(page.locator('#premiumLibraryGrid [data-book="book-1"]')).toBeVisible();
  await expect(page.locator('#premiumLibraryGrid .book-badge')).toHaveText('TXT');

  await page.locator('#settingsButton').click();
  await page.locator('.accent-swatch[data-accent="violet"]').click();
  await page.locator('#densityCompact').click();
  await expect(page.locator('html')).toHaveAttribute('data-accent', 'violet');
  await expect(page.locator('body')).toHaveAttribute('data-density', 'compact');
  expect(await page.evaluate(() => localStorage.getItem('listenleaf-accent'))).toBe('violet');
  expect(await page.evaluate(() => localStorage.getItem('listenleaf-density'))).toBe('compact');

  expect(pageErrors).toEqual([]);
});

test('import failure stays in context and can be retried', async ({ page }) => {
  await page.route('**/api/dashboard', route => json(route, dashboard));
  await page.route('**/api/books/import', route => route.fulfill({
    status: 400,
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'Unsupported or unreadable book file' }),
  }));

  await page.goto('/');
  await page.locator('#importButton').click();
  await page.locator('#dialogBookFile').setInputFiles({
    name: 'broken.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('not a real book'),
  });
  await expect(page.locator('#importTitle')).toHaveValue('broken');
  await page.locator('#confirmImport').click();

  await expect(page.locator('#importDialog')).toHaveAttribute('open', '');
  await expect(page.locator('#importStatus')).toContainText('Unsupported or unreadable book file');
  await expect(page.locator('#confirmImport')).toBeEnabled();
});
