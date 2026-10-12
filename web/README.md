# web

Public and government dashboards: **Next.js (App Router) + TypeScript**, **MapLibre GL**
with free OpenFreeMap tiles, **Recharts**.

| Page | What |
|---|---|
| `/` | Public dashboard: headline figures, map, new-vs-resolved trend, issues by type, area leaderboard with drill-down, road-authority table, most urgent issues |
| `/tickets/[ref]` | Public ticket page: sanitized photos, status, deadline, public history |
| `/gov/login` | Official sign-in (password + optional 2FA code) |
| `/gov` | Government dashboard, scoped by the API to the official's area: work queue, map, drill-down, trend, backlog ageing, CSV export |
| `/gov/tickets/[ref]` | Ticket actions: status, assignment, notes, repair-photo upload; confirmation counts |

## Run

```bash
npm install
npm run dev            # http://localhost:3000, expects the API on http://localhost:8000
```

`NEXT_PUBLIC_API_URL` changes the API address; `NEXT_PUBLIC_MAP_STYLE` the base map
(any MapLibre style URL). Without internet the map falls back to a plain background but
still shows the tickets.

## Check

```bash
npm run typecheck
npm run build
# End-to-end (needs API with seed + demo data, and `npm start` running):
CHROMIUM_PATH=/path/to/chrome npm run test:e2e   # or `npx playwright install chromium` once
```

## Design notes

- Colours are tokens in `app/globals.css`, with light and dark values. The two chart
  series colours were checked with a colour-blindness/contrast validator in both modes.
- Ticket status uses reserved status colours, always paired with an icon and a label.
- Charts: one y-axis, thin marks, hairline grid, legends and tooltips; every chart has
  a table nearby carrying the same numbers.
- English, Hindi and Bengali: every label goes through `t()` from `useI18n()`
  (`lib/locale.tsx`); strings are in `lib/messages/{en,hi,bn}.ts`. The language comes
  from the `rw_lang` cookie (set by the header menu) or the browser's Accept-Language,
  and is read on the server, so pages render in the right language from the start.
  `npm test` checks every translation keeps English's placeholders.
- The government token is kept in the browser's localStorage; signing out clears it.
