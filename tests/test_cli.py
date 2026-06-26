"""Tests for the omnist CLI (omnist/cli.py).

Each command is invoked in-process via ``main(argv)`` with stdin/stdout/
stderr captured -- no subprocess, consistent with this repo's fast test
suite. See docs/design/cli-spec.md for the full command surface; this
file's coverage grows alongside the CLI's own implementation PRs.
"""
from __future__ import annotations

import pytest

from omnist.cli import main


def run(argv, stdin=None, capsys=None, monkeypatch=None):
    if stdin is not None:
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(stdin))
    code = main(argv)
    out = capsys.readouterr()
    return code, out.out, out.err


class TestFormat:
    def test_reformats_oml_from_file_to_stdout(self, tmp_path, capsys):
        p = tmp_path / "in.oml"
        p.write_text('a: 1\nb: "x"\n')
        code, out, err = run(["format", str(p)], capsys=capsys, monkeypatch=None)
        assert code == 0
        assert err == ""
        assert out == 'a: 1\nb: "x"\n'

    def test_writes_to_output_file(self, tmp_path, capsys):
        src = tmp_path / "in.oml"
        src.write_text('a: 1\n')
        dst = tmp_path / "out.oml"
        code, out, err = run(["format", str(src), "-o", str(dst)], capsys=capsys, monkeypatch=None)
        assert code == 0
        assert out == ""
        assert dst.read_text() == 'a: 1\n'

    def test_reads_from_stdin(self, capsys, monkeypatch):
        code, out, err = run(
            ["format", "-"], stdin='a: 1\n', capsys=capsys, monkeypatch=monkeypatch)
        assert code == 0
        assert out == 'a: 1\n'

    def test_round_trips_canonically_even_if_messy(self, tmp_path, capsys):
        p = tmp_path / "in.oml"
        p.write_text('a:   1\nb:"x"\n')
        code, out, err = run(["format", str(p)], capsys=capsys, monkeypatch=None)
        assert code == 0
        assert out == 'a: 1\nb: "x"\n'

    def test_invalid_oml_is_a_clean_error_not_a_traceback(self, tmp_path, capsys):
        p = tmp_path / "bad.oml"
        p.write_text('a: [1, 2]\n')   # OML has no JSON-style array literal
        code, out, err = run(["format", str(p)], capsys=capsys, monkeypatch=None)
        assert code == 2
        assert out == ""
        assert err.startswith("error: ")

    def test_missing_file_is_a_clean_error(self, tmp_path, capsys):
        missing = tmp_path / "nope.oml"
        code, out, err = run(["format", str(missing)], capsys=capsys, monkeypatch=None)
        assert code == 2
        assert err.startswith("error: ")

    def test_missing_input_argument_is_argparse_usage_error(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["format"])
        assert exc.value.code == 2


class TestValidate:
    SCHEMA = 'record R { "a": integer }\nroot R\n'

    def test_valid_document_exits_0_text(self, tmp_path, capsys):
        doc_f = tmp_path / "d.json"
        doc_f.write_text('{"a": 1}')
        schema_f = tmp_path / "s.osd"
        schema_f.write_text(self.SCHEMA)
        code, out, err = run(
            ["validate", str(doc_f), "--from", "json", "--schema", str(schema_f)],
            capsys=capsys, monkeypatch=None)
        assert code == 0
        assert out == "valid\n"
        assert err == ""

    def test_invalid_document_exits_1_text(self, tmp_path, capsys):
        doc_f = tmp_path / "d.json"
        doc_f.write_text('{"a": 1, "b": "extra"}')
        schema_f = tmp_path / "s.osd"
        schema_f.write_text(self.SCHEMA)
        code, out, err = run(
            ["validate", str(doc_f), "--from", "json", "--schema", str(schema_f)],
            capsys=capsys, monkeypatch=None)
        assert code == 1
        assert out == "invalid:\n  at $.b: unexpected field\n"

    def test_result_format_json(self, tmp_path, capsys):
        doc_f = tmp_path / "d.json"
        doc_f.write_text('{"a": 1, "b": "extra"}')
        schema_f = tmp_path / "s.osd"
        schema_f.write_text(self.SCHEMA)
        code, out, err = run(
            ["validate", str(doc_f), "--from", "json", "--schema", str(schema_f),
             "--result-format", "json"],
            capsys=capsys, monkeypatch=None)
        assert code == 1
        assert out == (
            '{"ok": false, "errors": [{"path": "$.b", "message": "unexpected field"}]}\n')

    def test_result_format_oml(self, tmp_path, capsys):
        doc_f = tmp_path / "d.json"
        doc_f.write_text('{"a": 1}')
        schema_f = tmp_path / "s.osd"
        schema_f.write_text(self.SCHEMA)
        code, out, err = run(
            ["validate", str(doc_f), "--from", "json", "--schema", str(schema_f),
             "--result-format", "oml"],
            capsys=capsys, monkeypatch=None)
        assert code == 0
        assert out == "ok: true\n"

    def test_does_not_upgrade_scalars(self, tmp_path, capsys):
        # validate reads without schema-directed upgrading -- an ISO date
        # string stays a string and is reported as a type mismatch, never
        # silently upgraded to a real date first
        doc_f = tmp_path / "d.json"
        doc_f.write_text('{"d": "2024-01-01"}')
        schema_f = tmp_path / "s.osd"
        schema_f.write_text('record R { "d": date }\nroot R\n')
        code, out, err = run(
            ["validate", str(doc_f), "--from", "json", "--schema", str(schema_f)],
            capsys=capsys, monkeypatch=None)
        assert code == 0   # an ISO date string already satisfies `date` per matches_kind
        assert out == "valid\n"

    def test_unknown_format_value_is_argparse_usage_error(self, tmp_path):
        doc_f = tmp_path / "d.json"
        doc_f.write_text('{"a": 1}')
        with pytest.raises(SystemExit) as exc:
            main(["validate", str(doc_f), "--from", "bogus", "--schema", "s.osd"])
        assert exc.value.code == 2

    def test_missing_schema_flag_is_argparse_usage_error(self, tmp_path):
        doc_f = tmp_path / "d.json"
        doc_f.write_text('{"a": 1}')
        with pytest.raises(SystemExit) as exc:
            main(["validate", str(doc_f), "--from", "json"])
        assert exc.value.code == 2

    def test_malformed_input_is_a_clean_error_not_a_traceback(self, tmp_path, capsys):
        doc_f = tmp_path / "d.json"
        doc_f.write_text('{not valid json')
        schema_f = tmp_path / "s.osd"
        schema_f.write_text(self.SCHEMA)
        code, out, err = run(
            ["validate", str(doc_f), "--from", "json", "--schema", str(schema_f)],
            capsys=capsys, monkeypatch=None)
        assert code == 2
        assert err.startswith("error: ")

    def test_malformed_schema_is_a_clean_error_not_a_traceback(self, tmp_path, capsys):
        doc_f = tmp_path / "d.json"
        doc_f.write_text('{"a": 1}')
        schema_f = tmp_path / "s.osd"
        schema_f.write_text('record R { "a": integer }\n')   # no root
        code, out, err = run(
            ["validate", str(doc_f), "--from", "json", "--schema", str(schema_f)],
            capsys=capsys, monkeypatch=None)
        assert code == 2
        assert err.startswith("error: ")


class TestSchemaFormat:
    def test_reformats_osd_from_file_to_stdout(self, tmp_path, capsys):
        p = tmp_path / "in.osd"
        p.write_text('record R { "a": integer }\nroot R\n')
        code, out, err = run(["schema", "format", str(p)], capsys=capsys, monkeypatch=None)
        assert code == 0
        assert err == ""
        assert out == 'record R {\n    "a": integer,\n}\nroot R\n'

    def test_writes_to_output_file(self, tmp_path, capsys):
        src = tmp_path / "in.osd"
        src.write_text('record R { "a": integer }\nroot R\n')
        dst = tmp_path / "out.osd"
        code, out, err = run(
            ["schema", "format", str(src), "-o", str(dst)], capsys=capsys, monkeypatch=None)
        assert code == 0
        assert out == ""
        assert dst.read_text() == 'record R {\n    "a": integer,\n}\nroot R\n'

    def test_reads_from_stdin(self, capsys, monkeypatch):
        code, out, err = run(
            ["schema", "format", "-"],
            stdin='record R { "a": integer }\nroot R\n',
            capsys=capsys, monkeypatch=monkeypatch)
        assert code == 0
        assert out == 'record R {\n    "a": integer,\n}\nroot R\n'

    def test_invalid_osd_is_a_clean_error_not_a_traceback(self, tmp_path, capsys):
        p = tmp_path / "bad.osd"
        p.write_text('record R { "a": integer }\n')   # no root
        code, out, err = run(["schema", "format", str(p)], capsys=capsys, monkeypatch=None)
        assert code == 2
        assert out == ""
        assert err.startswith("error: ")

    def test_missing_schema_file_argument_is_argparse_usage_error(self):
        with pytest.raises(SystemExit) as exc:
            main(["schema", "format"])
        assert exc.value.code == 2

    def test_missing_schema_subcommand_is_argparse_usage_error(self):
        with pytest.raises(SystemExit) as exc:
            main(["schema"])
        assert exc.value.code == 2


class TestSchemaNormalize:
    def test_merges_structurally_identical_records(self, tmp_path, capsys):
        p = tmp_path / "in.osd"
        p.write_text(
            'record A { "x": integer }\n'
            'record B { "x": integer }\n'
            'record R { "a": A, "b": B }\n'
            'root R\n')
        code, out, err = run(["schema", "normalize", str(p)], capsys=capsys, monkeypatch=None)
        assert code == 0
        assert err == ""
        # A and B are structurally identical -- normalize merges them to one record
        assert out.count("record ") == 2   # the merged record + R, not 3

    def test_writes_to_output_file(self, tmp_path, capsys):
        src = tmp_path / "in.osd"
        src.write_text('record R { "a": integer }\nroot R\n')
        dst = tmp_path / "out.osd"
        code, out, err = run(
            ["schema", "normalize", str(src), "-o", str(dst)], capsys=capsys, monkeypatch=None)
        assert code == 0
        assert dst.read_text() == 'record R {\n    "a": integer,\n}\nroot R\n'

    def test_invalid_osd_is_a_clean_error(self, tmp_path, capsys):
        p = tmp_path / "bad.osd"
        p.write_text('record R { "a": integer }\n')   # no root
        code, out, err = run(["schema", "normalize", str(p)], capsys=capsys, monkeypatch=None)
        assert code == 2
        assert err.startswith("error: ")


class TestSchemaCompatibleWith:
    V1 = 'record R { "host": string }\nroot R\n'
    V2 = 'record R { "host": string, "port" [0,1]: integer }\nroot R\n'

    def test_compatible_text(self, tmp_path, capsys):
        a = tmp_path / "v1.osd"
        a.write_text(self.V1)
        b = tmp_path / "v2.osd"
        b.write_text(self.V2)
        code, out, err = run(
            ["schema", "compatible-with", str(a), str(b)], capsys=capsys, monkeypatch=None)
        assert code == 0
        assert out == "true\n"

    def test_incompatible_text(self, tmp_path, capsys):
        a = tmp_path / "v2.osd"
        a.write_text(self.V2)
        b = tmp_path / "v1.osd"
        b.write_text(self.V1)
        code, out, err = run(
            ["schema", "compatible-with", str(a), str(b)], capsys=capsys, monkeypatch=None)
        assert code == 1
        assert out == "false\n"

    def test_result_format_json(self, tmp_path, capsys):
        a = tmp_path / "v1.osd"
        a.write_text(self.V1)
        b = tmp_path / "v2.osd"
        b.write_text(self.V2)
        code, out, err = run(
            ["schema", "compatible-with", str(a), str(b), "--result-format", "json"],
            capsys=capsys, monkeypatch=None)
        assert code == 0
        assert out == '{"compatible": true}\n'

    def test_result_format_oml(self, tmp_path, capsys):
        a = tmp_path / "v1.osd"
        a.write_text(self.V1)
        b = tmp_path / "v2.osd"
        b.write_text(self.V2)
        code, out, err = run(
            ["schema", "compatible-with", str(a), str(b), "--result-format", "oml"],
            capsys=capsys, monkeypatch=None)
        assert code == 0
        assert out == "compatible: true\n"

    def test_malformed_schema_is_a_clean_error(self, tmp_path, capsys):
        a = tmp_path / "bad.osd"
        a.write_text('record R { "a": integer }\n')
        b = tmp_path / "v1.osd"
        b.write_text(self.V1)
        code, out, err = run(
            ["schema", "compatible-with", str(a), str(b)], capsys=capsys, monkeypatch=None)
        assert code == 2
        assert err.startswith("error: ")


class TestSchemaEquivalent:
    def test_equivalent_text(self, tmp_path, capsys):
        a = tmp_path / "a.osd"
        a.write_text('record R { "x": integer }\nroot R\n')
        b = tmp_path / "b.osd"
        b.write_text('record R { "x": integer }\nroot R\n')
        code, out, err = run(
            ["schema", "equivalent", str(a), str(b)], capsys=capsys, monkeypatch=None)
        assert code == 0
        assert out == "true\n"

    def test_not_equivalent_text(self, tmp_path, capsys):
        a = tmp_path / "a.osd"
        a.write_text('record R { "x": integer }\nroot R\n')
        b = tmp_path / "b.osd"
        b.write_text('record R { "x": integer, "y" [0,1]: string }\nroot R\n')
        code, out, err = run(
            ["schema", "equivalent", str(a), str(b)], capsys=capsys, monkeypatch=None)
        assert code == 1
        assert out == "false\n"

    def test_result_format_json(self, tmp_path, capsys):
        a = tmp_path / "a.osd"
        a.write_text('record R { "x": integer }\nroot R\n')
        b = tmp_path / "b.osd"
        b.write_text('record R { "x": integer, "y" [0,1]: string }\nroot R\n')
        code, out, err = run(
            ["schema", "equivalent", str(a), str(b), "--result-format", "json"],
            capsys=capsys, monkeypatch=None)
        assert code == 1
        assert out == '{"equivalent": false}\n'


class TestTopLevel:
    def test_missing_command_is_argparse_usage_error(self):
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 2

    def test_unknown_command_is_argparse_usage_error(self):
        with pytest.raises(SystemExit) as exc:
            main(["bogus"])
        assert exc.value.code == 2
