# AnkiWeb listing

Everything here is meant to be pasted into the upload form at
<https://ankiweb.net/shared/addons/>.

AnkiWeb allows basic HTML but **strips every attribute except `src` on images**,
so pictures appear at their natural size — resize them first (`docs/resize.sh`).
The image URLs below start working once `docs/images/` is pushed to GitHub.

---

## Title

    Pace Estimator — honest study time estimates

## Description (paste as-is)

```html
<p>Measures how fast you actually answer cards and turns that into an honest
estimate of how long today's workload will take.</p>

<img src="https://raw.githubusercontent.com/TalmagePotts/anki-pace-estimator/main/docs/images/home.png">

<h3>Why the estimate differs from other add-ons</h3>

<p>Most speed add-ons multiply "cards due" by one average seconds-per-card.
Four things make that wrong, and all four are fixed here.</p>

<ul>
<li><b>Decks are not interchangeable.</b> On the collection this was built
against, decks ranged from 8 to 29 seconds a card. One collection-wide rate
gave the same answer for both and was wrong by a factor of three in opposite
directions. Every deck is priced from its own history, falling back to its
parent deck when it has too little.</li>
<li><b>A new card is not one answer.</b> With learning steps it is two or
three. Your real answers-per-new-card is measured from your own history rather
than assumed.</li>
<li><b>Card types differ.</b> Learning, young, mature and relearning cards are
measured separately and weighted by what you actually have due.</li>
<li><b>A total is a sum of averages, not of typical cards.</b> Card times are
right-skewed, so multiplying a median by a card count underestimates every
session — by 43% on the test collection, where the slowest tenth of cards used
38% of the time.</li>
</ul>

<img src="https://raw.githubusercontent.com/TalmagePotts/anki-pace-estimator/main/docs/images/stats.png">

<h3>Two speeds</h3>

<p><b>Answer time</b> is the question appearing until you press a button.
<b>Wall-clock time</b> is the same plus the gap before the next card appears —
rendering, hesitation, the moment between cards. Wall-clock is the default
because it is what actually happens. Breaks longer than a cutoff are excluded,
so walking away mid-session does not wreck your averages, and gaps are measured
across your whole review stream so interleaving decks stays accurate.</p>

<h3>What it shows</h3>

<p>Time remaining as a range with the clock time you finish at; due, new and
learning counts; both speeds, optionally split by card type, ease factor,
interval or time of day; new cards learned today, this week and this month; and
a summary of the session you just finished.</p>

<p>It can appear on the deck list, on a deck's study screen, in the top toolbar,
as a heads-up display while reviewing, and in a detailed analysis window under
Tools. Every block can be turned off and reordered.</p>

<img src="https://raw.githubusercontent.com/TalmagePotts/anki-pace-estimator/main/docs/images/session.png">

<h3>Per-card time goal</h3>

<p>Off unless you want it. Switched on, it stays out of the way: no timer on
screen, and a large symbol at the bottom once a card has run over its time,
while the question is still up — the point at which the useful response is to
stop struggling and turn the card over. Move it to the answer side, or switch
on a countdown timer, if you prefer.</p>

<p>Set a target seconds-per-card globally or per deck. It is all drawn by the
add-on, so it works on every card in every note type without editing a single
template.</p>

<img src="https://raw.githubusercontent.com/TalmagePotts/anki-pace-estimator/main/docs/images/reviewer.png">

<h3>Is it accurate?</h3>

<p>Every choice above was settled by backtesting against real review history:
speeds built from earlier days only, then used to predict a later day with no
access to it. Over 55 such days the actual time came in under the headline
estimate 50% of the time and under the top of the range 78% of the time, so the
range means what it says.</p>

<p>The remaining error is day-to-day variation in your own pace, which swings
about 40% and which nothing about a card can predict — so it is shown as a
range rather than pretended away. The full method, including the ideas that
were tested and rejected, is in the README.</p>

<p>Requires Anki 23.10 or later. Source, methodology and issue tracker:
<a href="https://github.com/TalmagePotts/anki-pace-estimator">github.com/TalmagePotts/anki-pace-estimator</a></p>
```

## Support page

    https://github.com/TalmagePotts/anki-pace-estimator/issues

## Supported versions

Tick only what you have actually run it on. It is developed and tested against
Anki 26.8; `min_point_version` in the manifest is set to 23.10.
