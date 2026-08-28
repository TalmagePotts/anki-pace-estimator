Text to paste into the AnkiWeb upload form.

## Title

Pace Estimator — accurate study time estimates

## Description

Measures how fast you actually answer cards and turns it into an honest
estimate of how long today's workload will take.

**Why the estimate differs from other add-ons**

Most speed add-ons multiply "cards due" by one average seconds-per-card. Four
things make that wrong, and Pace Estimator fixes all four:

- **Decks are not interchangeable.** On the collection this was built against,
  decks ranged from 8 to 29 seconds a card. A single collection-wide rate gave
  the same answer for both and was wrong by a factor of three in opposite
  directions. Every deck is priced from its own history, falling back to its
  parent deck when it has too little.
- **A new card is not one answer.** With learning steps it is two or three.
  Your real answers-per-new-card is measured from your history.
- **Card types differ.** Learning, young, mature and relearning cards are
  measured separately and weighted by what you actually have due.
- **A total is a sum of averages, not of typical cards.** Card times are
  right-skewed, so using a median underestimates every session — by 43% on the
  test collection.

**Two speeds**

- *Answer time* — question shown until you press a button.
- *Wall-clock time* — the same, plus the gap before the next card appears.

Wall-clock is the default because it is what actually happens. Breaks longer
than a cutoff are excluded, so walking away mid-session does not wreck your
averages.

**What it shows**

Time remaining as a range with the clock time you finish at; due, new and
learning counts; both speeds, optionally split by card type, ease, interval or
time of day; new cards learned today, this week and this month; and a summary of
the session you just finished.

Surfaces: the deck list, a deck's study screen, the top toolbar, a heads-up
display while reviewing, and a detailed analysis window under Tools. Every
block can be turned off and reordered.

**Per-card time goal**

Off unless you want it. Switched on, it stays out of the way: no timer on
screen, and a large symbol at the bottom once a card has run over its time, so
you know to stop struggling and turn it over. It can sit on the answer side
instead if you would rather not be nudged mid-recall.

Set a target seconds-per-card, globally or per deck. If you would rather watch
the clock, a countdown timer can be switched on, in any corner, counting up or
down. The timer and the warning are independent, and the question and answer
sides can have separate clocks. It is all drawn by the add-on, so it works on
every note type without editing a single card template.

**Calibration**

Backtested against real review history: over 55 days, the actual time came in
under the headline estimate 50% of the time and under the top of the range 78%
of the time — the range means what it says.

Requires Anki 23.10 or later. Source and full methodology:
<https://github.com/YOURNAME/anki-review-pace>

## Support page

Point this at your GitHub issues URL.
