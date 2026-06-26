# CLI

The `omnist` command-line tool — a thin wrapper over the library described
throughout the rest of these docs; every command maps directly onto one or
two calls into the public `omnist` API. This page documents exactly what's
implemented today; the full planned command surface is
[the CLI spec](design/cli-spec.md).

## `omnist format`

```
omnist format <input> [-o OUTPUT]
```

Canonicalizes an OML document — `read_oml` then `write_oml`. `<input>` is a
file path or `-` for stdin; `-o`/`--output` is a file path, or omit it for
stdout.

```sh
omnist format messy.oml -o clean.oml
echo 'a:   1' | omnist format -
# a: 1
```

Malformed OML raises the same `ParseError` `read_oml` would, printed to
stderr as `error: ...`, exit code `2` — nothing written.

## `omnist infer`

```
omnist infer <input>... --from FMT [-o OUTPUT]
```

All inputs must be the same format. Each is read as a `Doc`,
[`infer(docs)`](schema.md#operations-compare-and-infer) drafts a schema
from them, written out as OSD.

```sh
omnist infer samples/*.json --from json -o inferred.osd
```

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
omnist validate order.json --from json --schema order.osd
omnist validate order.json --from json --schema order.osd --result-format json
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
omnist schema format messy.osd -o clean.osd
```

Malformed OSD raises `SchemaError`, printed to stderr as `error: ...`,
exit code `2`.

## `omnist schema normalize`

```
omnist schema normalize <schema-file> [-o OUTPUT]
```

`Schema.normalize()`, written back out as OSD — unlike `schema format`,
this *can* change a schema's structure (merging separately-named records
that are structurally identical).

```sh
omnist schema normalize messy.osd -o normalized.osd
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
omnist schema compatible-with v1.osd v2.osd && echo "safe to ship v2"
```

## `omnist schema equivalent`

```
omnist schema equivalent <a> <b> [--result-format text|json|oml]
```

`a.equivalent(b)` — true if both accept exactly the same Documents. Same
output/exit convention as `compatible-with`.
