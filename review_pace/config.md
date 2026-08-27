## Review Pace

Use **Tools ▸ Review Pace… ▸ Settings**, or the ⚙ on the home-screen panel, for a
proper settings dialog with a deck picker. Editing the JSON here works too.

- **decks.ids** — deck ids to track. Empty means the whole collection.
- **speed.mode** — `wall` counts the time between cards as well as the answer
  itself; `answer` counts only question-to-button time.
- **speed.estimator** — `mean`, `trimmed` or `median`. What the ETA is built
  from. Only the mean is unbiased for a total.
- **speed.features** — any of `ease`, `interval`. Extra ways to split the speed
  measurement on top of card type. Off by default.
- **speed.min_sample** — widen the window automatically below this many reviews.
- **display.speed_display** — `mean`, `typical` or `both`.
- **display.columns** — 0 picks a column count from the number of tiles so the
  last row stays full.
- **speed.idle_cutoff_s** — a gap longer than this is a break, not study time.
- **speed.count_full_learning** — count every learning step a new card needs,
  measured from your own history, instead of one answer per card.
- **display.components** — ordered list of home-screen blocks with an
  `enabled` flag each.
- **goal.show_timer** — whether a running timer appears on every card.
- **goal.alert_style** — what happens when time is up: `none`, `badge` (turn the
  timer red), `exclamation` (a large symbol over the card) or `both`.
- **goal.alert_position** — `bottom`, `lower-half`, `center`, `upper-half` or
  `top`.
- **goal.timer_phase** — `whole_card`, `question`, `answer` or `separate`.
- **goal.answer_seconds** — the allowance for the answer, used by `separate`.
- **goal.alert_phase** — `always`, `question` or `answer`.
- **debug** — write a log to `review_pace_debug.log` in your add-ons folder.
