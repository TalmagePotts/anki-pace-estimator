## Review Pace

Use **Tools ▸ Review Pace… ▸ Settings**, or the ⚙ on the home-screen panel, for a
proper settings dialog with a deck picker. Editing the JSON here works too.

- **decks.ids** — deck ids to track. Empty means the whole collection.
- **speed.mode** — `wall` counts the time between cards as well as the answer
  itself; `answer` counts only question-to-button time.
- **speed.idle_cutoff_s** — a gap longer than this is a break, not study time.
- **speed.count_full_learning** — count every learning step a new card needs,
  measured from your own history, instead of one answer per card.
- **display.components** — ordered list of home-screen blocks with an
  `enabled` flag each.
- **goal** — per-card time goal and the countdown badge shown while reviewing.
