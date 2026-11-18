#!/usr/bin/env python3
"""directive-ledger: an append-only, tamper-evident log of what the owner decided.

Python 3.8+, standard library only, no network.

Each line of the ledger is one JSON object. It carries the hash of the previous
line, so editing or deleting any earlier line breaks the chain and `verify` says where.
A small ".head" file next to the ledger remembers the line count and last hash,
which also catches a deleted last line.

`missing` reads a conversation transcript (read only) and lists what a person typed
that is not in the ledger. It lists candidates and never adds them.
"""
import argparse
import datetime
import difflib
import hashlib
import json
import os
import re
import sys
import unicodedata

__version__ = "1.1.0"

DEFAULT_PATH = os.path.join(".", "ledger", "ledger.jsonl")
WHEN_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")

# -- conversation transcripts (read only) --------------------------------------------------
# A transcript is the .jsonl file a coding session keeps of one conversation: one JSON object
# per line. Nothing here writes to it. A line that cannot be read is skipped and counted.
# These rules match `ledger missing` in Backlog OS 1.1.0, so both tools find the same lines.
HARNESS_STARTS = ("<", "[Request interrupted", "[Backlog", "[card reminder]", "Caveat:",
                  "This session is being continued")
HARNESS_BLOCK = re.compile(r"<(system-reminder|user-prompt-submit-hook)>.*?</\1>", re.DOTALL)
SIMILAR, CANDIDATE_WIDTH = 0.85, 120
FREE_LIMIT = 5
FULL_URL = "https://vivastory4.gumroad.com/l/backlog-os"
MORE_LINE = ("+%d more. Backlog OS shows the full list, turns each decision into a card, "
             "and keeps handoff notes: " + FULL_URL)


class LedgerError(Exception):
    pass


def digest(record):
    body = {k: v for k, v in record.items() if k != "hash"}
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def read_text(path):
    with open(path, "rb") as handle:
        data = handle.read()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data.decode("utf-8")


def head_path(path):
    return path + ".head"


def check(path):
    """Walk the chain. Return the list of records, or raise LedgerError naming the first bad line."""
    name = os.path.basename(path)
    if not os.path.exists(path):
        if os.path.exists(head_path(path)):
            raise LedgerError("%s is missing (a .head file still exists)." % name)
        return []
    records, prev = [], ""
    for number, line in enumerate(read_text(path).splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            raise LedgerError("line %d is not valid JSON." % number)
        if not isinstance(record, dict) or record.get("prev") != prev or record.get("hash") != digest(record):
            raise LedgerError("line %d was changed or its neighbours were removed." % number)
        prev = record["hash"]
        records.append(record)
    if os.path.exists(head_path(path)):
        try:
            head = json.loads(read_text(head_path(path)))
            count, last = head["count"], head["last"]
        except (ValueError, KeyError, TypeError):
            raise LedgerError("the .head file is unreadable.")
        if count > len(records):
            raise LedgerError("line %d is missing: the ledger should have %d lines but has %d."
                              % (len(records) + 1, count, len(records)))
        if count == len(records) and last != prev:
            raise LedgerError("line %d does not match the recorded head." % count)
    return records


def write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(tmp, path)


def append(path, when, who, text, gloss=()):
    if not text or not text.strip():
        raise LedgerError("the directive text is empty.")
    if not WHEN_RE.fullmatch(when):
        raise LedgerError('--when must look like "2026-01-31 09:30".')
    if not who.strip():
        raise LedgerError("--who is empty.")
    records = check(path)
    record = {
        "id": "D-%04d" % (len(records) + 1),
        "when": when,
        "who": who.strip(),
        "text": text,
        "gloss": list(gloss),
        "prev": records[-1]["hash"] if records else "",
    }
    record["hash"] = digest(record)
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    write_atomic(head_path(path), json.dumps({"count": len(records) + 1, "last": record["hash"]}))
    return record


def one_line(record, width=70):
    text = " ".join(record["text"].split())
    if len(text) > width:
        text = text[: width - 3] + "..."
    return "%s  %s  %s: %s" % (record["id"], record["when"], record["who"], text)


def transcript_lines(path):
    """One dict per line of a transcript. None stands for a line that could not be read."""
    with open(path, "rb") as handle:
        for raw in handle:
            line = raw.decode("utf-8", "replace").strip().lstrip("﻿")
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                record = None
            yield record if isinstance(record, dict) else None


def transcript_time(stamp, utc=False):
    """A transcript timestamp as local time (or UTC). None when it cannot be read."""
    try:
        when = datetime.datetime.fromisoformat(str(stamp).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        return when
    try:
        return (when.astimezone(datetime.timezone.utc) if utc else when.astimezone()).replace(tzinfo=None)
    except (OverflowError, OSError, ValueError):
        return None


def typed_text(record):
    """The words a person typed on this line, or "" when the line is something else: a tool result,
    a line the program wrote for itself (meta), a summary, a sub-task, a hook's text, or anything
    that starts with "<"."""
    kind = record.get("type")
    if kind == "queue-operation":      # typed while the session was busy
        content = record.get("content") if record.get("operation") == "enqueue" else None
    elif kind == "user" and not (record.get("isMeta") or record.get("isSidechain") or record.get("isCompactSummary")):
        message = record.get("message")
        content = message.get("content") if isinstance(message, dict) else None
    else:
        return ""
    if isinstance(content, str):
        parts = [content]
    elif isinstance(content, list):
        if any(isinstance(part, dict) and part.get("type") == "tool_result" for part in content):
            return ""
        parts = [part["text"] for part in content
                 if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)]
    else:
        return ""
    kept = []
    for part in parts:
        part = HARNESS_BLOCK.sub("", part).strip()
        if part and not part.startswith(HARNESS_STARTS):
            kept.append(part)
    return "\n".join(kept)


def flat(text):
    """Text for comparing: no spaces, no punctuation, case ignored. Letters, digits and emoji stay."""
    return "".join(ch for ch in unicodedata.normalize("NFC", text).casefold()
                   if not ch.isspace() and unicodedata.category(ch)[0] not in "PZC"
                   and unicodedata.category(ch) not in ("Sm", "Sk"))


def in_ledger(words, ledger_texts):
    """True when the flattened words sit inside one ledger text, or are at least 85% similar to one."""
    if any(words in text for text in ledger_texts):
        return True
    for text in ledger_texts:
        matcher = difflib.SequenceMatcher(None, words, text, autojunk=False)
        if matcher.real_quick_ratio() >= SIMILAR and matcher.quick_ratio() >= SIMILAR and matcher.ratio() >= SIMILAR:
            return True
    return False


def find_missing(path, transcript, since=None, utc=False):
    """Compare what a person typed in a transcript with the ledger. Returns the report data; writes nothing."""
    if since is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", since):
        raise LedgerError("--since is a date like 2026-03-02.")
    if not os.path.isfile(transcript):
        raise LedgerError("transcript not found: %s" % os.path.basename(transcript))
    records = check(path)
    typed, queued, skipped = [], [], 0
    for record in transcript_lines(transcript):
        if record is None:
            skipped += 1
            continue
        text = typed_text(record)
        words = flat(text)
        if not words:
            continue
        when = transcript_time(record.get("timestamp"), utc)
        if since and when is not None and when.strftime("%Y-%m-%d") < since:
            continue
        (queued if record.get("type") == "queue-operation" else typed).append((when, text, words))
    seen = set(words for _when, _text, words in typed)
    for item in queued:                # a queued line usually shows up again as a normal line: count it once
        if item[2] not in seen:
            seen.add(item[2])
            typed.append(item)
    typed.sort(key=lambda item: (item[0] is None, item[0] or datetime.datetime.min))
    ledger_texts = [flat(str(entry.get("text", ""))) for entry in records]
    candidates = [(when, text) for when, text, words in typed if not in_ledger(words, ledger_texts)]
    return {"typed": len(typed), "found": len(typed) - len(candidates), "candidates": candidates, "skipped": skipped}


def missing_report(data, transcript, since=None, utc=False):
    """The report text. This free tool shows the first FREE_LIMIT candidates and says how many more there are."""
    out = ["# Typed words that are not in the ledger - %s" % os.path.basename(transcript), "",
           "Candidates only. Nothing was added to the ledger: a person decides which of these are instructions.",
           "Times are %s%s. Each line is the first %d characters."
           % ("UTC" if utc else "local time", ", from %s on" % since if since else "", CANDIDATE_WIDTH), ""]
    for when, text in data["candidates"][:FREE_LIMIT]:
        text = " ".join(text.split())
        out.append("- %s  %s" % (when.strftime("%Y-%m-%d %H:%M") if when else "(no time)     ",
                                 text if len(text) <= CANDIDATE_WIDTH else text[:CANDIDATE_WIDTH - 1] + "…"))
    if not data["candidates"]:
        out.append("- none")
    more = len(data["candidates"]) - FREE_LIMIT
    if more > 0:
        out.append(MORE_LINE % more)
    out += ["", "lines skipped (could not be read): %d" % data["skipped"],
            "typed by a person %d · in the ledger %d · candidates %d"
            % (data["typed"], data["found"], len(data["candidates"]))]
    return "\n".join(out) + "\n"


def safe_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def cmd_init(args):
    path = args.path
    if os.path.exists(path):
        print("Ledger already exists: %s" % path)
        return 0
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n"):
        pass
    write_atomic(head_path(path), json.dumps({"count": 0, "last": ""}))
    print("Created empty ledger: %s" % path)
    return 0


def cmd_add(args):
    when = args.when or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    record = append(args.path, when, args.who, args.text, args.gloss or [])
    print("Added %s" % record["id"])
    return 0


def cmd_verify(args):
    records = check(args.path)
    print("OK: %d line(s), chain intact." % len(records))
    return 0


def cmd_show(args):
    wanted = args.id.upper()
    for record in check(args.path):
        if record["id"] == wanted:
            print("%s" % record["id"])
            print("when: %s" % record["when"])
            print("who:  %s" % record["who"])
            print("text: %s" % record["text"])
            for note in record.get("gloss", []):
                print("gloss: %s" % note)
            print("hash: %s" % record["hash"])
            return 0
    raise LedgerError("%s is not in the ledger." % wanted)


def cmd_list(args):
    records = check(args.path)
    if args.last is not None:
        if args.last < 0:
            raise LedgerError("--last must be 0 or more.")
        records = records[len(records) - args.last:] if args.last else []
    for record in records:
        print(one_line(record))
    return 0


def cmd_missing(args):
    data = find_missing(args.path, args.transcript, args.since, args.utc)
    text = missing_report(data, args.transcript, args.since, args.utc)
    if args.out:
        out = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        write_atomic(out, text)
    sys.stdout.write(text)
    return 0


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--path", default=DEFAULT_PATH, help="ledger file (default: ./ledger/ledger.jsonl)")
    parser = argparse.ArgumentParser(prog="ledger.py", description="Append-only, tamper-evident log of owner decisions.")
    parser.add_argument("--version", action="version", version="directive-ledger " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", parents=[common], help="create an empty ledger").set_defaults(func=cmd_init)
    add = sub.add_parser("add", parents=[common], help="append one directive")
    add.add_argument("text", help="what the owner decided, in the owner's own words")
    add.add_argument("--who", default="owner", help="who gave the directive (default: owner)")
    add.add_argument("--when", help='when it was said, "YYYY-MM-DD HH:MM" (default: now)')
    add.add_argument("--gloss", action="append", help="optional plain-words note; may be repeated")
    add.set_defaults(func=cmd_add)
    sub.add_parser("verify", parents=[common], help="check the hash chain").set_defaults(func=cmd_verify)
    show = sub.add_parser("show", parents=[common], help="show one directive in full")
    show.add_argument("id", help="for example D-0001")
    show.set_defaults(func=cmd_show)
    lst = sub.add_parser("list", parents=[common], help="one line per directive")
    lst.add_argument("--last", type=int, help="only the last N")
    lst.set_defaults(func=cmd_list)
    missing = sub.add_parser("missing", parents=[common],
                             help="list what a person typed in a transcript that is not in the ledger "
                                  "(candidates only; nothing is added)")
    missing.add_argument("--transcript", required=True, help="the conversation's .jsonl file (read only)")
    missing.add_argument("--since", help="only words typed on or after this date: 2026-03-02")
    missing.add_argument("--out", help="also write the list to this Markdown file")
    missing.add_argument("--utc", action="store_true", help="show times in UTC instead of local time")
    missing.set_defaults(func=cmd_missing)
    return parser


def main(argv=None):
    safe_stdio()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except LedgerError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
