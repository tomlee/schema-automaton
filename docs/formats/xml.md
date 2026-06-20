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

read_xml("<person><name>Ann</name><age>30</age></person>")
# {'person': {'name': 'Ann', 'age': 30}}

print(write_xml({"person": {"name": "Ann", "age": 30}}))
# <person>
#   <name>Ann</name>
#   <age>30</age>
# </person>
```

## XML is single-rooted

An XML document has exactly **one** top-level (document) element. In the data
tree, that document element is the single child of the tree's own (anonymous)
root, connected by an edge labeled with its tag — so the tag is a real key,
not a discardable wrapper.

This means `read_xml`/`write_xml` work with a Document that has exactly **one
top-level key**, whose value isn't itself a list: `{"person": {...}}` reads
from and writes to `<person>...</person>` losslessly. A Document with more
than one top-level key (`{"x": 1, "y": 2}`), or whose single key holds a list
(`{"x": [1, 2]}`), has no representation as *one* XML document — it would need
two `<x>` elements side by side, which isn't valid XML — so `write_xml` raises
`WriteError` regardless of `strict`. (TOML's "wrap the leftover under a key"
trick doesn't apply here: inventing a wrapper node the data never had would
mean the round-tripped tree no longer matches the schema the original was
written for.)

For a Document that isn't single-rooted, use `write_xml_documents`/
`read_xml_documents` instead — they treat the Document's anonymous root as a
**forest**: one XML document per top-level key, with a list value producing
one repeated-tag document per item.

```python
from dataspec import write_xml_documents, read_xml_documents

write_xml_documents({"x": 1, "y": {"z": 2}})
# ['<x>1</x>', '<y>\n  <z>2</z>\n</y>\n']

write_xml_documents({"x": [1, 2, 3]})
# ['<x>1</x>', '<x>2</x>', '<x>3</x>']

read_xml_documents(['<x>1</x>', '<x>2</x>', '<x>3</x>'])
# {'x': [1, 2, 3]}
```

`write_xml_documents` requires a top-level `dict` (it needs a tag for every
document); a top-level scalar or list has no top-level key to use and raises
`WriteError`.

## How it maps

- An **element with child elements** is an object; each child tag is a field.
- **Repeated child tags** become an array, in document order:

  ```python
  read_xml("<r><item>1</item><item>2</item><other>x</other></r>")
  # {'r': {'item': [1, 2], 'other': 'x'}}
  ```

- A **leaf element** is a scalar — its text content.

## What's supported

- Objects and (named) arrays nested to any depth.
- Scalars as element text.
- The same `null` handling as TOML: a `null` field is omitted (`warning`); a
  `null` array item is dropped (`error`). `strict=True` raises on either.

## Limitations

Two kinds of limitation. **On read**, input outside the data-XML profile is
rejected (or, for namespaces, normalized). **On write**, shapes XML can't hold
natively are adjusted and reported — lenient by default, like the other
formats; use `report=`, `check_xml(doc)`, or `strict=True` to see or forbid
them. One exception: a Document that isn't single-rooted has no fallback
shape at all, so it always raises (see above), not just under `strict`.

| Limitation | When | Behaviour |
|---|---|---|
| Attributes (`<a x="1">`) | read | `ParseError` |
| Mixed content (text *and* elements together) | read | `ParseError` |
| Namespaces | read | prefix **stripped** (`<n:a>` reads as `a`) |
| Document isn't single-rooted (multiple top-level keys, or a top-level list/scalar) | write | `WriteError`, always — use `write_xml_documents` |
| Nested / bare arrays (array of arrays) | write | wrapped in `<item>` elements, reported as `error` |
| Object key that isn't a legal XML name | write | sanitized (e.g. `"a b"` → `<a_b>`), reported as a warning |
| Two distinct keys that sanitize to the same name | write | merge into one list on read; reported as `key.collision`, **error** |
| Date / time | write | written as text, reported (reads back as a string) |
| A string that looks like a number/bool/`null` (e.g. `"true"`, `"123"`) | write | reads back as that type, not a string; reported as `string.ambiguous` |
| A string containing `\r` (e.g. CRLF line endings) | write | the XML spec normalizes `\r\n`/`\r` to `\n` on read; reported as `string.line_ending_normalized` |
| Empty object `{}` or empty array `[]` as a value | write | reads back as `""` (an empty string); reported as `container.empty.ambiguous` |
| A string containing a character with no legal XML representation (most C0 controls, surrogates) | write | the character is removed; reported as `string.illegal_xml_char`, **error** |

A legal XML name allows letters, digits (not as the first character),
underscore, `.`, and `-` — so a key like `"a.b"` is written **unchanged**,
with no `key.sanitized` adjustment, even though a literal dot is
syntactically special in TOML (it denotes a nested table there). "Special" in
one format's grammar doesn't mean special in another's; each format only
sanitizes what's actually illegal in *its own* syntax.

If your XML uses attributes, transform it first (for example with XSLT) into an
attribute-free shape, then read that.

Because XML element text is **untyped**, scalar types are recovered with
best-effort guessing on read:

```python
read_xml("<r><n>30</n><ok>true</ok><s>x</s></r>")
# {'r': {'n': 30, 'ok': True, 's': 'x'}}
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
A string containing a character with no legal XML representation at all
(most C0 control characters, surrogates) has that character **removed**,
reported as `string.illegal_xml_char` — the one `error`-severity string
adjustment, since the alternative isn't a different reading on the other
end, it's output that doesn't parse as XML at all. `strict=True` rejects
all four of the cases above.

## Round-trip behaviour

A single-rooted Document — objects, named arrays, and scalars under one
top-level key — round-trips through XML exactly, **including the document
element's name**:

```python
data = {"rec": {"name": "Ann", "age": 30, "tags": ["x", "y"],
                "addr": {"city": "London"}}}
read_xml(write_xml(data)) == data      # True
```

This also means the name survives a detour through another format, since it's
an ordinary key like any other:

```python
from dataspec import read_xml, write_xml, read_json, write_json

original = "<k><name>Ann</name></k>"
roundtrip = write_xml(read_json(write_json(read_xml(original))))
roundtrip                              # '<k>\n  <name>Ann</name>\n</k>\n'
read_xml(roundtrip) == read_xml(original)   # True -- same data, "k" preserved
```

The caveats above are the exceptions: numeric-looking strings are retyped as
numbers, and dates return as strings.
