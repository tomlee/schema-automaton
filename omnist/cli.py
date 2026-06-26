"""The ``omnist`` command-line interface.

A thin wrapper over the public :mod:`omnist` API -- see
``docs/design/cli-spec.md`` for the full command surface. Each command maps
to one or two calls into the library; this module adds no new behavior of
its own beyond argument parsing, file/stdio plumbing, and exit codes.
"""

from __future__ import annotations

import argparse
import json as _json
import sys
from typing import Any, Optional, Sequence

from . import (
    Doc,
    ParseError,
    SchemaError,
    ValidationResult,
    WriteError,
    doc,
    infer,
    parse_schema,
    read_json,
    read_oml,
    read_toml,
    read_xml,
    read_yaml,
    to_dsl,
    write_oml,
)

FMT_CHOICES = ["json", "yaml", "toml", "xml", "oml"]
RESULT_FORMAT_CHOICES = ["text", "json", "oml"]

_READERS = {
    "json": read_json,
    "yaml": read_yaml,
    "toml": read_toml,
    "xml": read_xml,
    "oml": read_oml,
}


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_output(path: Optional[str], text: str) -> None:
    if not text.endswith("\n"):
        text += "\n"
    if path is None or path == "-":
        sys.stdout.write(text)
    else:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)


def _encode_validation_result(result: ValidationResult, fmt: str) -> str:
    """Encode a ValidationResult as text/json/oml -- shared by every command
    whose result is an {ok, errors} shape (validate; later schema
    compatible-with/equivalent's boolean is a degenerate case of this)."""
    if fmt == "text":
        return str(result)
    payload: dict[str, Any] = {
        "ok": result.ok,
        "errors": [{"path": e.path, "message": e.message} for e in result.errors],
    }
    if fmt == "json":
        return _json.dumps(payload)
    if fmt == "oml":
        return doc(payload).to_oml()
    raise ValueError(f"unknown result format {fmt!r}")  # unreachable: argparse restricts choices


def _cmd_format(args: argparse.Namespace) -> int:
    node = read_oml(_read_input(args.input))
    _write_output(args.output, write_oml(node))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    node = _READERS[args.from_](_read_input(args.input))
    d = Doc(node)
    s = parse_schema(_read_input(args.schema))
    result = s.validate(d)
    print(_encode_validation_result(result, args.result_format))
    return 0 if result.ok else 1


def _cmd_infer(args: argparse.Namespace) -> int:
    reader = _READERS[args.from_]
    docs = [Doc(reader(_read_input(p))) for p in args.input]
    s = infer(docs)
    _write_output(args.output, to_dsl(s))
    return 0


def _cmd_schema_format(args: argparse.Namespace) -> int:
    s = parse_schema(_read_input(args.schema_file))
    _write_output(args.output, to_dsl(s))
    return 0


def _cmd_schema_normalize(args: argparse.Namespace) -> int:
    s = parse_schema(_read_input(args.schema_file))
    _write_output(args.output, to_dsl(s.normalize()))
    return 0


def _encode_bool_result(key: str, value: bool, fmt: str) -> str:
    """Encode a single boolean result -- shared by schema compatible-with
    and equivalent."""
    if fmt == "text":
        return "true" if value else "false"
    if fmt == "json":
        return _json.dumps({key: value})
    if fmt == "oml":
        return doc({key: value}).to_oml()
    raise ValueError(f"unknown result format {fmt!r}")  # unreachable: argparse restricts choices


def _cmd_schema_compatible_with(args: argparse.Namespace) -> int:
    a = parse_schema(_read_input(args.a))
    b = parse_schema(_read_input(args.b))
    result = a.compatible_with(b)
    print(_encode_bool_result("compatible", result, args.result_format))
    return 0 if result else 1


def _cmd_schema_equivalent(args: argparse.Namespace) -> int:
    a = parse_schema(_read_input(args.a))
    b = parse_schema(_read_input(args.b))
    result = a.equivalent(b)
    print(_encode_bool_result("equivalent", result, args.result_format))
    return 0 if result else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omnist")
    subparsers = parser.add_subparsers(dest="command", required=True)

    format_p = subparsers.add_parser(
        "format", help="canonicalize an OML document (the only format with no other tool for this)")
    format_p.add_argument("input", help="OML file, or - for stdin")
    format_p.add_argument("-o", "--output", help="output file; omit for stdout")
    format_p.set_defaults(func=_cmd_format)

    validate_p = subparsers.add_parser(
        "validate", help="check a document against a schema (no schema-directed upgrading)")
    validate_p.add_argument("input", help="document file, or - for stdin")
    validate_p.add_argument("--from", dest="from_", required=True, choices=FMT_CHOICES)
    validate_p.add_argument("--schema", required=True, help="OSD schema file")
    validate_p.add_argument(
        "--result-format", choices=RESULT_FORMAT_CHOICES, default="text")
    validate_p.set_defaults(func=_cmd_validate)

    infer_p = subparsers.add_parser(
        "infer", help="draft a schema from example documents (all the same format)")
    infer_p.add_argument("input", nargs="+", help="document files, same format")
    infer_p.add_argument("--from", dest="from_", required=True, choices=FMT_CHOICES)
    infer_p.add_argument("-o", "--output", help="output file; omit for stdout")
    infer_p.set_defaults(func=_cmd_infer)

    schema_p = subparsers.add_parser("schema", help="operate on a Schema (OSD)")
    schema_sub = schema_p.add_subparsers(dest="schema_command", required=True)

    schema_format_p = schema_sub.add_parser(
        "format", help="canonicalize an OSD schema file (safe reformat only, no structural change)")
    schema_format_p.add_argument("schema_file", help="OSD file, or - for stdin")
    schema_format_p.add_argument("-o", "--output", help="output file; omit for stdout")
    schema_format_p.set_defaults(func=_cmd_schema_format)

    schema_normalize_p = schema_sub.add_parser(
        "normalize", help="simplify an OSD schema (may merge structurally-identical records)")
    schema_normalize_p.add_argument("schema_file", help="OSD file, or - for stdin")
    schema_normalize_p.add_argument("-o", "--output", help="output file; omit for stdout")
    schema_normalize_p.set_defaults(func=_cmd_schema_normalize)

    schema_compat_p = schema_sub.add_parser(
        "compatible-with", help="is every document `a` accepts also accepted by `b`")
    schema_compat_p.add_argument("a", help="OSD file, or - for stdin")
    schema_compat_p.add_argument("b", help="OSD file")
    schema_compat_p.add_argument(
        "--result-format", choices=RESULT_FORMAT_CHOICES, default="text")
    schema_compat_p.set_defaults(func=_cmd_schema_compatible_with)

    schema_equiv_p = schema_sub.add_parser(
        "equivalent", help="do `a` and `b` accept exactly the same documents")
    schema_equiv_p.add_argument("a", help="OSD file, or - for stdin")
    schema_equiv_p.add_argument("b", help="OSD file")
    schema_equiv_p.add_argument(
        "--result-format", choices=RESULT_FORMAT_CHOICES, default="text")
    schema_equiv_p.set_defaults(func=_cmd_schema_equivalent)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ParseError, SchemaError, WriteError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
