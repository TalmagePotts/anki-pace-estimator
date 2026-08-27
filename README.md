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
4. **A total is a sum of averages, not of typical cards.** Card times are
   right-skewed: most are quick and a few are slow, so the median sits well
   below the mean. Multiplying the median by a card count underestimates every
   session, so speeds are means. The median is still shown, labelled "typical",
   and is never multiplied by anything.

## What the design is based on

The choices above were settled by walk-forward backtesting against a real
collection: for each day, speeds were built from the preceding days only and
used to predict that day's total time, with no access to the day being
predicted. Across 60-75 such days:

| Estimator | Bias | Average error |
|---|---|---|
| Mean, per card type, 14-day window | +3.8% | **25.3%** |
| Mean, single figure for all cards | +5.4% | 27.4% |
| Trimmed mean | -17.3% | 31.0% |
| Median | **-43.3%** | 45.4% |

The median underestimates by more than 40%: on that collection the slowest 10%
of cards account for 38% of all time spent, and the median throws that tail
away. Per-card-type means beat one overall mean by about two points, and a
14-day window beats 30 or 90 days, because it tracks your current pace.

Card-level features were tested and **rejected**: adding ease factor, lapse
count, interval or repetition count to the model changed the error by less than
a point, which is noise at this sample size. A variance decomposition explains
why -- of the variation in how long a card takes, which card type it is
explains 0.3%, which *day* it falls on explains 10%, and the remaining 90% is
card-to-card noise that averages out over a session. Your pace swings about
±39% from day to day, and no property of a card can predict that. It is
expressed as the ETA's upper bound instead.

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

Set a target seconds-per-card, globally or per deck on the Decks tab. The timer
and the out-of-time warning are independent, so you can have:

- a running timer that turns red when you go over,
- a large symbol over the lower half of the card and no timer at all, so nothing
  distracts you until you are actually out of time,
- or both.

The warning fires at exactly the time you set — there is no early warning stage.
Everything is drawn by the add-on, so it works on every note type without
editing a single card template. **Preview it here** on the settings tab runs the
whole thing on the current screen with a shortened goal, so you can check a
setting without sitting through a real card.

## Development

    python -m pytest tests

The suite includes `tests/test_reviewer_js.py`, which runs the injected reviewer
script under Node against a stub DOM and a fake clock, so the per-card timer is
checked second by second rather than by eye. Those tests skip if Node is absent.

`review_pace/src/stats.py` holds all the arithmetic and imports nothing from
Anki, so the numbers are testable without launching the app.

Shortcuts are recorded with a purpose-built widget rather than Qt's
`QKeySequenceEdit`: click it, press the combination, and it is taken the moment
you release every key, with an ✕ to clear it. Escape cancels, Backspace clears.

Turn on **Troubleshooting ▸ Write a debug log** in the settings to get
`review_pace_debug.log` in your add-ons folder, or read the in-memory tail with
**Show recent activity…**. Every hook the add-on registers is wrapped so a
failure is logged rather than breaking the screen it is attached to.
