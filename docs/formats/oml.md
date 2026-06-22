# OML

OML (Omnist Markup Language) is omnist's **own** format — the only one
designed to hold a Document exactly, with no adjustments. Where JSON/YAML/
TOML/XML each give up something (TOML has no `null`, JSON has no native
dates, XML forces a single root), OML maps onto the Document model 1:1: all
seven scalars, `null`, repeated labels, interleaving, and multiple top-level
edges are all native — `check_oml` is always an empty report.

```python
from omnist import read_oml, write_oml, Doc

d = Doc.from_oml('name: "Ann"\ntags: "x"\ntags: "y"\n')
d.to_grouped()                     # {'name': 'Ann', 'tags': ['x', 'y']}
d.to_oml()
```

## Shape

A document is zero or more `label: value` edges, one per line (or
`;`-separated on one line). A repeated label is how an array appears — same
as every other format. Values nest with `{ }`:

```oml
venue: {
    name: "Strange Loop"
    building: {
        address: { street: "123 Main St", city: "St. Louis", country: "US" }
        room: "Ballroom A"
    }
}
session: {
    title: "Schema Compatibility, Revisited"
    speaker: {
        name: "Ada Lovelace"
        bio: """
Works on data models and provenance.
Quote: "Hopper said it best".
Path: C:\\talks\\ada\\slides.key
"""
    }
    note: "Recording starts five minutes late."
    note: 'Slides posted after the talk -- path on the laptop: C:\talks\ada\slides.key'
    start: 2024-09-18T14:00:00
    duration: 50
    tags: "schemas"
    tags: "compatibility"
}
attendee_count: 312
virtual: false
```

This reads straight into the Document `[(venue, [...]), (session, [...]),
(attendee_count, 312), (virtual, False)]` — `session.note` is a repeated
label (two notes, in order), `session.tags` likewise, and `session.start`
comes back as a real `datetime.datetime`, not a string.

## Scalars are typed by their spelling, not a tag

There's no type annotation — the literal's shape says what it is:

| Spelling | Scalar |
|---|---|
| `"text"` | string |
| `42` / `-42` | integer |
| `3.14` / `1e10` / `nan` / `inf` / `-inf` | number |
| `true` / `false` | boolean |
| `2024-01-01` | date |
| `12:30:00` | time |
| `2024-01-01T12:30:00` | datetime |
| `null` | null |

Bare words are never strings — `name: Ann` is a syntax error; quote it:
`name: "Ann"`.

## Strings: escaping, raw, and multiline

A normal string escapes the usual set: `\"`, `\\`, `\n`, `\t`, `\r`, `\b`,
`\f`, and `\uXXXX` (a surrogate pair of two `\uXXXX` escapes denotes one
astral code point, e.g. U+1F600). The canonical writer only ever emits this
minimal form — `\"` and `\\` plus literal Unicode, nothing more.

Two extra spellings (read-only — `write_oml` never produces them, so reading
one and writing it back changes layout, never meaning):

- **Raw** `'…'` — no escape processing at all; ideal for paths/regexes:
  `'C:\talks\ada\slides.key'`. The one limitation: it can't contain `'`
  (there's no escape for it inside raw strings) — use the quoted or
  multiline form instead.
- **Multiline** `"""…"""` — may contain literal newlines (a newline right
  after the opening `"""` is stripped, so the first content line doesn't
  have to share the delimiter's line); ordinary escapes still work inside.
  Because the terminator is three quotes, a lone or double `"` is just
  content — only a run of three needs `\"""`.

Newlines *inside* a multiline string are never confused with the structural
line separator: the tokenizer reads `"""…"""` as one token from open to
close (the same way a string can contain `#` without it becoming a
comment), so only a newline *outside* any token separates one edge from the
next.

## Separators

Edges are separated by one or more newlines and/or `;`. There's no comma —
OML has no array literal, so nothing invites one. `;` is for one-line
("inline") style: `{ a: 1; b: 2 }`.

## Errors, not silent surprises

A few things that look almost-valid are deliberate hard errors, not lenient
parses:

```python
read_oml("a: 1 b: 2")          # ParseError -- no separator between edges
read_oml('{ a: 1 }\nb: 2')      # ParseError -- braces must wrap the WHOLE document
read_oml("true: 1")             # ParseError -- true/false/null can't be bare labels
read_oml('"true": 1')           # fine -- quoting always works
```

There's also a digit-count limit on bare integers (4300 digits, matching
CPython's own default `sys.get_int_max_str_digits()`) and a nesting-depth
limit of 200, matching the Document model's own bound — both raise
`ParseError` rather than letting a pathological input hang or crash the
process.

## Schema-directed read and validation

Like every other format, `read_oml(text, schema=...)` upgrades leaves to
match a schema, and the result validates the same way:

```python
from omnist import parse_schema, Doc

s = parse_schema('record R { "d": date, "n": number }\nroot R')
read_oml('d: "2024-01-01"\nn: 3', schema=s)
# [('d', datetime.date(2024, 1, 1)), ('n', 3.0)]
```

## Notes

- OML is the one format with no `WriteReport` adjustments: `check_oml`
  always returns an empty report, because every Document shape (all seven
  scalars, `null`, repeats, interleaving, multiple top-level edges) maps
  onto OML without loss.
- The canonical writer always emits `LF` newlines, 2-space indentation, and
  the minimal string-escape form — same input always produces the same
  output (useful for diffing/snapshotting).
- Not yet implemented: a few further OML-Extended conveniences from the
  design draft — digit separators (`1_000_000`), non-decimal integer
  literals (`0x1F`, `0o17`, `0b1010`), the pair-free astral escape
  `\u{1F600}`, a lenient `date time` (space) datetime separator, and a
  trailing `Z` UTC-zone marker. None of these affect what OML can
  *represent* (every Document already round-trips); they're optional input
  sugar for later.
