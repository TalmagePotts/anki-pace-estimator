# Screenshots for the AnkiWeb listing

AnkiWeb strips every `<img>` attribute except `src`, so a picture is shown at
its natural pixel size. **Resize before uploading** — anything wider than about
900px will overflow the page.

Use `./docs/grab.sh <name>` — it captures straight into `docs/images/` under the
right filename and scales the result down. Drag a box around just the panel:
these pages are public, and a full deck-list shot puts every deck name on them.

## Taking them by hand (macOS)

- **⌘⇧4** then drag — saves a region shot to the Desktop.
- **⌘⇧4** then **space**, then click a window — captures that window with its
  shadow. Hold **⌥** while clicking to drop the shadow, which looks better here.
- Retina screens capture at 2x, so a 900px-wide window becomes an 1800px file.
  `./docs/resize.sh` fixes that.

Use a deck with real cards due, and switch Anki to whichever theme you want the
listing to show. Dark tends to photograph better.

## The five to take

Save each into `docs/images/` with these exact names:

| File | What to capture |
|---|---|
| `home.png` | The deck list with the panel showing, cards due, an ETA and a range. The hero shot — take this one twice and keep the better. |
| `stats.png` | **Tools ▸ Pace Estimator**, scrolled so the by-deck table and its differing speeds are visible. This is the evidence that the add-on does something other tools don't. |
| `settings.png` | The settings dialog on **Speed & accuracy**, showing the estimator and the splits. |
| `reviewer.png` | A card with the out-of-time symbol showing. Set the goal to 2s and let a card run over. |
| `session.png` | The home panel right after finishing a deck, showing the session summary and the "faster than usual" chip. |

## Then

    ./docs/resize.sh          # scales anything over 900px wide
    git add docs/images && git commit -m "Add listing screenshots" && git push

The URLs in `LISTING.md` point at these filenames and start working the moment
they are pushed.
