---
title: "Comet API incident: June 2026 outage"
type: project
---

# Comet API incident: June 2026 outage

Comet had an outage in June 2026 caused by an expired TLS certificate on the
proxy's public endpoint that nobody had put on a renewal calendar. Every
request to Comet started failing TLS handshakes the moment the certificate's
expiry timestamp passed. The fix was a manual certificate renewal followed by
adding automatic certificate renewal so an expired TLS certificate can never
cause a Comet outage again.
