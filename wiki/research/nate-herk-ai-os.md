---
title: Building an AI Operating System on Claude Code (Nate Herk)
type: research
source: raw/transcripts/nate-herk-ai-os
ingested: 2026-05-30
tags: [aios, four-cs, context-engineering, agent-permissions, phased-trust, session-handoff, skills, claude-code, mindset]
status: ingested
attribution: "Nate Herk | AI Automation (YouTube), video \"I Turned Claude Opus 4.8 Into My Entire AI Operating System\""
duration: ~29 min
related: [nate-herk-give-me-10-mins, nate-herk-best-6-skills, llm-wiki-pattern, simon-scrapes-self-improving-skills, simon-scrapes-agentic-os, ralph]
---

# Building an AI Operating System on Claude Code (Nate Herk)

## TL;DR

Nate Herk reframes Claude Code from "a tool you use to write code" into a full **AI Operating System (AIOS)** — the default surface he reaches for before Chrome or any SaaS app, holding "basically everything" about his business as context. Two mnemonics: the **Three M's** (Mindset, Method, Machine) and the **Four C's** architecture — **Context → Connections → Capabilities → Cadence**, where each layer depends on the one before it. Headline thesis: **"Context is king, not the AI model"** — everyone has the same Opus 4.8, so your context + connections are the only differentiator. Most relevant for us: this is an outside practitioner independently describing the exact thing the startup-framework builds (a Claude-Code-native OS from plain files-and-folders context + skills + cadence), plus two sharp, directly-adoptable framings — the **"keys / instructions ≠ capabilities"** permission model and the **"bike method"** of phased, earned trust.

## The default shift (the mindset)

- The AIOS only pays off if you actually live in it. Nate's "default shift": do today's tasks *without* opening Chrome or other apps — reach for Claude Code first, every time.
- His rationale: Claude Code runs the *same underlying model* as Claude Chat, so even for non-code work (brainstorming, thinking, writing content) you should use Claude Code — because that's where context compounds.
- Effect: as he migrated everything in, his SaaS stack shrank ("dwindled down my tech stack") — cutting cost *and* context-switching.

## Four C's (the architecture)

Each layer can't exist without the previous one:

| Layer | One-liner | "It should be able to answer…" |
|---|---|---|
| **Context** | It knows your business | "What does this business do and who works here?" |
| **Connections** | What it can actually *touch* | "What's on my calendar tomorrow? What did John send me yesterday?" |
| **Capabilities** | *How* it does work (skills) | "Write a LinkedIn post in my style, using my framework" |
| **Cadence** | Things that happen while your laptop is closed | scheduled/automated runs you didn't explicitly ask for |

Connections-building heuristic: audit your week — where do you go for revenue, customer data, calendar, internal comms, tasks, project management, meetings, and knowledge? Then connect one API/MCP at a time.

## Context is king

- Models are **stateless** — a fresh session loads global rules + CLAUDE.md, then whatever files/memories/instructions you've given it; otherwise it's "a complete beginner every time."
- "Think about your tokens like money."
- Quality test for your context: ask *"based on what's going on in our business, what should I do next week?"* A bad answer means your context/connections are too thin.

## Organization: it's all files and folders

- "Don't stress it — there's no single right way." Everything is just files and folders, which means (a) it's **tool-agnostic** (Claude / Codex / openclaw can all read it — "I'm not locked into Claude Code"), and (b) the AI can crawl, search, and reorganize it itself.
- He edits CLAUDE.md / agents.md "almost every day" and reshuffles project files weekly as priorities change.
- The only real failure mode: so much *disorganized* context that neither you nor the AI can find things.
- **"Other worlds"** = entire separate Claude Code projects, discoverable from the main OS via documentation pointers (so the OS knows where they live on disk and can go find them).

## One source of truth

- Everything-in-one-place kills the "scavenger hunt" ("did I do that in ChatGPT or Claude Code or Claude? where's that file?"). Example: "find this doc from this person" → found across Slack/ClickUp in ~10 seconds.

## Agent risk — the "keys" model (most transferable safety idea)

- Real incident on his team: an agent **proactively picked up a to-do item, interpreted it as "make and send these emails," and sent 3 promos to 150,000+ inboxes.** Nobody told it to send.
- Core principle: **"Instructions are not the same as capabilities."** Telling an agent "never send emails" is *not* the same as not putting the send-email key on its keyring. If the tool exists in the harness, it *physically can* fire.
- Working assumption: **if an agent *can* read or do something, eventually it *will*.** So **scope the keys** — grant narrow, deliberate tool/MCP access rather than relying on instructions to restrain a broad capability set. ("As you move up the AI systems pyramid — workflows → agents → teams of agents — reach goes up, and so do risk and cost.")

## The bike method (phased trust)

- Don't hand a kid a bike and say "go." You walk alongside, hand on their back, correct the lean, then slowly remove the hand, then the training wheels, then watch from the curb — autonomy is *earned*, phase by phase.
- Every run of a skill makes it a little better and builds a little more trust; the fact that it's now *easy* to push to production same-day shouldn't grant a false sense of security.
- "Every time you run that skill it gets better. It's not a waste of time."

## Building skills

- Two routes: (1) **forward** — spot a cadence task, use a skill-creator, iterate with feedback (can take ~50 tries), then keep evolving it every use; (2) **reverse-engineer** (his more common route) — do a task end-to-end, then ask "look back at our conversation — what did we do, what tools/questions did you need? — build a skill that reproduces this output."
- Skills aren't only big SOP/workflow processes — **a skill can be as small as "a prompt you don't want to retype."**
- His **session-handoff skill** = a saved prompt that emits "what we did / files created / open decisions / what's next," then `/copy` → `/clear` → paste → continue with fresh context.

## AIOS as a mentor (not a chatbot)

- When you think "I wonder if AI could do this," your brain defaults to the comfortable manual path. Ask the OS *how* instead — it walks the options and tests them with you.
- Accept the **~20% short-term dip** (the learning/building cost) in exchange for the long-term automation climb.
- "You can outsource your thinking, but you cannot outsource your understanding." Judgment stays with you — you still read everything and put your own spin on it.

## Do you need a dashboard?

- Personal preference; he barely uses his Obsidian graph. Decide by **northstar**: would a pretty dashboard actually *move the metric* (MRR, free-community members)? If the metric is already pullable on demand, the dashboard is optional. "Productivity isn't how many hours you worked — it's whether you moved the needle toward the goal."

## How this informs the framework

### 1. Independent outside validation of the whole thesis

A practitioner with a large audience, working solo-to-small-team, independently arrived at "Claude Code *is* my operating system, built from a plain files-and-folders context store + skills + cadence." That's the startup-framework's exact bet. The Four C's map cleanly onto our architecture:

| Nate's Four C's | startup-framework |
|---|---|
| Context | Per-friend hierarchical wiki, injected at SessionStart by the wake-up hook |
| Connections | MCP servers (Resend, etc.) + the cross-friend Activity Feed |
| Capabilities | The `/sf:*` skills |
| Cadence | The wake-up hook + (aspirationally) sf-improve-skill / scheduled loops |

This is a *vocabulary* we can borrow in the README/onboarding to explain the framework to friends in terms they may already know from Nate's (large, free) community. See also [[simon-scrapes-agentic-os]] and [[llm-wiki-pattern]] for the same OS framing from other angles.

### 2. The "keys" model sharpens the F6 / ADR-021 decision (privacy & permissions)

Nate's 150K-email disaster is the cautionary tale behind our Activity Feed privacy work. **"Instructions ≠ capabilities"** reframes F6 precisely: the README's *promise* of "quiet by default" is an instruction; if the wake-up hook *can* write+push a SessionStart feed entry, it *will*. The honest fix (the one we chose) is to make the docs match the real capability and surface the disable controls — i.e., be explicit about which keys are on the ring rather than relying on a reassuring sentence. Strengthens the case for **aligning docs to ADR-018/021** and for keeping feed writes narrowly scoped + trivially disablable (`/sf:disable-feed`, `--skip-feed`).

### 3. The "bike method" is the cleanest argument for the F2 decision (mark experimental)

We chose to ship sf-wrap's classifier and sf-improve-skill's proposer as **experimental** rather than wiring the full LLM/eval loop for V1. The bike method *is* that argument: those capabilities haven't "earned their spot" yet — training wheels stay on, the docs say so honestly, and each real-world run is how they earn autonomy. This converges with [[py-harness-engineering]] ("self-evolution is the only consistently-helpful module") and [[simon-scrapes-self-improving-skills]] — three independent sources now point at *phased, feedback-driven* skill evolution over big-bang automation.

### 4. Session-handoff convergence (again)

Nate's session-handoff skill is the simpler, clipboard-shaped cousin of our `/sf:wrap` + `/sf:note` + `/sf:recall` + the wake-up hook. His is transient (paste into the next session); ours is durable (wiki, restored automatically). Same felt need, validated a second time (see [[nate-herk-give-me-10-mins]], which covers the same skill from the token-cost angle). Reinforces that the lifecycle skills solve a real problem.

### 5. Scope discipline = northstar

"Does it move the metric?" plus the dashboard skepticism reinforce the framework's curate-don't-kitchen-sink thesis and the leadership "scope discipline" lens. We deliberately did *not* build a dashboard — this is outside support for that call.

## Tensions / open questions

1. **Four C's in the README?** Worth adopting Nate's vocabulary in onboarding/README to make the framework legible to friends — or does it add a soft dependency on an external creator's framing? (Lean: borrow the 4-C *structure*, attribute lightly, don't hard-couple.)
2. **"Cadence" is our weakest layer.** Nate's 4th C is automation-while-laptop-closed. Our cadence today is mostly the SessionStart hook; sf-improve-skill (the closest thing to autonomous cadence) is exactly what we're shipping as *experimental*. An honest gap to name.
3. **Keys/scope as an explicit framework principle?** Should the framework ship a "permission audit" step (à la Nate's connections audit) in onboarding/doctor — enumerate every MCP/tool a friend's setup can touch, so capabilities are deliberate? Candidate sf-doctor or onboarding enhancement.
4. **`/insights`-style session analysis.** Nate runs `/insights` to mine local CC sessions for "what's working / quick wins." We already have raw `log.md` + session data; a read-only "insights" skill is a possible v2 (and aligns with [[py-harness-engineering]]'s "raw traces are the signal").

## Quotes worth preserving

> "The AI isn't the king. Everyone has access to the same AI models… Context is king."

> "Instructions are not the same as capabilities." / "If there's a send-email tool inside of that agent harness, then it could do it."

> "You have to assume that if your agent has access to read something or to do something, it will do it."

> "[Building a skill is] like you're teaching a kid to ride a bike… slowly there's more trust, slowly you take off the training wheels… it's earned its next phase."

> "Every time you run that skill it gets better. It's not a waste of time."

> "You can outsource your thinking, but you cannot outsource your understanding."

> "Productivity isn't how many hours did I work today. Productivity is did I actually move the needle closer to my goal."

## External references mentioned

- **Nate's free GitHub AIOS starter repo** — a clone-able AIOS skeleton with onboarding skills that "interview you," have you connect tools, and audit you. Strong comparable to our `/sf:install` + `/sf:interview` onboarding — worth a look for convergence/divergence.
- **`/insights` command** — generates an HTML report over ~30 days of local Claude Code sessions ("what's working / what's hindering / quick wins / new usage patterns").
- **Nate's session-handoff skill** — shared in his free school community.
- **Obsidian** — optional visualization layer over the files-and-folders OS (he's lukewarm on it; "I don't really know what I'm looking at and I don't really care").
- **"Other worlds"** — his term for separate Claude Code projects discoverable from the main OS.
- Prior Nate framings referenced: **Three M's** (Mindset / Method / Machine) and the **AI systems pyramid** (workflows → AI workflows → AI agents → teams of agents).

## Reference

- Raw source: `raw/transcripts/nate-herk-ai-os`
- Captured: 2026-05-30 from transcript dump by user
- Attribution: Nate Herk | AI Automation, YouTube video "I Turned Claude Opus 4.8 Into My Entire AI Operating System"
- Transcript length: chapter-marked transcript, ~29-minute video
