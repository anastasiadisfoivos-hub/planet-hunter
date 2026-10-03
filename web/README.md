# planet-hunter web

Next.js (App Router, TypeScript): the Planet Finder and its live monitor. Read `DESIGN.md` before building
UI. v2 removed the sky events, the 3D sky map and the Lab; [../docs/REMOVED.md](../docs/REMOVED.md) lists
what went.

```bash
npm install
npm run dev        # http://localhost:3000
npm test           # node --test
npm run typecheck && npm run lint && npm run build
```

## Routes

| Route | What it is |
|---|---|
| `/` | The monitor: the star being searched now, or a replay of the last run |
| `/candidates` | Planet candidates from the search, with the funnel |
| `/candidates/[id]` | One candidate's dossier: light curves, checks, pixel check, vetting, votes |
| `/log` | Every star searched, and where on the sky |
| `/methods` | How the search works (text: `components/monitor/methodsText.ts`, from docs/plan/METHODS.md) |
| `/sensitivity` | What the search can find (injection-recovery) |
| `/finder/*` | Redirects to the routes above |
| `/credits` | Every picture's credit and licence |

## API client (`lib/api.ts`)

- `NEXT_PUBLIC_API_BASE=https://…` (the API, api/README.md) switches the site to the real API. Live
  responses are mapped onto the same types the components use, and the site shows only what the API
  answers: an empty candidate list says so.
- Unset, the site runs in mock mode on `public/data/monitor/*` (real recorded data; the candidates there are
  stand-ins, real TOIs, and every page says so). Stand-ins never appear with the real API.
- Votes carry an `X-Voter-Key` header: a random id kept in localStorage (`ph-voter-key`), not an account.
  `submitVote(id, null, [])` withdraws a vote.
