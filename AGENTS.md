# AGENTS.md

## Cursor Cloud specific instructions

This is a minimal static PWA (Progressive Web App) called **LS Audit** — a wrapper for a Lightspeed POS reconciliation audit dashboard. There is no build system, package manager, or dependencies to install.

### Project structure

- `index.html` — PWA shell that loads the audit dashboard via an iframe from Google Apps Script
- `sw.js` — Service worker for offline caching
- `manifest.json` — PWA manifest (app name, icons, display mode)
- `icon-192.png`, `icon-512.png` — App icons

### Running the app

Serve static files with any HTTP server:

```
python3 -m http.server 8080
```

Then open `http://localhost:8080/` in Chrome.

### Key caveats

- The actual business logic is hosted externally on Google Apps Script (loaded via iframe). The app requires network access to `script.google.com` to display the audit dashboard.
- Service worker registration requires the page to be served over HTTP(S), not from `file://`.
- There are no lint checks, automated tests, or build steps in this project — it is purely static HTML/JS/JSON.
