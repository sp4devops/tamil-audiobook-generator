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

async function mockCommonApi(page, customDashboard = dashboard) {
  await page.route('**/api/dashboard', route => json(route, customDashboard));
  await page.route('**/api/preferences', route => json(route, { ok: true }));
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

test('premium mobile layout keeps navigation usable and avoids horizontal overflow', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));

  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/api/dashboard', route => json(route, dashboard));
  await page.route('**/api/books/book-1/generation', route => json(route, { active: false }));
  await page.route('**/api/books/book-1', route => json(route, book));
  await page.goto('/');

  await expect(page.locator('#premiumHero')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Home' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Your Library' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Following' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Playlists' })).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  await page.getByRole('button', { name: 'Your Library' }).click();
  await expect(page.locator('#libraryToolbar')).toBeVisible();
  await expect(page.locator('#librarySearch')).toBeVisible();
  await expect(page.locator('#libraryList [data-book="book-1"]')).toBeVisible();

  await page.locator('#libraryList [data-book="book-1"]').click();
  await expect(page.locator('#readerView')).toHaveClass(/active-view/);
  await expect(page.locator('#readerTitle')).toBeVisible();
  await expect(page.locator('#generateButton')).toBeVisible();
  await expect(page.locator('#readalong')).toBeVisible();

  const readerOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(readerOverflow).toBeLessThanOrEqual(1);
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

test('top-level navigation, hero, settings and focus buttons perform their UI contracts', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await mockCommonApi(page);
  await page.goto('/');

  await page.locator('#heroLibrary').click();
  await expect(page.locator('#libraryView')).toHaveClass(/active-view/);
  await page.getByRole('button', { name: 'Following' }).click();
  await expect(page.locator('#followingView')).toHaveClass(/active-view/);
  await page.getByRole('button', { name: 'Playlists' }).click();
  await expect(page.locator('#playlistsView')).toHaveClass(/active-view/);
  await page.getByRole('button', { name: 'Home' }).click();
  await expect(page.locator('#homeView')).toHaveClass(/active-view/);

  await page.locator('#heroImport').click();
  await expect(page.locator('#importDialog')).toHaveAttribute('open', '');
  await page.locator('[data-close="importDialog"]').first().click();
  await expect(page.locator('#importDialog')).not.toHaveAttribute('open', '');

  await page.locator('#settingsButton').click();
  await expect(page.locator('#settingsDialog')).toHaveAttribute('open', '');
  await page.locator('[data-close="settingsDialog"]').first().click();
  await expect(page.locator('#settingsDialog')).not.toHaveAttribute('open', '');

  await page.locator('#toggleNav').click();
  await expect(page.locator('body')).toHaveClass(/nav-collapsed/);
  expect(await page.evaluate(() => localStorage.getItem('listenleaf-nav-collapsed'))).toBe('1');
  await page.locator('#toggleNav').click();
  await expect(page.locator('body')).not.toHaveClass(/nav-collapsed/);

  await page.locator('#focusToggle').click();
  await expect(page.locator('#focusToggle span')).toHaveText('Pause focus sprint');
  await page.locator('#focusToggle').click();
  await expect(page.locator('#focusToggle span')).toHaveText('Resume focus sprint');

  expect(pageErrors).toEqual([]);
});

test('reader controls toggle panels, text presentation, edit and playlist dialogs', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await mockCommonApi(page);
  await page.route('**/api/books/book-1', route => json(route, book));
  await page.goto('/');
  await page.locator('[data-book="book-1"]').first().click();

  await page.locator('#toggleSoundPanel').click();
  await expect(page.locator('body')).toHaveClass(/sound-collapsed/);
  await page.locator('#toggleSoundPanel').click();
  await expect(page.locator('body')).not.toHaveClass(/sound-collapsed/);

  const before = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--reader-size').trim());
  await page.locator('#textPlus').click();
  const afterPlus = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--reader-size').trim());
  expect(afterPlus).not.toBe(before);
  await page.locator('#textMinus').click();

  await page.locator('#focusLine').click();
  await expect(page.locator('#readalong')).toHaveClass(/focus-line-mode/);
  await page.locator('#focusLine').click();
  await expect(page.locator('#readalong')).not.toHaveClass(/focus-line-mode/);

  await page.locator('#editBook').click();
  await expect(page.locator('#editBookDialog')).toHaveAttribute('open', '');
  await expect(page.locator('#editBookTitle')).toHaveValue('Tamil E2E Book');
  await page.locator('[data-close="editBookDialog"]').first().click();

  await page.locator('#addPlaylist').click();
  await expect(page.locator('#playlistDialog')).toHaveAttribute('open', '');
  await expect(page.locator('#playlistBooks input[value="book-1"]')).toBeChecked();
  await page.locator('[data-close="playlistDialog"]').first().click();

  await page.locator('#readerVoiceSettings').click();
  await expect(page.locator('#settingsDialog')).toHaveAttribute('open', '');
  await expect(page.locator('#voiceSettingsSection')).toBeVisible();

  expect(pageErrors).toEqual([]);
});

test('sound and preference buttons update state and persist intended values', async ({ page }) => {
  const preferencePayloads = [];
  await page.route('**/api/dashboard', route => json(route, dashboard));
  await page.route('**/api/preferences', async route => {
    preferencePayloads.push(route.request().postDataJSON());
    await json(route, { ok: true });
  });
  await page.route('**/api/books/book-1', route => json(route, book));
  await page.goto('/');
  await page.locator('[data-book="book-1"]').first().click();

  await page.locator('#advancedSound').evaluate(node => { node.open = true; });
  await page.locator('#largeText').check();
  await expect(page.locator('body')).toHaveClass(/large-text/);
  await page.locator('#reduceMotion').check();
  await expect(page.locator('body')).toHaveClass(/reduce-motion/);

  await page.locator('#speedSelect').selectOption('1.25');
  await expect(page.locator('#speedButton')).toHaveText('1.25×');
  await page.locator('#skipSelect').selectOption('30');
  await expect(page.locator('#rewind')).toHaveText('↶30');
  await expect(page.locator('#forward')).toHaveText('30↷');

  await page.locator('#shuffleButton').click();
  await expect(page.locator('#shuffleButton')).toHaveClass(/active/);
  await page.locator('#repeatButton').click();
  await expect(page.locator('#repeatButton')).toHaveClass(/active/);
  await expect(page.locator('#repeatButton')).toHaveText('↻');
  await page.locator('#repeatButton').click();
  await expect(page.locator('#repeatButton')).toHaveText('↻1');

  await expect.poll(() => preferencePayloads.length).toBeGreaterThanOrEqual(6);
  expect(preferencePayloads).toEqual(expect.arrayContaining([
    { large_text: true },
    { reduce_motion: true },
    { playback_rate: 1.25 },
    { skip_seconds: 30 },
    { shuffle: true },
    { repeat_mode: 'all' },
    { repeat_mode: 'one' },
  ]));
});