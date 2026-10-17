# Strava Lens web

React 19 / TypeScript frontend. Start the API on port 8000, then run `npm ci` and `npm run dev`. The development server proxies `/api` to the backend; production uses the same-origin reverse proxy in `deploy/`.

`npm run build` performs strict TypeScript checking and creates `dist/`. `npm test` checks bookmark filter immutability, metric registry identifiers and missing-value presentation. `npm run format:check` checks formatting.

The API owns the dashboard catalog, metric definitions, units, coverage and calculations. The browser stores filter selections in the URL, caches requests with TanStack Query and renders ECharts with equivalent data tables. Import status is polled every three seconds. Uploads are accepted on Setup by file selection or drag and drop. The active snapshot changes only after a successful import; the snapshot history control can activate another committed snapshot.

When backend authentication is enabled, enter the access token after the initial authorization error. The token stays in sessionStorage for this browser tab and is sent only to same-origin API requests. Configuration editing is restricted by the backend authorization policy; edits apply to future imports. The frontend loads no external fonts, map tiles or analytics.
