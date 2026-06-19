# Formats

Every format is a **codec** over the same Document, so transcoding is just *read
one, write another*. The readers and writers:

| Format | Read | Write | Needs |
|---|---|---|---|
| JSON | `read_json` | `write_json` | stdlib |
| YAML | `read_yaml` | `write_yaml` | `pyyaml` |
| TOML | `read_toml` | `write_toml` | stdlib `tomllib` (read) + `tomli_w` (write) |
| XML  | `read_xml`  | `write_xml`  | `defusedxml` (recommended) |

## The guarantee: lossless, or a clear error

A writer never produces something that silently loses your data. If a Document
can't be represented in the target format, you get a `WriteError` that says
where and why. So a conversion either preserves the data or fails loudly.

The formats differ only at the edges:

| | JSON | YAML | TOML | XML |
|---|---|---|---|---|
| `null` | ✅ | ✅ | ⚠️ (see below) | ⚠️ (see below) |
| typed scalars (int/number/bool) | ✅ | ✅ | ✅ | best-effort |
| native date/time/datetime | string | ✅ | ✅ | string |
| top-level array / scalar | ✅ | ✅ | ❌ (object only) | ❌ (object only) |

## `null` (Option C)

TOML and XML have no `null`. dataspec handles this predictably:

- a **null object field** is **omitted** when writing TOML/XML;
- a **null array item** or a **top-level null** raises `WriteError` (there's no
  way to represent it);
- pass `strict=True` to *also* raise on the omitted-field case, if you'd rather
  be told than have a field silently dropped.

```python
write_toml({"a": 1, "b": None})              # -> a = 1   (b omitted)
write_toml({"a": 1, "b": None}, strict=True) # -> WriteError
write_toml({"xs": [1, None]})                # -> WriteError (null in array)
```

Round-trip note: a `null` survives JSON↔YAML exactly, but once it crosses into
TOML/XML (as an omitted field) it comes back as a *missing* field. That single
`null → missing` normalisation is the only place a value-level loss can happen,
and it only happens going **into** a format that has no null.

## Temporal values

`datetime` / `date` / `time` are native in TOML and YAML and round-trip
faithfully there. JSON and XML have no temporal type, so they are written as
ISO-8601 **strings**. A schema can re-impose the type: a `date` field accepts
both a real date and an ISO date string, so JSON data still validates.

## YAML — core subset

YAML is read as its **JSON-compatible core**. Features outside a plain tree of
string-keyed maps are rejected with a `ParseError`: non-string keys and
recursive anchors/aliases. (Comments and presentation are ignored, as data.)

## XML — data-XML profile

XML is treated purely as a way to serialize tree data, not as markup:

- **elements only** — no attributes, no mixed content, no namespaces, no CDATA
  constructs (these raise `ParseError`, except namespaces which are stripped to
  local names);
- **repeated child names become a list**: `<r><item>1</item><item>2</item></r>`
  → `{"item": [1, 2]}`;
- order across different names is not significant;
- a top-level array has no element name, so `write_xml([...])` raises;
- `write_xml(data, root="name")` sets the wrapping root element name.

XML scalars are untyped text, so they're read back with **best-effort typing**
(`"30"` → `30`, `"true"` → `True`). This means `1` and `"1"` are
indistinguishable after an XML round-trip — inherent to XML, and the one place
XML differs from the typed formats.

## Security

The XML reader uses `defusedxml` when available to block the classic XML attacks
(external-entity injection, entity-expansion DoS). Install it for untrusted
input: `pip install defusedxml`.
