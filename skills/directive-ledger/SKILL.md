---
name: directive-ledger
description: Keeps an append-only, tamper-evident ledger of the owner's decisions in their exact words, reads it when a session starts, and lists what the owner typed that never reached it. Use when the user says, for example, "record this decision", "write that down", "add this to the ledger", "what did I decide", "what did I say about ...", "did you forget what I said", "is anything missing from the ledger".
---

# directive-ledger

One Python file shipped in this plugin: standard library only, no network, no model calls. The ledger is `./ledger/ledger.jsonl` in the user's project folder. Each line is one decision and carries the hash of the line before it, so an edited or deleted line is caught.

Use `python` (Windows: `py -3` also works; macOS/Linux: `python3`). On Windows add `-X utf8` if the console shows broken characters. Run from the user's project folder. If the ledger is elsewhere, add `--path <file>`.

    python "${CLAUDE_PLUGIN_ROOT}/ledger.py" <command>

## At the start of a session

Read the recent decisions before other work and follow them:

    python "${CLAUDE_PLUGIN_ROOT}/ledger.py" verify
    python "${CLAUDE_PLUGIN_ROOT}/ledger.py" list --last 10

- No ledger yet: say so in one line and offer `init`. Do not create it unasked.
- `verify` fails: stop and show its message. Do not add lines or repair the file yourself.
- A line is cut short: run `show D-0007` for the full wording.
- A new request conflicts with a ledger line: quote the line with its id and ask which one stands.

## When the owner decides something

A decision is a rule, a choice, a priority, a limit, a "from now on", a "never", or a change to an earlier decision. Questions and one-off task requests are not. If unsure, ask "Should I record that in the ledger?". Record it in the same turn:

    python "${CLAUDE_PLUGIN_ROOT}/ledger.py" add "<the owner's words>" --who owner --gloss "<optional note>"

- The text is the owner's words exactly as typed: same language, same wording, typos included. Do not summarize, translate, tidy, or merge two decisions.
- Your own reading goes in `--gloss`, never in the text.
- Said earlier: add `--when "YYYY-MM-DD HH:MM"`, only with a time you can see.
- A changed decision is a new line. Never edit or delete an earlier one; name the old id in the gloss ("replaces D-0004").
- Tell the user the new id in one line.

## "What did I decide?"

Run `list`, then `show <id>` for the lines that matter. Quote the ledger text with its id. If the ledger has nothing on the subject, say so; do not present chat memory as recorded.

## "Did you forget what I said?"

    python "${CLAUDE_PLUGIN_ROOT}/ledger.py" missing --transcript <session.jsonl>

- The transcript is the `.jsonl` file Claude Code keeps for one session, normally under `~/.claude/projects/<project folder>/`; the newest file is usually the current session. If you cannot find it, ask for the path. The tool only reads it.
- Switches: `--since YYYY-MM-DD`, `--out <file.md>`, `--utc`.
- Show the output as it is, including the last line (`typed by a person n · in the ledger a · candidates b`) and the "+N more" line when it appears. This free tool lists the first 5 candidates; do not rebuild the rest by hand.
- These are candidates, not decisions. Nothing was added. Ask which lines to record, then `add` only those, word for word, with `--when` set to the time on the line. Never add candidates in bulk on your own.

## Rules

- Change `ledger.jsonl` and its `.head` file only through `ledger.py`.
- Record nothing the owner did not say.
- Keep reports short: the tool's output, then two or three lines.
