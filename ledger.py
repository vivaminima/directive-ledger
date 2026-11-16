#!/usr/bin/env python3
"""directive-ledger: an append-only, tamper-evident log of what the owner decided.

Python 3.8+, standard library only, no network.

Each line of the ledger is one JSON object. It carries the hash of the previous
line, so editing or deleting any earlier line breaks the chain and `verify` says where.
A small ".head" file next to the ledger remembers the line count and last hash,
which also catches a deleted last line.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

DEFAULT_PATH = os.path.join(".", "ledger", "ledger.jsonl")
WHEN_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")


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


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--path", default=DEFAULT_PATH, help="ledger file (default: ./ledger/ledger.jsonl)")
    parser = argparse.ArgumentParser(prog="ledger.py", description="Append-only, tamper-evident log of owner decisions.")
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
