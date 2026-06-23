# XML

A deliberately narrow **data-XML** profile: elements only, used to carry the
same Documents as the other formats. Install `pip install defusedxml` so
parsing is hardened against entity-expansion / XXE attacks (without it, the
standard-library parser is used and `read_xml` emits an `UnsafeXMLWarning`).

```python
from omnist import read_xml, Doc

d = Doc(read_xml("<order><id>A1</id>"
                 "<item><sku>W</sku></item><item><sku>G</sku></item></order>"))
d.to_json()    # '{"order": {"id": "A1", "item": [{"sku": "W"}, {"sku": "G"}]}}'
```

## How it maps

- An element with child elements becomes a node; each child tag is an edge label.
- **Repeated elements are a repeated label** — `<item/><item/>` is the label
  `item` twice, i.e. an array, exactly like JSON `"item": [{…}, {…}]`.
- A leaf element is a scalar — its text content.

## Single document element

XML has exactly **one** top-level element, so an XML Document always has a
**single top-level edge** (the document element's tag). That's why a Document
meant to round-trip through XML is *single-rooted* — wrap your data under one
top-level key:

```python
read_xml("<order>…</order>")          # -> [("order", […])]
```

To share a Document with JSON/YAML/TOML, give them a matching single top-level
key (`{"order": {…}}`). Writing requires a single top-level edge — a Document
with several top-level edges has no single XML document form and raises.

## Interleaving is preserved

Because the Document is an *ordered* edge list, XML's interleaved repeats
survive on read — `<m/><x/><m/>` reads as `[(m,…), (x,…), (m,…)]`, the one thing
a dict-with-arrays can't represent. (Projecting to JSON groups the `m`s, since
JSON can't interleave.)

## Notes

- Element **text is untyped**, so scalars are recovered with best-effort typing
  on read: `<n>30</n>` reads as the integer `30`, `<ok>true</ok>` as `True`. If
  exact types matter, validate against a schema or prefer JSON/TOML.
- **Not supported** (outside the data-XML profile): attributes, mixed text and
  elements, and CDATA. A namespace prefix is stripped (`<n:a>` reads as `a`).
- A key that isn't a legal XML element name is sanitized on write (e.g.
  `"a b"` → `<a_b>`, reported as `key.sanitized`), and a date/time value is
  written as text (`temporal.stringified`). See
  [adjustment reports](../api.md#adjustment-reports-lossy-writes) to inspect
  these, or `strict=True` to raise instead of adjusting.
- **An empty internal node (zero edges, `[]`) is indistinguishable from an
  empty-string leaf (`""`)** once written: both serialize to `<tag />`, and
  `read_xml` always reconstructs the empty-string leaf. Writing `[]` is
  reported as `shape.empty_ambiguous` so you know ahead of time that it won't
  round-trip; writing `""` round-trips fine and is not flagged.
- **A string containing a character XML 1.0 cannot represent** (most C0
  control characters -- everything below U+0020 except tab/LF/CR -- or a
  UTF-16 surrogate) would otherwise produce text that isn't well-formed XML,
  so `write_xml` replaces each such character with U+FFFD (the standard
  replacement character) and reports `string.illegal_xml_char` with
  `"error"` severity -- `strict=True` raises instead of silently substituting.
- **A string containing `\r`** is legal XML, but XML mandates line-ending
  normalization on parse (`\r` and `\r\n` both become `\n`), so it doesn't
  round-trip byte-for-byte. `write_xml` leaves `\r` as-is (no substitution
  needed) and reports it as `string.cr_normalized` so you know ahead of time
  the read-back value will differ.
