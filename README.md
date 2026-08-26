# Review Pace

An Anki add-on that measures how fast you actually answer cards and turns that
into an honest estimate of how long today's workload will take.

## Why the estimate differs from other add-ons

Most speed add-ons multiply "cards due" by one average seconds-per-card. Three
things make that wrong, and Review Pace fixes all three:

1. **A new card is not one answer.** With learning steps it is two, three or
   more. Review Pace measures your real answers-per-new-card from your review
   history rather than assuming.
2. **Card types differ enormously.** A mature review might take 5 seconds and a
   brand-new card 20. Speeds are measured separately for learning, young,
   mature and relearning cards, then weighted by what you actually have due.
3. **You will fail some reviews.** Cards graded Again come back within the same
   session. Your real Again-rate and relearning cost are folded in.

Cards already part-way through learning are counted by the answers they still
owe (`cards.left`), not as one card each, and every count comes from Anki's own
scheduler, so per-deck limits are respected.

## Two speeds

- **Answer speed** — question shown until you press a button (`revlog.time`).
- **Wall-clock speed** — the same, *plus* the gap before the next card appears:
  rendering, your pause before flipping, the moment between cards.

Wall-clock is the default because it is what actually happens. Gaps longer than
the idle cutoff (60s by default) count as breaks and are excluded, so walking
away mid-session doesn't wreck your averages. Gaps are measured across the whole
review stream, not per deck, so interleaving decks stays accurate.

## What it shows

- Time remaining, as a range, with the clock time you finish at
- Due / new / learning counts for the decks you pick
- Answer and wall-clock speed, optionally broken down by card type
- New cards learned today, this week, this month
- Answers and time spent today

Every block can be turned off and reordered. Surfaces: the deck list, a deck's
study screen, the top toolbar, a heads-up display while reviewing, and a
detailed window at **Tools ▸ Review Pace…**.

## Per-card time goal

Set a target seconds-per-card (globally, or per deck on the Decks tab) and a
badge counts down on every card, turning amber as you approach the limit and red
when you go over. It is drawn by the add-on, so it works on every note type
without editing a single card template.

## Development

    python -m pytest tests

`review_pace/src/stats.py` holds all the arithmetic and imports nothing from
Anki, so the numbers are testable without launching the app.
