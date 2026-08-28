# Publishing Review Pace to AnkiWeb

## 1. Add the licence text (once)

The add-on imports Anki's own code, which is AGPL-3.0, so releasing under the
same licence is the safe choice. Run this once, in the project folder:

    curl -o LICENSE https://www.gnu.org/licenses/agpl-3.0.txt

## 2. Build the package

    ./build.sh

This runs the tests, deletes `__pycache__` and `meta.json`, and writes
`dist/review_pace.ankiaddon`. It refuses to build if the archive would contain
anything AnkiWeb rejects.

## 3. Test the built file before uploading

Do not upload a package you have not installed from. In Anki:

1. **Tools → Add-ons → View Files**, and delete the `review_pace` symlink so
   the development copy cannot mask the real install.
2. Quit Anki, reopen it.
3. **Tools → Add-ons → Install from file…**, choose
   `dist/review_pace.ankiaddon`.
4. Restart and confirm the panel, the settings dialog and the reviewer badge
   all work.

## 4. Upload

1. Sign in at <https://ankiweb.net>.
2. Go to <https://ankiweb.net/shared/addons/> and press **Upload**.
3. Attach `dist/review_pace.ankiaddon`.
4. Fill in the title and description (see `LISTING.md`), and tick the Anki
   versions you have actually tested.
5. Submit. AnkiWeb assigns a numeric ID and a page at
   `https://ankiweb.net/shared/info/<id>`.

## 5. Releasing an update

Bump `human_version` in `review_pace/manifest.json`, run `./build.sh`, then use
the **Update** button on your add-on's AnkiWeb page. Users get it through
**Tools → Add-ons → Check for Updates**.

## Restoring the development setup

After testing the packaged build, remove the AnkiWeb-installed copy and put the
symlink back so edits are live again:

    ln -sfn "$PWD/review_pace" ~/Library/Application\ Support/Anki2/addons21/review_pace
