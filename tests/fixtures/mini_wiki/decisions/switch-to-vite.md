---
title: "Decision: switch frontend build tool from webpack to vite"
type: decision
---

# Decision: switch frontend build tool from webpack to vite

We switched the frontend build tool from webpack to vite. Webpack's cold start
and hot-module-reload times had grown painful as the frontend codebase grew.
Vite's native ES-module dev server made hot reload nearly instant, which was
the whole point of the switch. The production bundle step still uses Rollup
under the hood, but the dev-loop speedup is the win developers actually feel
every day.
