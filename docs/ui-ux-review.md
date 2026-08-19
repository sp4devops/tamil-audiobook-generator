# UI/UX Review — ListenLeaf

## Product read

ListenLeaf already has the right functional ingredients for a local audiobook product: import, generation, progressive playback, read-along, library management, focus aids, sound controls, playlists, and privacy-first local storage. The main design problem was not missing capability; it was competing capability.

The previous interface gave many controls similar visual weight, especially in the reader. This made the product feel closer to an engineering control surface than a focused audiobook app. The redesign keeps the synthesis engine and API contracts intact while changing the hierarchy around them.

## Primary UX problems found

1. **Weak visual hierarchy.** Home cards, reader actions, generation controls, playback controls, sound controls, and destructive actions competed for attention.
2. **Reader overload.** Metadata, generation, follow/edit/playlist/fullscreen, read-along controls, equalizer, ambience, and focus options appeared at once.
3. **Book cards read as generic tiles.** Square covers and dense metadata reduced the audiobook/library feel.
4. **Responsive behavior compressed rather than reprioritized.** Mobile hid useful reader context and retained too many competing actions.
5. **Persistent player was visually heavy.** It occupied substantial vertical space and competed with the reading surface.
6. **Voice readiness was disconnected from generation.** A required precondition was buried in Settings instead of appearing next to the Generate action.
7. **Generation state was too local.** Users could not understand from Home whether the single local generation worker was idle or active.
8. **Import failures lacked an in-context recovery path.** Async errors could escape to the console instead of remaining inside the import workflow.

## Implemented design direction

### Navigation and shell

- Home and Library are treated as the primary destinations.
- Following and Playlists remain available but are visually demoted into an organization group.
- Replaced several ad-hoc navigation/action symbols with a consistent inline SVG icon set that requires no external assets.
- Refined the focus timer and local-only status to read as supporting utilities.

### Home and generation center

- Added a compact **Voice** status card showing whether the required original reference is configured locally.
- Added a truthful **Generation** status card showing idle/active state, stage, percentage, active title, and chunk progress.
- The surface reflects the actual backend model: one active local generation worker, not a fabricated queue.
- Voice setup can be opened directly from Home.

### Home and library content

- Shifted book covers toward portrait proportions to better match books/audiobooks.
- Reduced card chrome and improved title/author/metadata hierarchy.
- Made playback actions visually distinct without dominating each card.
- Refined list-row density and empty-library messaging.

### Reader

- Read along remains the dominant workspace.
- Voice readiness now appears immediately beside audiobook generation.
- Generate is gated when the original source voice is missing.
- Generate is also gated when a different book already owns the single generation worker.
- Generation progress, estimated duration, progressive playback, and export behavior remain intact.
- Destructive and maintenance actions are moved under **Book options** instead of occupying permanent visual space.
- Active read-along cues use a quieter accent marker rather than scale-heavy motion.

### Sound controls

- Ordinary playback speed and skip settings remain immediately available.
- Equalizer, ambient sound, and focus aids are moved under **Advanced audio**.
- Existing audio behavior is preserved; only information hierarchy changed.

### Player

- Reduced persistent-player visual weight and tightened spacing.
- Preserved transport, seek, sleep, speed, repeat, shuffle, volume, and read-along shortcuts.

### Import and error UX

- Rebuilt the import dialog around a clear local file dropzone.
- Selected filename and size are shown immediately.
- The title defaults from the selected filename when blank.
- Import now has explicit working, error, retry, and success feedback.
- Failed imports remain in the dialog so the user can correct or retry instead of losing context.
- Added a lightweight app-level notice surface for actionable asynchronous errors and successful imports.

### Mobile

- Navigation remains bottom-oriented while controls are reprioritized for narrow screens.
- Generation context remains visible instead of disappearing with the book card.
- Reader actions collapse to the highest-value controls first.
- Advanced/destructive controls are reduced or hidden where they would overwhelm the reading surface.

## Implementation strategy

The first visual pass used CSS-only overrides. The structural pass adds `product-ui.js` and `product-ui.css` as a progressive enhancement layer after the existing `app.js` and `progressive.js` controllers.

This intentionally avoids rewriting working synthesis/playback logic. The existing application remains authoritative for:

- API access and library refresh
- audio transport and persistence
- equalizer and ambience behavior
- progressive generation and partial playback
- read-along cue synchronization
- local settings and destructive operations

The product layer is responsible only for product-state presentation, truthful generation gating, import UX, async notices, and the final information hierarchy.

## Validation

The browser regression suite now checks:

- Home voice readiness state
- Home generation-idle state
- reader voice readiness
- advanced audio being collapsed by default
- existing progressive/export lifecycle compatibility
- import filename-to-title behavior
- in-context import failure and retry readiness

CI also syntax-checks `product-ui.js` in addition to the pre-existing frontend scripts.

## Remaining product-level opportunities

The highest-value future improvements require new backend capability or larger product decisions rather than more styling:

- real chapter extraction/navigation for long books
- a true generation queue only if the engine is changed to support queued jobs
- keyboard shortcuts for play/pause, skip, speed, and read-along focus
- optional recent generation history using the backend job history
- richer cover metadata or user-provided cover images
- accessibility pass with screen-reader workflow testing, not only semantic/status markup
- visual regression screenshots across desktop/mobile and all themes
