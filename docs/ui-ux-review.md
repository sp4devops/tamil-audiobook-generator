# UI/UX Review — ListenLeaf

## Product read

ListenLeaf already has the right functional ingredients for a local audiobook product: import, generation, progressive playback, read-along, library management, focus aids, sound controls, playlists, and privacy-first local storage. The main design problem is not missing capability; it is competing capability.

The current interface gives many controls similar visual weight, especially in the reader. This makes the product feel closer to an engineering control surface than a focused listening app. The redesign therefore keeps behavior intact and changes the hierarchy around it.

## Primary UX problems found

1. **Weak visual hierarchy.** Home cards, reader actions, generation controls, playback controls, sound controls, and destructive actions all compete for attention.
2. **Reader overload.** The reader presents metadata, generation, transport, follow/edit/playlist/fullscreen controls, read-along controls, equalizer, ambience, and focus options at once.
3. **Book cards read as generic tiles.** Their square covers and dense metadata reduce the audiobook/library feel.
4. **Responsive behavior compresses rather than reprioritizes.** Mobile previously hid useful reader context and retained too many competing controls.
5. **Persistent player is visually heavy.** It occupies substantial vertical space and competes with the reading surface.
6. **Settings and destructive actions lack workflow hierarchy.** They are functional but visually close to the rest of the interface.

## First-pass implementation

The first-pass redesign is intentionally CSS-only so the audiobook engine, API contracts, DOM IDs, progressive generation lifecycle, and automated browser tests remain stable.

### Navigation and shell

- Increased sidebar clarity and reduced visual noise.
- Added a distinct active-navigation treatment rather than relying only on background fill.
- Refined the focus timer and local-only state to read as supporting utilities rather than primary product actions.
- Constrained content width so the desktop layout does not become visually sparse on large screens.

### Home and library

- Shifted book covers toward portrait proportions to better match books/audiobooks.
- Reduced card chrome and improved title/author/metadata hierarchy.
- Made playback actions visually distinct without dominating the card.
- Refined list-row density and hover states.
- Improved the empty-library state so the import action is clearer.

### Reader

- Prioritized the read-along surface.
- Reduced the visual weight of metadata and utility controls.
- Made generation controls read as a workflow within the book context.
- Kept the generation progress, estimated duration, partial playback, and export behavior intact.
- Improved active-cue treatment using a quieter accent marker instead of scale animation.
- Made the sound panel feel like a secondary inspector rather than a third equal-weight column.
- Added sticky desktop side panels while preserving the existing collapse behavior.

### Player

- Reduced persistent player height.
- Tightened control spacing and metadata sizing.
- Preserved transport, seek, sleep, speed, repeat, shuffle, volume, and read-along shortcuts.

### Mobile

- Converted bottom navigation into a floating dock.
- Preserved generation information instead of hiding the entire book-context panel.
- Reflowed reader actions into a compact grid.
- Reduced read-along toolbar density.
- Kept the player reachable without obscuring navigation.

### Dialogs and settings

- Added clearer section separation and workflow grouping.
- Increased distinction for danger-zone content.
- Refined form control contrast and spacing.

## Recommended next design pass

The current HTML information architecture still exposes features that are probably unnecessary for the core Stage 2 audiobook workflow. A second pass should make product-level decisions rather than only styling decisions:

- Consider moving **Following** and **Playlists** out of primary navigation until the core create → generate → listen workflow is mature.
- Move **Equalizer** and **Ambient sound** under an advanced playback disclosure or settings sheet.
- Replace emoji/symbol icons with a consistent local SVG icon set.
- Add a true **generation queue / recent jobs** surface if users will process long books.
- Add explicit **voice readiness** status near the generate action instead of burying it in Settings.
- Add import progress/error handling and filename/file-size feedback in the import dialog.
- Add keyboard shortcuts for play/pause, skip, speed, and read-along focus.
- Add accessible status semantics for generation failures and success states.
- Consider adding audiobook chapter/navigation structure when the backend exposes it.

## Validation constraints

This first pass intentionally avoids changing JavaScript or backend behavior. Existing selectors, DOM IDs, API calls, progressive generation logic, audio controls, and E2E expectations are preserved.
