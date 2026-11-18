# Directive Ledger

*Part of the [Vivaminima tools](https://github.com/vivaminima) for Claude Code users.*

<img src="https://raw.githubusercontent.com/vivaminima/vivaminima/main/img/run/directive-ledger.png" width="760" alt="directive-ledger: real output of the free version on a made-up sample">

Keep your AI coding decisions in an append-only log, so new sessions can recover what matters without rereading the entire conversation.

Version 1.1.0. New: `missing` finds what you typed that never reached the ledger, and the tool installs as a Claude Code plugin. Ledgers written by 1.0 read as they are.

## Why

- Trimming instruction files drops rules. A decision that only lives in a long instruction file disappears the day someone shortens it.
- Chat history gets compacted. The exact words of a decision are the first thing to go.
- A hash chain shows if anyone edited the past. Every line carries the hash of the line before it, so one changed or deleted line is caught.

## Quick start

```
python ledger.py init
python ledger.py add "Ship the Windows build first" --who owner --gloss "Mac comes after launch"
python ledger.py list --last 5
python ledger.py verify
```

`show D-0001` prints one directive in full. The ledger lives in `./ledger/ledger.jsonl` (change it with `--path`). A sample ledger is in `examples/`:

```
python ledger.py list --path examples/ledger.jsonl
python ledger.py verify --path examples/ledger.jsonl
```

In Claude Code, tell the session: "Read the last 10 lines of the ledger before you start, and add a line whenever I decide something."

## Did your AI forget what you said? (`missing`)

`missing` reads one conversation transcript (the `.jsonl` file Claude Code keeps for a session) and lists what a person typed that is not in the ledger. Tool results, hook text, summaries and sub-task lines are left out. A typed line counts as "in the ledger" when it sits inside a ledger entry or is at least 85% the same, ignoring case, spaces and punctuation.

```
python ledger.py missing --transcript examples/transcript_example.jsonl --utc --path examples/ledger.jsonl
```

```
# Typed words that are not in the ledger - transcript_example.jsonl

Candidates only. Nothing was added to the ledger: a person decides which of these are instructions.
Times are UTC. Each line is the first 120 characters.

- 2026-03-19 09:15  Use the blue logo on the download page, not the green one.
- 2026-03-19 10:05  Price stays at $19 until the end of April.
- 2026-03-19 11:20  Never email the whole list twice in one week.
- 2026-03-19 13:07  The installer must work offline.
- 2026-03-19 14:30  Ask me before you delete any customer file.
+1 more. Backlog OS shows the full list, turns each decision into a card, and keeps handoff notes: https://vivastory4.gumroad.com/l/backlog-os

lines skipped (could not be read): 1
typed by a person 8 · in the ledger 2 · candidates 6
```

- `--since 2026-03-01` looks only at words typed on or after that date.
- `--out missing.md` also writes the list to a file.
- `--utc` shows times in UTC instead of local time.

The transcript is only read. Nothing is added to the ledger: you pick the lines that are real decisions and `add` them. This free tool shows the first 5 candidates and counts the rest.

## Install as a Claude Code plugin

Inside Claude Code:

```
/plugin marketplace add vivaminima/vivaminima
/plugin install directive-ledger@vivaminima
```

Then say "record this decision", "what did I decide?" or "did you forget what I said?". The skill runs the same `ledger.py` that ships in this repository.

## What it needs

- Python 3.8+
- Standard library only
- No network, no LLM calls
- The tool's own messages are plain text. Your own words are printed back as you typed them; a character the console cannot show is replaced instead of stopping the run.

`verify` exits non-zero and names the first broken line. Run the tests with `python test_ledger.py`.

## Want the full system?

Backlog OS ($39) adds the full `missing` list, cards with handoff notes, an index, a morning brief, a 4-times-a-day refresh cycle, session hooks and a worked example. Don't cut your rules — move the detail into cards: https://vivastory4.gumroad.com/l/backlog-os

Not affiliated with Anthropic.
