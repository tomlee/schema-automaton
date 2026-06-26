"""Executes the exact CLI examples shown in docs/cli.md, against the real
fixture files in examples/cli/, so the docs can't silently drift from what
running them actually produces -- same convention as test_docs.py, applied
to the CLI page. Assumes cwd is the repo root (pytest's default).
"""
from __future__ import annotations

from omnist.cli import main


def run(argv, capsys, stdin_text=None, monkeypatch=None):
    if stdin_text is not None:
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
    code = main(argv)
    out = capsys.readouterr()
    return code, out.out, out.err


class TestFormatExample:
    def test_messy_oml_reformats(self, capsys):
        code, out, err = run(["format", "examples/cli/messy.oml"], capsys)
        assert code == 0
        assert out == 'a: 1\nb: "x"\n'
        assert err == ""

    def test_pipe_example(self, capsys, monkeypatch):
        code, out, err = run(["format", "-"], capsys, stdin_text="a:   1", monkeypatch=monkeypatch)
        assert code == 0
        assert out == "a: 1\n"


class TestConvertExamples:
    def test_order_json_to_oml(self, capsys):
        code, out, err = run(
            ["convert", "examples/cli/order.json", "--from", "json", "--to", "oml"], capsys)
        assert code == 0
        assert out == (
            'order: {\n'
            '  id: "A1"\n'
            '  status: "shipped"\n'
            '  total: 29.97\n'
            '  address: {\n'
            '    street: "1 Main"\n'
            '    city: "London"\n'
            '  }\n'
            '  items: {\n'
            '    sku: "W"\n'
            '    qty: 3\n'
            '    price: 9.99\n'
            '  }\n'
            '  items: {\n'
            '    sku: "G"\n'
            '    qty: 1\n'
            '    price: 9.99\n'
            '  }\n'
            '}\n'
        )

    def test_order_xml_to_oml_with_schema(self, capsys):
        code, out, err = run(
            ["convert", "examples/cli/order.xml", "--from", "xml", "--to", "oml",
             "--schema", "examples/cli/order.osd"], capsys)
        assert code == 0
        assert out.startswith('order: {\n  id: "A1"\n')

    def test_toml_to_json_via_stdin(self, capsys, monkeypatch):
        with open("examples/cli/order.toml", encoding="utf-8") as f:
            toml_text = f.read()
        code, out, err = run(
            ["convert", "-", "--from", "toml", "--to", "json"], capsys,
            stdin_text=toml_text, monkeypatch=monkeypatch)
        assert code == 0
        assert out == (
            '{"order": {"id": "A1", "status": "shipped", "total": 29.97, '
            '"items": [{"sku": "W", "qty": 3, "price": 9.99}, '
            '{"sku": "G", "qty": 1, "price": 9.99}], '
            '"address": {"street": "1 Main", "city": "London"}}}\n'
        )

    def test_report_on_lossy_json_to_toml(self, capsys):
        code, out, err = run(
            ["convert", "examples/cli/lossy.json", "--from", "json", "--to", "toml", "--report"],
            capsys)
        assert code == 0
        assert err == "warning: $.a: null value dropped (TOML has no null)\n"

    def test_strict_on_lossy_json_to_toml(self, capsys):
        code, out, err = run(
            ["convert", "examples/cli/lossy.json", "--from", "json", "--to", "toml", "--strict"],
            capsys)
        assert code == 1
        assert out == ""
        assert err == "error: warning: $.a: null value dropped (TOML has no null)\n"


class TestCheckExamples:
    def test_lossy_json_to_toml(self, capsys):
        code, out, err = run(
            ["check", "examples/cli/lossy.json", "--from", "json", "--to", "toml"], capsys)
        assert code == 0
        assert out == "warning: $.a: null value dropped (TOML has no null)\n"

    def test_lossy_json_to_toml_strict(self, capsys):
        code, out, err = run(
            ["check", "examples/cli/lossy.json", "--from", "json", "--to", "toml", "--strict"],
            capsys)
        assert code == 1
        assert out == "warning: $.a: null value dropped (TOML has no null)\n"


class TestInferExample:
    def test_sample1_sample2(self, capsys):
        code, out, err = run(
            ["infer", "examples/cli/sample1.json", "examples/cli/sample2.json", "--from", "json"],
            capsys)
        assert code == 0
        assert out == (
            'record Root {\n'
            '    "host": string,\n'
            '    "port" [0,1]: integer,\n'
            '}\n'
            'root Root\n'
        )


class TestValidateExamples:
    def test_order_is_valid(self, capsys):
        code, out, err = run(
            ["validate", "examples/cli/order.json", "--from", "json",
             "--schema", "examples/cli/order.osd"], capsys)
        assert code == 0
        assert out == "valid\n"

    def test_invalid_order_text(self, capsys):
        code, out, err = run(
            ["validate", "examples/cli/invalid-order.json", "--from", "json",
             "--schema", "examples/cli/order.osd"], capsys)
        assert code == 1
        assert out == (
            "invalid:\n"
            "  at $.order.total: expected number, got string ('ten')\n"
            "  at $.order: field 'items' occurs 0 time(s), expected at least 1\n"
        )

    def test_invalid_order_json(self, capsys):
        code, out, err = run(
            ["validate", "examples/cli/invalid-order.json", "--from", "json",
             "--schema", "examples/cli/order.osd", "--result-format", "json"], capsys)
        assert code == 1
        assert out == (
            '{"ok": false, "errors": ['
            '{"path": "$.order.total", "message": "expected number, got string (\'ten\')"}, '
            '{"path": "$.order", '
            '"message": "field \'items\' occurs 0 time(s), expected at least 1"}'
            ']}\n'
        )


class TestSchemaFormatExample:
    def test_messy_osd_reformats(self, capsys):
        code, out, err = run(["schema", "format", "examples/cli/messy.osd"], capsys)
        assert code == 0
        assert out == 'record R {\n    "a": integer,\n    "b": string,\n}\nroot R\n'


class TestSchemaNormalizeExample:
    def test_merges_duplicate_records(self, capsys):
        code, out, err = run(
            ["schema", "normalize", "examples/cli/duplicate-records.osd"], capsys)
        assert code == 0
        assert out == (
            'record A {\n'
            '    "x": integer,\n'
            '}\n'
            'record R {\n'
            '    "a": A,\n'
            '    "b": A,\n'
            '}\n'
            'root R\n'
        )


class TestSchemaCompatibleWithExample:
    def test_v1_compatible_with_v2(self, capsys):
        code, out, err = run(
            ["schema", "compatible-with", "examples/cli/v1.osd", "examples/cli/v2.osd"], capsys)
        assert code == 0
        assert out == "true\n"


class TestSchemaEquivalentExample:
    def test_v1_not_equivalent_to_v2(self, capsys):
        code, out, err = run(
            ["schema", "equivalent", "examples/cli/v1.osd", "examples/cli/v2.osd"], capsys)
        assert code == 1
        assert out == "false\n"
