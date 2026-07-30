---
title: "Comet API overview"
type: project
---

# Comet API overview

Comet is a rate-limited weather-data proxy service written in Go. It sits in
front of an upstream weather provider, caches responses briefly, and enforces
a per-client rate limit so a single noisy caller can't exhaust the upstream
provider's quota for everyone else. Comet exposes a small REST surface: current
conditions, a short forecast, and historical daily summaries.
