# Koneta source-trace tools

These tracked scripts operate on the local-only cards in
`workbench/koneta-stock/` without adopting or publishing them.

- `mine_transcripts.py` mines recent Codex, Claude Code, and Antigravity JSONL
  turns and writes draft cards with source locators.
- `backfill_source_trace.py` finds a unique raw turn for an existing card. It
  defaults to a dry run; `--write` is required to update cards.
- `audit_source_trace.py` verifies that every `exact` card still points to an
  existing raw turn and reproduces the stored quote hash.

## Source-trace contract

An exact trace stores the source platform, complete session UUID, absolute raw
log path, timestamp, one-based turn index, user/model line numbers, and a
SHA-256 quote hash calculated from the unabridged user and model messages.

Use `ambiguous` when more than one raw turn matches and `missing` when none do.
Unverified locator fields remain empty; they are never inferred from card copy
or relay prompts.

The draft cards and raw logs stay ignored by Git. Only the deterministic tools
and their contract are versioned here.
