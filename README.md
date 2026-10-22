# Browser Disc Clock

Open [index.html](index.html) directly in a modern browser. No installation,
build step, Python runtime, or server is required. This folder is independent of
the desktop application.

The Canvas clock uses the device's local time and reproduces the seven outer
rings, seasonal month colors, ten-second chasing light, and sixty central
domino rings. Animation targets 60 FPS and pauses in hidden tabs.

Use the fullscreen icon or F11 to toggle fullscreen; Escape exits fullscreen
(browsers do not allow the desktop application's Escape-to-quit behavior).

Sunrise, sunset, and solar noon are optional. The page contacts ipapi.co for an
approximate IP location, then sunrise-sunset.org for sun data. Network failures,
API limits, or browser restrictions do not stop the clock. Failed requests retry
after ten minutes, and sun data refreshes when the local date changes.

Choose coordinates through Location, or append a query such as
`?lat=37.3541&lon=-121.9552` to the page URL. Manual settings are saved locally
where browser storage is available. Choose a location in the device's time zone:
coordinates change sun data, not the clock's time zone. Polar-day/night shading
is omitted when the API returns no sunrise or sunset.

## Publishing

The deployment branch is `gh-pages`, with this folder's contents at its root.
In the repository's Settings > Pages, select "Deploy from a branch", then
`gh-pages` and `/ (root)` as the source.

The site address is https://hertzvador.github.io/milleniumClock/ once GitHub
Pages is enabled and the deployment has finished.

To publish later updates, commit changes to `GitHubPages` on `main`, then run
these commands from the repository root:

```sh
git push origin main
git subtree push --prefix=GitHubPages origin gh-pages
```