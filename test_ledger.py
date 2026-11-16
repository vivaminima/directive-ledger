import contextlib
import io
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


if __name__ == "__main__":
    unittest.main()
