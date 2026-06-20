# XML

XML can express far more than tree-shaped data — attributes, mixed text and
markup, namespaces, processing instructions. dataspec supports a deliberately
narrow **data-XML** profile: elements only, used purely to carry the same
Documents as the other formats.

Install `pip install defusedxml` so parsing is hardened against entity-expansion
and external-entity attacks. If it isn't installed, the standard library is used
as a fallback — `read_xml` emits an `UnsafeXMLWarning` each time this happens
(Python's default warning filter shows it once per call site, not on every
call), since the stdlib parser has no protection against those attacks on
untrusted input. Suppress it only if you've deliberately decided it doesn't
apply, e.g. `warnings.filterwarnings("ignore", category=UnsafeXMLWarning)`.

```python
from dataspec import read_xml, write_xml

read_xml("<r><name>Ann</name><age>30</age></r>")
# {'name': 'Ann', 'age': 30}

print(write_xml({"name": "Ann", "age": 30}, root="person"))
# <person>
#   <name>Ann</name>
#   <age>30</age>
# </person>
```

## How it maps

- An **element with child elements** is an object; each child tag is a field.
- **Repeated child tags** become an array, in document order:

  ```python
  read_xml("<r><item>1</item><item>2</item><other>x</other></r>")
  # {'item': [1, 2], 'other': 'x'}
  ```

- A **leaf element** is a scalar — its text content.
- `write_xml` wraps the document in a root element; set its name with
  `root="..."` (default `"root"`).

## What's supported

- Objects and (named) arrays nested to any depth.
- Scalars as element text.
- The same `null` handling as TOML: a `null` field is omitted (`warning`); a
  `null` array item is dropped (`error`); a top-level `null` becomes an empty
  element (`error`). `strict=True` raises on any of these.

## Limitations

Two kinds of limitation. **On read**, input outside the data-XML profile is
rejected (or, for namespaces, normalized). **On write**, shapes XML can't hold
natively are adjusted and reported — lenient by default, like the other formats;
use `report=`, `check_xml(doc)`, or `strict=True` to see or forbid them.

| Limitation | When | Behaviour |
|---|---|---|
| Attributes (`<a x="1">`) | read | `ParseError` |
| Mixed content (text *and* elements together) | read | `ParseError` |
| Namespaces | read | prefix **stripped** (`<n:a>` reads as `a`) |
| Top-level array/scalar | write | wrapped under `wrap_key` (default `"value"`), reported |
| Nested / bare arrays (array of arrays) | write | wrapped in `<item>` elements, reported as `error` |
| Object key that isn't a legal XML name | write | sanitized (e.g. `"a b"` → `<a_b>`), reported as a warning |
| Two distinct keys that sanitize to the same name | write | merge into one list on read; reported as `key.collision`, **error** |
| Date / time | write | written as text, reported (reads back as a string) |
| A string that looks like a number/bool/`null` (e.g. `"true"`, `"123"`) | write | reads back as that type, not a string; reported as `string.ambiguous` |
| A string containing `\r` (e.g. CRLF line endings) | write | the XML spec normalizes `\r\n`/`\r` to `\n` on read; reported as `string.line_ending_normalized` |
| Empty object `{}` or empty array `[]` as a value | write | reads back as `""` (an empty string); reported as `container.empty.ambiguous` |

If your XML uses attributes, transform it first (for example with XSLT) into an
attribute-free shape, then read that.

Because XML element text is **untyped**, scalar types are recovered with
best-effort guessing on read:

```python
read_xml("<r><n>30</n><ok>true</ok><s>x</s></r>")
# {'n': 30, 'ok': True, 's': 'x'}
```

This means a string that looks like a number (`"30"`) comes back as a number.
Dates come back as plain strings (they aren't guessed). When exact scalar types
matter, validate against a schema after reading, or prefer JSON/TOML.

Because the writer knows this in advance, writing a string that looks like a
number, boolean, or `null` is reported (`string.ambiguous`) rather than left
for you to discover on the next read — same with an empty object or array,
which has no representation in XML at all (a self-closing element is the only
way to write "nothing here," so `{}`, `[]`, and `""` are indistinguishable on
read; writing either of the first two is reported as `container.empty.ambiguous`).
A string containing `\r` (a Windows-style `\r\n` line ending, for instance) is
also reported (`string.line_ending_normalized`): the XML spec itself mandates
normalizing `\r\n`/`\r` to `\n` on read, regardless of parser, so this isn't
something dataspec could preserve even with attributes or a different parser.
`strict=True` rejects all three.

## Round-trip behaviour

A Document made of objects, named arrays, and scalars round-trips through XML:

```python
data = {"name": "Ann", "age": 30, "tags": ["x", "y"], "addr": {"city": "London"}}
read_xml(write_xml(data, root="rec")) == data      # True
```

The caveats above are the exceptions: numeric-looking strings are retyped as
numbers, and dates return as strings.
