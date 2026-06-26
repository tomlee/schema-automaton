# CLI

The `omnist` command-line tool — a thin wrapper over the library described
throughout the rest of these docs; every command maps directly onto one or
two calls into the public `omnist` API. This page matches
[the CLI spec](design/cli-spec.md) exactly.

Every example below is real: it's run against the files under
[`examples/cli/`](https://github.com/omnist-dev/omnist/tree/master/examples/cli)
in this repo, and the output shown is the exact, verified output of running
it — see `tests/test_cli_examples.py`, which runs every one of these and
fails CI if the output ever drifts from what's shown here. Run them
yourself from the repo root.

## Commands

- [Version and help](#version-and-help)
- [`omnist format`](#omnist-format)
- [`omnist convert`](#omnist-convert)
- [`omnist check`](#omnist-check)
- [`omnist infer`](#omnist-infer)
- [`omnist validate`](#omnist-validate)
- [`omnist schema format`](#omnist-schema-format)
- [`omnist schema normalize`](#omnist-schema-normalize)
- [`omnist schema compatible-with`](#omnist-schema-compatible-with)
- [`omnist schema equivalent`](#omnist-schema-equivalent)

## Version and help

```sh
$ omnist --version
omnist 0.2.9
```

`--help` is available on the top-level command and every subcommand
(`omnist <command> --help`) — standard `argparse` behavior, nothing
omnist-specific:

```sh
$ omnist --help
usage: omnist [-h] [--version]
              {format,convert,check,validate,infer,schema} ...

One canonical data model for JSON, YAML, TOML, XML, and OML -- read, validate,
and write any of them. See docs/cli.md for the full command reference.

positional arguments:
  {format,convert,check,validate,infer,schema}
    format              canonicalize an OML document (the only format with no
                        other tool for this)
    convert             convert a document between formats (one in, one out)
    check               report what writing as --to would adjust, without ever
                        writing
    validate            check a document against a schema (no schema-directed
                        upgrading)
    infer               draft a schema from example documents (all the same
                        format)
    schema              operate on a Schema (OSD)

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
```

## `omnist format`

```
omnist format <input> [-o OUTPUT]
```

Canonicalizes an OML document — `read_oml` then `write_oml`. `<input>` is a
file path or `-` for stdin; `-o`/`--output` is a file path, or omit it for
stdout.

```sh
$ cat examples/cli/messy-person.oml
name:"Ann"
age:   30
$ omnist format examples/cli/messy-person.oml
name: "Ann"
age: 30
$ echo 'name:   "Ann"' | omnist format -
name: "Ann"
```

Malformed OML raises the same `ParseError` `read_oml` would, printed to
stderr as `error: ...`, exit code `2` — nothing written.

## `omnist convert`

```
omnist convert <input> --from FMT --to FMT [--schema FILE] [--strict] [--report] [--result-format text|json|oml] [-o OUTPUT]
```

`read_<from>(text, schema=...)` → `write_<to>(node, strict=, report=)`.
Reformats data across formats, optionally upgrading/validating it against
a schema on the way in (per the [deserialization guarantee](deserialization.md)).

`--from oml --to oml` is rejected (exit `2`, pointing at `omnist format`
instead) — that's the one same-format case with a real alternative.
Every *other* same-format pair (`json`→`json`, `yaml`→`yaml`, etc.) is
allowed through `convert`, since there's no replacement command for
those (other formats already have their own formatters elsewhere; this
CLI doesn't duplicate them).

If `--schema` is given and the input can't be made to conform,
`materialize` raises `ParseError` (every problem found, not just the
first) — printed to stderr, nothing written, exit `2`.

`--report` and `--strict` map directly to `write_<to>`'s own `report=`/
`strict=` parameters (no effect on `--to oml`, which never needs them —
OML is always exactly lossless):

- **`--report`** prints what got adjusted to **stderr** (`--result-format`,
  default `text`, controls the encoding — same `text`/`json`/`oml`
  convention as everywhere else) — the write still happens normally.
  `--result-format` without `--report` has no effect.
- **`--strict`** refuses to write at all if anything would need
  adjusting — exit `1` (a definite "no, not losslessly possible," grouped
  with `validate`/`compatible-with`'s `1`, not the usage/parse failures
  that exit `2`).

`convert` is one document in, one document out — no batch mode (the
library's `read_xml`/`write_xml` only support a single-rooted Document;
converting many files is a shell loop).

```sh
$ omnist convert examples/cli/person.json --from json --to oml
person: {
  name: "Ann"
  age: 30
}
```

The same person, read from XML this time, upgraded/validated against the
schema on the way in:

```sh
$ omnist convert examples/cli/person.xml --from xml --to oml --schema examples/cli/person.osd
person: {
  name: "Ann"
  age: 30
}
```

Through stdin/stdout:

```sh
$ cat examples/cli/person.toml | omnist convert - --from toml --to json
{"person": {"name": "Ann", "age": 30}}
```

`--report`/`--strict`, on a document TOML can't hold losslessly
(`examples/cli/lossy.json` is `{"name": "Ann", "age": null}`):

```sh
$ omnist convert examples/cli/lossy.json --from json --to toml --report
name = "Ann"
# stderr:
warning: $.age: null value dropped (TOML has no null)

$ omnist convert examples/cli/lossy.json --from json --to toml --strict
# exit 1, nothing written, stderr:
error: warning: $.age: null value dropped (TOML has no null)
```

## `omnist check`

```
omnist check <input> --from FMT --to FMT [--strict] [--result-format text|json|oml]
```

Reports what `write_<to>` would adjust (`check_json`/`check_yaml`/
`check_toml`/`check_xml`/`check_oml`) **without ever writing anything** —
`convert`'s dry-run counterpart, for asking the question without
producing (or risking producing) any output. Unlike `convert`,
`--from`/`--to` may be equal.

By default, `check` always exits `0` — it's purely informational.
`--strict` turns it into a CI gate: exit `0` if nothing would need
adjusting, `1` if anything would.

```sh
$ omnist check examples/cli/lossy.json --from json --to toml
warning: $.age: null value dropped (TOML has no null)

$ omnist check examples/cli/lossy.json --from json --to toml --strict
warning: $.age: null value dropped (TOML has no null)
# exit 1
```

## `omnist infer`

```
omnist infer <input>... --from FMT [-o OUTPUT]
```

All inputs must be the same format. Each is read as a `Doc`,
[`infer(docs)`](schema.md#operations-compare-and-infer) drafts a schema
from them, written out as OSD.

```sh
$ omnist infer examples/cli/sample1.json examples/cli/sample2.json --from json
record Root {
    "name": string,
    "age" [0,1]: integer,
}
root Root
```

(`sample1.json` is `{"name": "Ann"}`; `sample2.json` is `{"name": "Bo", "age": 30}` —
`age` is absent from the first sample, so `infer` drafts it as optional. This
is exactly the same `name`/`age` evolution shown in `schema compatible-with`
below, as data instead of as two schema versions.)

## `omnist validate`

```
omnist validate <input> --from FMT --schema FILE [--result-format text|json|oml]
```

Reads `<input>` as `FMT` (`json`/`yaml`/`toml`/`xml`/`oml`) **without**
schema-directed upgrading — the same lenient parse a plain `read_<from>`
call would produce — then runs `Schema.validate` against the OSD file
given by `--schema`. This mirrors the library's own validation/
deserialization split: validation only ever *checks* a value already in
the document; it never converts anything (see [Schema-directed
deserialization](deserialization.md) for the upgrading side of that
split, which is what `convert --schema` does instead).

`--result-format` (default `text`) controls the printed result:

- `text` — `ValidationResult`'s own `"invalid:\n  at $.path: message"`
  formatting, or `valid`.
- `json` — `{"ok": bool, "errors": [{"path": str, "message": str}, ...]}`.
- `oml` — the same `{ok, errors}` shape, OML-encoded.

```sh
$ omnist validate examples/cli/person.json --from json --schema examples/cli/person.osd
valid
```

A rejected person (`invalid-person.json` has `"age": "thirty"` — the wrong
type — and no `name` at all):

```sh
$ omnist validate examples/cli/invalid-person.json --from json --schema examples/cli/person.osd
invalid:
  at $.person.age: expected integer, got string ('thirty')
  at $.person: field 'name' occurs 0 time(s), expected exactly 1
# exit 1

$ omnist validate examples/cli/invalid-person.json --from json --schema examples/cli/person.osd --result-format json
{"ok": false, "errors": [{"path": "$.person.age", "message": "expected integer, got string ('thirty')"}, {"path": "$.person", "message": "field 'name' occurs 0 time(s), expected exactly 1"}]}
```

Exit `0` if valid, `1` if invalid, `2` on a read/parse error (malformed
input or schema, printed to stderr as `error: ...`).

## `omnist schema format`

```
omnist schema format <schema-file> [-o OUTPUT]
```

Canonicalizes an OSD ([Omnist Schema Definition](schema.md)) file —
`parse_schema` then `to_dsl`. Same records, same names, just canonical
whitespace/field order; it never changes a schema's structure (contrast
[`Schema.normalize()`](schema.md#operations-compare-and-infer), which can
merge structurally-identical records).

```sh
$ cat examples/cli/messy-person.osd
record Person{"name":string,"age" [0,1]:integer}
root Person
$ omnist schema format examples/cli/messy-person.osd
record Person {
    "name": string,
    "age" [0,1]: integer,
}
root Person
```

Malformed OSD raises `SchemaError`, printed to stderr as `error: ...`,
exit code `2`.

## `omnist schema normalize`

```
omnist schema normalize <schema-file> [-o OUTPUT]
```

`Schema.normalize()`, written back out as OSD — unlike `schema format`,
this *can* change a schema's structure (merging separately-named records
that are structurally identical). `duplicate-records.osd` defines `Employee`
and `Customer` with the exact same shape (just a `name`); normalizing merges
them into one:

```sh
$ cat examples/cli/duplicate-records.osd
record Employee { "name": string }
record Customer { "name": string }
record Company  { "employee": Employee, "customer": Customer }
root Company
$ omnist schema normalize examples/cli/duplicate-records.osd
record Customer {
    "name": string,
}
record Company {
    "employee": Customer,
    "customer": Customer,
}
root Company
```

## `omnist schema compatible-with`

```
omnist schema compatible-with <a> <b> [--result-format text|json|oml]
```

`a.compatible_with(b)` — true if every Document `a` accepts, `b` also
accepts (`b` is backward-compatible with `a`). `--result-format` (default
`text`) prints `true`/`false`, `{"compatible": bool}` (`json`), or the
same shape OML-encoded. Exit `0` if true, `1` if false, `2` on a parse
error.

```sh
$ cat examples/cli/v1.osd
record Person { "name": string }
root Person
$ cat examples/cli/v2.osd
record Person { "name": string, "age" [0,1]: integer }
root Person
$ omnist schema compatible-with examples/cli/v1.osd examples/cli/v2.osd
true
```

## `omnist schema equivalent`

```
omnist schema equivalent <a> <b> [--result-format text|json|oml]
```

`a.equivalent(b)` — true if both accept exactly the same Documents. Same
output/exit convention as `compatible-with`. `v1.osd` and `v2.osd` above
are compatible but not equivalent (`v2` accepts a document `v1` doesn't):

```sh
$ omnist schema equivalent examples/cli/v1.osd examples/cli/v2.osd
false
# exit 1
```
