# web/ — React console (served by FastAPI at `/app`)

Build-time only: the Python runtime never needs node. Build output is
committed to `companion/static/app/` and served additively next to the
legacy console (`/`), which stays untouched (ADR-015).

```bash
cd web
npm install        # once
npm run build      # type-checks, then bundles into ../companion/static/app
npm run dev        # optional: Vite dev server on :5173, /api proxied to :8000
```

After changing anything under `src/`, run `npm run build` before merging so
the committed bundle matches the source.

Design system: see `docs/plans/console_ui_plan.md` and ADR-015 ("Test
Report" direction — tokens live in `src/styles.css`).
