# Directive Ledger

*Part of the [Vivaminima tools](https://github.com/vivaminima) for Claude Code users.*

<img src="https://raw.githubusercontent.com/vivaminima/vivaminima/main/img/run/directive-ledger.png" width="760" alt="directive-ledger: real output of the free version on a made-up sample">

An append-only, tamper-evident log of what the owner decided, so new AI coding sessions read one line instead of the whole chat.

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

## What it needs

- Python 3.8+
- Standard library only
- No network, no LLM calls
- Plain ASCII output, so it prints in any console

`verify` exits non-zero and names the first broken line. Run the tests with `python test_ledger.py`.

## Want the full system?

Backlog OS ($39) adds cards, an index, a morning brief, a 4-times-a-day refresh cycle, session start/stop hooks and a worked example. Don't cut your rules — move the detail into cards: https://vivastory4.gumroad.com/l/backlog-os

Not affiliated with Anthropic.
