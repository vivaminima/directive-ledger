import contextlib
import io
import json
import os
import shutil
import tempfile
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = ledger.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "ledger", "ledger.jsonl")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def add(self, text, when="2026-01-05 09:00"):
        return run("add", text, "--when", when, "--path", self.path)

    def fill(self, n=3):
        for i in range(n):
            self.assertEqual(self.add("directive %d" % (i + 1), "2026-01-0%d 09:00" % (i + 1))[0], 0)

    def lines(self):
        with open(self.path, encoding="utf-8") as handle:
            return handle.read().splitlines()

    def write_lines(self, lines):
        with open(self.path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("".join(line + "\n" for line in lines))

    def test_init_creates_empty_ledger(self):
        code, out, _ = run("init", "--path", self.path)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(self.path))
        self.assertEqual(run("verify", "--path", self.path)[0], 0)

    def test_add_writes_one_line(self):
        code, out, _ = self.add("Ship the Windows build first")
        self.assertEqual(code, 0)
        self.assertIn("D-0001", out)
        self.assertEqual(len(self.lines()), 1)

    def test_ids_increase(self):
        self.fill(3)
        text = run("list", "--path", self.path)[1]
        for number in ("D-0001", "D-0002", "D-0003"):
            self.assertIn(number, text)

    def test_verify_passes(self):
        self.fill(4)
        code, out, _ = run("verify", "--path", self.path)
        self.assertEqual(code, 0)
        self.assertIn("4 line(s)", out)

    def test_verify_catches_edited_line(self):
        self.fill(3)
        lines = self.lines()
        lines[1] = lines[1].replace("directive 2", "directive TWO")
        self.write_lines(lines)
        code, _, err = run("verify", "--path", self.path)
        self.assertNotEqual(code, 0)
        self.assertIn("line 2", err)

    def test_verify_catches_deleted_middle_line(self):
        self.fill(3)
        lines = self.lines()
        del lines[1]
        self.write_lines(lines)
        code, _, err = run("verify", "--path", self.path)
        self.assertNotEqual(code, 0)
        self.assertIn("line 2", err)

    def test_verify_catches_deleted_last_line(self):
        self.fill(3)
        self.write_lines(self.lines()[:-1])
        code, _, err = run("verify", "--path", self.path)
        self.assertNotEqual(code, 0)
        self.assertIn("line 3", err)

    def test_add_refuses_on_broken_ledger(self):
        self.fill(2)
        lines = self.lines()
        lines[0] = lines[0].replace("directive 1", "changed")
        self.write_lines(lines)
        self.assertNotEqual(self.add("more")[0], 0)

    def test_show(self):
        self.add("No paid ads this month")
        run("add", "Hold hiring", "--who", "founder", "--gloss", "until Q3", "--when", "2026-01-06 10:00", "--path", self.path)
        code, out, _ = run("show", "d-0002", "--path", self.path)
        self.assertEqual(code, 0)
        self.assertIn("Hold hiring", out)
        self.assertIn("founder", out)
        self.assertIn("until Q3", out)
        self.assertNotEqual(run("show", "D-0099", "--path", self.path)[0], 0)

    def test_list_last(self):
        self.fill(5)
        out = run("list", "--last", "2", "--path", self.path)[1]
        self.assertEqual(len(out.strip().splitlines()), 2)
        self.assertIn("D-0005", out)
        self.assertNotIn("D-0003", out)

    def test_unicode_round_trip(self):
        text = "Ship caf\u00e9 menu \u2014 \u65e5\u672c\u8a9e \u0414\u0430"
        self.add(text)
        self.assertEqual(run("verify", "--path", self.path)[0], 0)
        self.assertEqual([r["text"] for r in ledger.check(self.path)], [text])

    def test_bad_when_is_refused(self):
        code, _, err = run("add", "x", "--when", "yesterday", "--path", self.path)
        self.assertNotEqual(code, 0)


def said(text, stamp="2026-03-19T09:00:00.000Z", **extra):
    record = {"type": "user", "timestamp": stamp, "message": {"role": "user", "content": text}}
    record.update(extra)
    return record


class MissingTests(unittest.TestCase):
    """`missing`: what a person typed in a transcript that is not in the ledger."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "ledger", "ledger.jsonl")
        self.transcript = os.path.join(self.dir, "talk.jsonl")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def add(self, text):
        self.assertEqual(run("add", text, "--when", "2026-03-01 09:00", "--path", self.path)[0], 0)

    def talk(self, records, raw=()):
        with open(self.transcript, "w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            for line in raw:
                handle.write(line + "\n")

    def missing(self, *more):
        return run("missing", "--transcript", self.transcript, "--utc", "--path", self.path, *more)

    def candidates(self, out):
        return [line for line in out.splitlines() if line.startswith("- ")]

    def test_missing_lists_only_words_not_in_ledger(self):
        self.add("Ship the Windows build first")
        self.talk([said("Ship the Windows build first", "2026-03-19T09:00:00.000Z"),
                   said("Never email the list twice in one week", "2026-03-19T10:30:00.000Z")])
        code, out, _ = self.missing()
        self.assertEqual(code, 0)
        self.assertEqual(self.candidates(out), ["- 2026-03-19 10:30  Never email the list twice in one week"])
        self.assertEqual(out.splitlines()[-1],
                         "typed by a person 2 · in the ledger 1 · candidates 1")

    def test_missing_ignores_case_spaces_punctuation_and_small_typos(self):
        self.add("Support replies go out within one business day")
        self.talk([said("support replies go out   within ONE business day!!"),
                   said("Support replies go out within one busines day"),
                   said("replies go out within one business day")])
        out = self.missing()[1]
        self.assertEqual(self.candidates(out), ["- none"])
        self.assertTrue(out.rstrip().endswith("typed by a person 3 · in the ledger 3 · candidates 0"))

    def test_missing_skips_lines_no_person_typed(self):
        self.talk([
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "a reply"}]}},
            said("<command-name>/status</command-name>", isMeta=True),
            said("words from a sub-task", isSidechain=True),
            said("a summary of the talk so far", isCompactSummary=True),
            said([{"type": "tool_result", "tool_use_id": "t1", "content": "42 files"}]),
            said("<local-command-stdout>ok</local-command-stdout>"),
            said("[Request interrupted by user]"),
            said([{"type": "text", "text": "Keep the old price"},
                  {"type": "text", "text": "<system-reminder>not typed</system-reminder>"}]),
        ])
        out = self.missing()[1]
        self.assertEqual(self.candidates(out), ["- 2026-03-19 09:00  Keep the old price"])
        self.assertIn("typed by a person 1 · in the ledger 0 · candidates 1", out)

    def test_missing_free_version_shows_five_then_points_to_full_list(self):
        self.talk([said("decision number %d is about topic %s" % (i, "abcdefgh"[i] * 12),
                        "2026-03-19T09:%02d:00.000Z" % i) for i in range(8)])
        out = self.missing()[1]
        shown = self.candidates(out)
        self.assertEqual(len(shown), 5)
        self.assertIn("decision number 0", shown[0])
        self.assertIn("decision number 4", shown[4])
        lines = out.splitlines()
        more = lines[lines.index(shown[4]) + 1]
        self.assertTrue(more.startswith("+3 more. Backlog OS shows the full list"))
        self.assertTrue(more.endswith(ledger.FULL_URL))
        self.assertEqual(lines[-1], "typed by a person 8 · in the ledger 0 · candidates 8")
        self.assertNotIn("decision number 5", out)

    def test_missing_exactly_five_has_no_more_line(self):
        self.talk([said("decision number %d is about topic %s" % (i, "abcdefgh"[i] * 12)) for i in range(5)])
        out = self.missing()[1]
        self.assertEqual(len(self.candidates(out)), 5)
        self.assertNotIn("more. Backlog OS", out)

    def test_missing_has_no_all_switch(self):
        self.talk([said("one")])
        with self.assertRaises(SystemExit):
            self.missing("--all")

    def test_missing_korean_and_emoji(self):
        self.add("윈도우 빌드부터 먼저 내자 🚀")
        self.talk([said("윈도우 빌드부터 먼저 내자 🚀", "2026-03-19T09:00:00.000Z"),
                   said("환불 문의는 내가 직접 답한다 🙂", "2026-03-19T09:05:00.000Z"),
                   said("🙂", "2026-03-19T09:06:00.000Z")])
        code, out, _ = self.missing()
        self.assertEqual(code, 0)
        self.assertEqual(self.candidates(out), ["- 2026-03-19 09:05  환불 문의는 내가 직접 답한다 🙂",
                                                "- 2026-03-19 09:06  🙂"])
        self.assertIn("typed by a person 3 · in the ledger 1 · candidates 2", out)

    def test_missing_empty_transcript(self):
        self.talk([])
        code, out, _ = self.missing()
        self.assertEqual(code, 0)
        self.assertEqual(self.candidates(out), ["- none"])
        self.assertEqual(out.splitlines()[-1], "typed by a person 0 · in the ledger 0 · candidates 0")

    def test_missing_skips_unreadable_and_unknown_lines(self):
        self.talk([said("Hold hiring until summer"),
                   {"type": "something-new", "payload": {"deep": [1, 2, 3]}},
                   {"type": "user", "message": "not a dict"},
                   {"type": "user", "message": {"role": "user", "content": 7}},
                   {"no_type_at_all": True}],
                  raw=['{"type": "user", "message": {"content": "cut o', "[1, 2, 3]", "plain words, not JSON"])
        code, out, _ = self.missing()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.candidates(out)), 1)
        self.assertIn("lines skipped (could not be read): 3", out)
        self.assertIn("typed by a person 1 · in the ledger 0 · candidates 1", out)

    def test_missing_since_and_out_file(self):
        self.talk([said("old words from last month", "2026-02-10T09:00:00.000Z"),
                   said("new words from this month", "2026-03-19T09:00:00.000Z")])
        target = os.path.join(self.dir, "out", "missing.md")
        code, out, _ = self.missing("--since", "2026-03-01", "--out", target)
        self.assertEqual(code, 0)
        self.assertNotIn("old words", out)
        self.assertIn("new words", out)
        with open(target, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), out)
        self.assertNotEqual(self.missing("--since", "March")[0], 0)

    def test_missing_never_writes_to_ledger_or_transcript(self):
        self.add("Ship the Windows build first")
        self.talk([said("Something that is not in the ledger at all")])
        files = (self.path, self.path + ".head", self.transcript)
        before = [ledger.read_text(p) for p in files]
        self.assertEqual(self.missing()[0], 0)
        after = [ledger.read_text(p) for p in files]
        self.assertEqual(before, after)
        self.assertIn("1 line(s)", run("verify", "--path", self.path)[1])

    def test_missing_queued_line_is_counted_once(self):
        self.talk([{"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-03-19T09:00:00.000Z",
                    "content": "Typed while the session was busy"},
                   said("Typed while the session was busy", "2026-03-19T09:00:05.000Z"),
                   {"type": "queue-operation", "operation": "dequeue", "timestamp": "2026-03-19T09:00:06.000Z"}])
        out = self.missing()[1]
        self.assertEqual(len(self.candidates(out)), 1)
        self.assertIn("typed by a person 1 ·", out)

    def test_missing_long_line_is_cut_and_no_transcript_is_an_error(self):
        self.talk([said("word " * 60)])
        line = self.candidates(self.missing()[1])[0]
        self.assertTrue(line.endswith("…"))
        self.assertEqual(len(line.split("  ", 1)[1]), ledger.CANDIDATE_WIDTH)
        code, _, err = run("missing", "--transcript", os.path.join(self.dir, "nope.jsonl"), "--path", self.path)
        self.assertNotEqual(code, 0)
        self.assertIn("transcript not found", err)

    def test_old_ledger_still_reads_and_example_matches(self):
        here = os.path.dirname(os.path.abspath(__file__))
        old = os.path.join(here, "examples", "ledger.jsonl")
        self.assertEqual(run("verify", "--path", old)[0], 0)
        code, out, _ = run("missing", "--transcript", os.path.join(here, "examples", "transcript_example.jsonl"),
                           "--utc", "--path", old)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.candidates(out)), 5)
        self.assertIn("+1 more. Backlog OS", out)
        self.assertEqual(out.splitlines()[-1], "typed by a person 8 · in the ledger 2 · candidates 6")


if __name__ == "__main__":
    unittest.main()
