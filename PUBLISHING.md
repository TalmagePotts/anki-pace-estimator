# Publishing Pace Estimator to AnkiWeb

## 1. Add the licence text (once)

The add-on imports Anki's own code, which is AGPL-3.0, so releasing under the
same licence is the safe choice. Run this once, in the project folder:

    curl -o LICENSE https://www.gnu.org/licenses/agpl-3.0.txt

## 2. Build the package

    ./build.sh

This runs the tests, deletes `__pycache__` and `meta.json`, and writes
`dist/pace_estimator.ankiaddon`. It refuses to build if the archive would contain
anything AnkiWeb rejects.

## 3. Test the built file before uploading

Do not upload a package you have not installed from. In Anki:

1. **Tools → Add-ons → View Files**, and delete the `pace_estimator` symlink so
   the development copy cannot mask the real install.
2. Quit Anki, reopen it.
3. **Tools → Add-ons → Install from file…**, choose
   `dist/pace_estimator.ankiaddon`.
4. Restart and confirm the panel, the settings dialog and the reviewer badge
   all work.

## 4. Upload

1. Sign in at <https://ankiweb.net>.
2. Go to <https://ankiweb.net/shared/addons/> and press **Upload**.
3. Attach `dist/pace_estimator.ankiaddon`.
4. Fill in the title and description (see `LISTING.md`), and tick the Anki
   versions you have actually tested.
5. Submit. AnkiWeb assigns a numeric ID and a page at
   `https://ankiweb.net/shared/info/<id>`.

## The add-on's identity

    AnkiWeb code : 1873683060
    AnkiWeb page : https://ankiweb.net/shared/info/1873683060

## 5. Releasing an update

Bump `human_version` in `pace_estimator/manifest.json`, run `./build.sh`, then use
the **Update** button on your add-on's AnkiWeb page. Users get it through
**Tools → Add-ons → Check for Updates**.

## Restoring the development setup

After testing the packaged build, remove the AnkiWeb-installed copy and put the
symlink back so edits are live again:

    ln -sfn "$PWD/pace_estimator" ~/Library/Application\ Support/Anki2/addons21/pace_estimator
