# sf-install — Learnings

Per ADR-011, every shipped skill MAY carry a `learnings.md` file as a long-running feedback log. This file starts empty and accretes notes from real-world use.

Format: dated bullet entries. Newest at top.

---

_No learnings yet — skill is freshly authored. As friends run `/ren:install` and surface surprises, capture them here. Common categories worth watching:_

- _Stage 1 probes that produce false negatives (e.g. node version output formats we didn't anticipate)_
- _Stage 2 plugin install failures + their root causes (registry typos, marketplace changes, license-prompt edge cases)_
- _Stage 3 conditional-plugin prompts that confuse (friends unsure whether they'll build UIs; Frontend Design install-on-demand copy)_
- _Stage 5 additive-diff prompt fatigue (friends declining every diff because they don't trust them — signal that the prompt copy needs work)_
- _Resume-protocol corner cases (concurrent /ren:install runs racing on the checkpoint file)_
- _Friend-facing copy that confused users (suggested next-action prompts, error remediation messages)_
