"""
lib.adapter — native-harness (Claude Code) adapter layer.

Spec §3.9 A-9 keeps knowledge-layer files harness-neutral and confines
harness glue to a separate adapter dir. `lib/portability/` is the FOREIGN
half of that rule (AGENTS.md surface + neutrality lints); this package is
the NATIVE half: surfaces that are allowed — expected — to speak Claude
Code's language (slash commands, CLAUDE.md hierarchy, plugin paths).
"""
