# planet-hunter web

Next.js (App Router, TypeScript): the Planet Finder and its home page. Read `DESIGN.md` before building
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
| `/` | Home |
| `/finder` | Planet candidates from the nightly sweep, with the funnel |
| `/finder/[id]` | One candidate's report: light curves, checks, pixel check, votes |
| `/finder/sensitivity` | What the search can find (injection-recovery) |
| `/credits` | Every picture's credit and licence |

## API client (`lib/api.ts`)

- Mock mode is the default and serves `public/data/finder/*`; mock data must show `<DemoTag />`.
- For the real API (api/README.md), build with `NEXT_PUBLIC_API_MOCK=false` and
  `NEXT_PUBLIC_API_BASE=https://…`. Live responses are mapped onto the same types the components use.
- Votes carry an `X-Voter-Key` header: a random id kept in localStorage (`ph-voter-key`), not an account.
  `submitVote(id, null, [])` withdraws a vote.
