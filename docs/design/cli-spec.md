# CLI Spec

> Status: **design only** — nothing under `omnist/cli.py` exists yet. This
> document specifies the command surface before implementation, the same
> way the [model spec](model.md) and the [grammars](schema-osd-grammar.md)
> precede their implementations.

## 1. Command tree

```
omnist format     <input>                          [-o OUTPUT]
omnist convert    <input>   --from FMT --to FMT [--schema FILE] [--strict] [--report] [--result-format text|json|oml] [-o OUTPUT]
omnist validate   <input>   --from FMT --schema FILE [--result-format text|json|oml]
omnist infer      <input>...  --from FMT             [-o OUTPUT]
omnist check      <input>   --from FMT --to FMT [--strict] [--result-format text|json|oml]

omnist schema format           <schema-file>  [-o OUTPUT]
omnist schema normalize        <schema-file>  [-o OUTPUT]
omnist schema compatible-with  <a> <b>        [--result-format text|json|oml]
omnist schema equivalent       <a> <b>        [--result-format text|json|oml]
```

`FMT` is one of `json|yaml|toml|xml|oml`. A schema file is always OSD
(Omnist Schema Definition; `parse_schema`/`to_dsl`) — schema commands take
no `--from`/`--to`.

## 2. Format handling

- `<input>`/`<a>`/`<b>` may be a file path or `-` for stdin; `-o`/
  `--output` may be a file path or omitted for stdout.
- `--from` is always required wherever it appears, file or stream alike —
  no extension-based inference.
- `--to` is always required on `convert`/`check` — no defaulting.
- `format`/`schema format`/`schema normalize`/`schema compatible-with`/
  `schema equivalent` take no `--from`/`--to`: each reads/writes exactly
  one format (OML or OSD).
- Schema files conventionally use `.osd`; not enforced.

## 3. Commands

### `omnist format <input> [-o OUTPUT]`

`read_oml(text)` → `write_oml(node)`. OML only; no flags beyond `-o`.

```sh
omnist format messy.oml -o clean.oml
```

### `omnist convert <input> --from FMT --to FMT [--schema FILE] [--strict] [--report] [--result-format text|json|oml] [-o OUTPUT]`

`read_<from>(text, schema=...)` → `write_<to>(node, strict=, report=)`.

- `--schema FILE`: schema-directed deserialization on read. If the input
  can't be made to conform, raises `ParseError` (every problem found),
  nothing written, exit `2`.
- `--report`: prints what `write_<to>` adjusted to stderr (encoding per
  `--result-format`, default `text`); the write still happens.
- `--strict`: refuses to write at all if anything would need adjusting —
  exit `1`.
- `--from oml --to oml` is rejected (exit `2`, use `format`). Every other
  same-format pair (`json`→`json`, etc.) is allowed.
- One document in, one document out; no batch mode.

```sh
omnist convert order.json --from json --to oml
omnist convert order.xml --from xml --to oml --schema order.osd -o order.oml
omnist convert data.json --from json --to toml --report -o data.toml
omnist convert data.json --from json --to toml --strict -o data.toml
```

### `omnist validate <input> --from FMT --schema FILE [--result-format text|json|oml]`

Reads without schema-directed upgrading, then `Schema.validate`.

- `text` (default): `ValidationResult`'s `"invalid:\n  at $.path: message"` (or `valid`).
- `json`: `{"ok": bool, "errors": [{"path": str, "message": str}, ...]}`.
- `oml`: same shape, OML-encoded.

Exit `0` valid, `1` invalid, `2` read/parse error.

```sh
omnist validate order.json --from json --schema order.osd
omnist validate order.xml --from xml --schema order.osd --result-format json
```

### `omnist infer <input>... --from FMT [-o OUTPUT]`

All inputs same format; `infer(docs)`, writes the result as OSD.

```sh
omnist infer samples/*.json --from json -o inferred.osd
```

### `omnist check <input> --from FMT --to FMT [--strict] [--result-format text|json|oml]`

`check_<to>` — reports what `write_<to>` would adjust, never writes
anything. `--from`/`--to` may be equal (unlike `convert`).

- Default: exit `0` regardless of result; purely informational.
- `--strict`: exit `0` if nothing would need adjusting, `1` otherwise.

```sh
omnist check data.json --from json --to toml
omnist check data.json --from json --to toml --strict
```

### `omnist schema format <schema-file> [-o OUTPUT]`

`parse_schema` → `to_dsl`. Safe reformat only — same records, same names,
canonical whitespace/field order. No structural change (contrast
`normalize`).

```sh
omnist schema format messy.osd -o clean.osd
```

### `omnist schema normalize <schema-file> [-o OUTPUT]`

`Schema.normalize()`, written back as OSD. May merge structurally-
identical records — a structural change, unlike `schema format`.

### `omnist schema compatible-with <a> <b> [--result-format text|json|oml]`

`a.compatible_with(b)`. `text`: `true`/`false`. `json`:
`{"compatible": bool}`. `oml`: `compatible: true`/`compatible: false`.
Exit `0`/`1`.

```sh
omnist schema compatible-with v1.osd v2.osd
```

### `omnist schema equivalent <a> <b> [--result-format text|json|oml]`

`a.equivalent(b)`. Same output/exit convention as `compatible-with`.

## 4. Conventions

| | |
|---|---|
| Exit `0` | success / valid / compatible / equivalent / losslessly-writable |
| Exit `1` | a definite "no" — invalid, incompatible, not equivalent, or (`--strict`) not losslessly writable |
| Exit `2` | usage error, parse error, missing file, unsupported format, schema non-conformance |
| `--result-format` | `text` (default) / `json` / `oml` — encodes a command's own result, not Document/Schema content; `convert` only uses it together with `--report` |
| `-`/`-o` | stdin/stdout |

## 5. Non-goals

- No format auto-detection (content or extension).
- No batch/multi-document conversion.
- No alternate Schema serialization (e.g. JSON-Schema-shaped import/export).
- No `schema diff` (structural diff beyond the boolean `compatible-with`/`equivalent`).
- No schema editing (only whole-schema read/transform).

## 6. Packaging

```toml
[project.scripts]
omnist = "omnist.cli:main"
```

`omnist/cli.py` — `argparse`-based, public `omnist` API only. No new
required dependency.
