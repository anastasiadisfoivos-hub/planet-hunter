# planet-hunter web

Next.js (App Router, TypeScript). Read `DESIGN.md` before building UI.

```bash
npm install
npm run dev        # http://localhost:3000
npm run build
```

## Shared foundation (owned by the SKYMAP session: request changes, don't edit)

| Path | What it is |
|---|---|
| `DESIGN.md` | Design system: colours, type, shape, motion, words, layout |
| `app/tokens.css` | Every design token as a CSS custom property |
| `app/globals.css`, `app/layout.tsx` | Base styles; Geist and Geist Mono wired in |
| `components/ui/` | `Button`, `Panel`, `Tag` / `DemoTag`, `Segmented`, `DataGrid`, `EmptyState` |
| `lib/contract.ts` | Shared contract types (identical across all five sessions) |
| `lib/api.ts` | Typed TRAPS API client. Mock mode is on by default |

## API client

```ts
import { api, waitForJob } from "@/lib/api";

const watch = await api.createTrap({ sphere: { ra_deg: 83.8, dec_deg: -5.4, radius_deg: 1 } });
const { job_id } = await api.hunt({ trap_id: watch.id }); // "Analyze" in the UI
const job = await waitForJob(job_id);
const detections = await api.listDiscoveries({ trap_id: watch.id });
```

- Mock mode is the default; mock data must show `<DemoTag />`.
- For a real server, build with `NEXT_PUBLIC_API_MOCK=false` and `NEXT_PUBLIC_API_BASE=https://…`.
- Every request carries an `X-Player-Id` header: a random UUID from localStorage, not an account.
