# Documents (the `Doc` API)

A **Document** is a tree of objects, arrays, and scalars. `Doc` is the guarded
data structure you use to build, navigate, edit, and serialize one. Think of it
as a format-neutral DOM: the same `Doc` can be written to JSON, YAML, TOML, or
XML, and reading any of those gives you a `Doc`.

The point of going through `Doc` rather than poking at raw dicts and lists is
**safety**: every value you put in is checked against the Document model and
copied in, so the structure can never drift into something unserializable.

Every example on this page builds the same document — a user profile, three
layers deep (object → object → object):

```python
{"name": "Ann", "address": {"city": "London", "geo": {"lat": 51.5, "lon": -0.1}}}
```

## Creating a Doc

There's no single "right" way to get one — pick whichever starting point
matches what you have.

**From a Python value:**

```python
from dataspec import doc

d = doc({"name": "Ann", "address": {"city": "London", "geo": {"lat": 51.5, "lon": -0.1}}})
```

**From a format string** — one `from_*` per built-in format, plus a generic
form that also works for plugin formats ([Formats](formats/overview.md)):

```python
from dataspec import Doc

Doc.from_json('{"name": "Ann", "address": {"city": "London", "geo": {"lat": 51.5, "lon": -0.1}}}')

Doc.from_yaml("""
name: Ann
address:
  city: London
  geo:
    lat: 51.5
    lon: -0.1
""")

Doc.from_toml("""
name = "Ann"

[address]
city = "London"

[address.geo]
lat = 51.5
lon = -0.1
""")

Doc.from_xml("""
<root>
  <name>Ann</name>
  <address>
    <city>London</city>
    <geo>
      <lat>51.5</lat>
      <lon>-0.1</lon>
    </geo>
  </address>
</root>
""")

Doc.from_format("json", text)   # generic: name the format by string
```

All four produce the identical `Doc`. The XML wrapper element name (`root`
above) is arbitrary — `from_xml` doesn't care what it's called, it just reads
the outer element's children; use whatever name fits your data (e.g.
`Doc.from_xml(text)` paired with `d.to_xml(root="profile")`, see
[Serializing](#serializing)). That name isn't part of the `Doc` at all — it's
discarded on import, so it doesn't survive a detour through another format
(see [XML](formats/xml.md#round-trip-behaviour)).

`doc(value)` and `Doc.from_data(value)` are the same thing. Tuples are accepted
and become lists; anything outside the Document model raises `DocumentError`
(see [The guard](#the-guard)).

**With the builder, one piece at a time** — start from `doc()` (an empty
object) and build it up with the editing API (see [Editing](#editing)):

```python
d = doc()                          # empty object
d.add("name", "Ann")

address = d.add_object("address")  # add an empty object, get a cursor to it
address.add("city", "London")

geo = address.add_object("geo")    # nest another object inside it
geo.add("lat", 51.5)
geo.add("lon", -0.1)

d.to_data()
# {"name": "Ann", "address": {"city": "London", "geo": {"lat": 51.5, "lon": -0.1}}}
```

Four different starting points — a Python value, four formats, and the
builder — one guarded result.

## Navigating

You move **one level at a time** — there are no deep paths, which keeps
navigation unambiguous even when repeated keys have produced arrays.

```python
d = doc({"name": "Ann", "address": {"city": "London", "geo": {"lat": 51.5, "lon": -0.1}}})

d.kind                          # "object"
d.keys()                        # ["name", "address"]
d.has("name")                   # True
d.has("missing")                # False
d.get("name")                   # "Ann"
d.get("address")                # {"city": "London", "geo": {...}}   (a detached snapshot copy)
d.get_or("missing", "n/a")      # "n/a" — default if absent

address = d.child("address")    # a live cursor into the object
address.path                    # "$.address"
address.get("city")             # "London"

geo = address.child("geo")      # navigate one more level
geo.path                        # "$.address.geo"
geo.get("lat")                  # 51.5

d.child("address").child("geo").get("lat")   # 51.5 — chaining is just repeated child()
```

Two getters, by intent:

- **`get(key)` / `at(index)`** return a **snapshot** — a plain value, and a
  *detached copy* for containers. Safe to read or hand off; editing it won't
  touch the document.
- **`child(key)` / `child_at(index)`** return a **live cursor** (`Doc`) you can
  navigate and edit further. They error on a scalar (you can't navigate into a
  value — use `get`/`at`).

A cursor knows where it is: `.parent`, `.key`, and `.path` (e.g.
`"$.address.geo"`, the same path style as validation errors).

## Editing

Mutation happens on the node you hold, one level at a time. Three verbs with
sharp, non-overlapping jobs:

```python
d = doc({"name": "Ann", "address": {"city": "London"}})

d.add("age", 30)                 # create a new child (key must not exist)
d.set("age", 31)                 # modify an existing scalar leaf, in place
d.remove("age")                  # delete the whole subtree at a key

address = d.child("address")
geo = address.add_object("geo")  # add an empty object, return a cursor to it
geo.add("lat", 51.5)

tags = d.add_array("tags")       # add an empty array, return a cursor
tags.append("vip"); tags.append("east")
```

- **`add`** introduces a new child; the key must not already exist. The value can
  be a scalar or a nested literal (validated + copied in).
- **`set`** only *modifies a scalar leaf*. It refuses to overwrite a subtree or to
  store a container — reshaping the tree is always an explicit `remove` + `add`,
  never a silent side effect of assignment.
- **`remove`** deletes the entire subtree at a key (object) or index (array).

Arrays add positional methods: `append`, `append_object`, `append_array`,
`insert`, `set(i, scalar)`, `remove(i)`, `at(i)`, `child_at(i)`, `len()`.

A cursor can remove itself from its parent with `drop()`:

```python
d.child("address").drop()        # detach this node from its parent
```

> **Stale cursors.** If you hold a cursor and then remove its node (or a node
> above it), using the cursor raises `DetachedNode` rather than silently editing
> an orphaned subtree. This also catches array-index invalidation — removing an
> earlier element detaches cursors to later ones.

## Serializing

`to_*` emit the document to any registered format; `to_data` gives you a plain
Python copy.

```python
d = doc({"name": "Ann", "address": {"city": "London", "geo": {"lat": 51.5, "lon": -0.1}}})

d.to_json(indent=2)
d.to_yaml()
d.to_toml()
d.to_xml(root="profile")         # root names the wrapper element (your choice)
d.to_format("json")              # generic, for plugin formats
d.to_data()                      # a detached deep copy as plain Python
```

The `to_*` methods accept the same options and lenient/`strict`/`report`
behavior as the functional writers — see [Formats](formats/overview.md).

## The guard

Every import and every `add`/`set` checks the value against the Document model
and **copies it in**. A `Doc` is therefore always a well-formed Document. The
guard rejects:

```python
doc({1: "x"})            # DocumentError: object key 1 is not a string
doc({"s": {1, 2}})       # DocumentError: set is not a Document value
doc({"f": open})         # DocumentError: builtin_function... is not a Document value
a = {}; a["x"] = a
doc(a)                   # DocumentError: cycle detected
```

Nesting past a depth limit (200 levels) is rejected the same way, so a
maliciously or accidentally deep structure — say, from parsing untrusted
JSON — raises a clean `DocumentError` instead of crashing the process with
an uncatchable `RecursionError`.

Errors carry the path to the offender (`"$.a.b[1]: ..."`). Copy-in also means
outside references can't corrupt the document after the fact:

```python
src = {"address": {"city": "London"}}
d = doc(src)
src["address"]["city"] = "Dublin"   # mutate the original
d.get("address")                      # {"city": "London"} — the Doc is unaffected
```

The guard checks **structure only** — that this is a legal Document. Whether it
matches an *expected shape* is a separate question, answered by a
[Schema](schema.md): `schema.validate(d)`.

## Dunders

`Doc` behaves like the container it wraps where it's unambiguous — same
profile document, showing exactly what each one does and returns:

```python
d = doc({"name": "Ann", "address": {"city": "London", "geo": {"lat": 51.5, "lon": -0.1}}})

len(d)                       # 2 — number of top-level keys (object) / elements (array)
list(d)                      # ["name", "address"] — objects iterate over keys
"name" in d                  # True — membership: keys for objects, values for arrays
"missing" in d                # False
d == {"name": "Ann", "address": {"city": "London", "geo": {"lat": 51.5, "lon": -0.1}}}
                              # True — compares by data, against a Doc or a plain value
repr(d)                       # "Doc(object: {'name': 'Ann', 'address': {...}})"
```

An array `Doc` iterates and measures its *elements*, not keys:

```python
tags = doc(["vip", "east"])

len(tags)                     # 2
list(tags)                    # ["vip", "east"] — arrays iterate element snapshots
"vip" in tags                 # True — membership checks values, not indices
tags == ["vip", "east"]       # True
```

A scalar `Doc` has no keys or elements: `len(s)` and `iter(s)` raise
`DocumentError` (there's nothing to count or iterate), while `x in s` quietly
returns `False` rather than erroring. Read a scalar's value with `.value`.

## Quick reference

| | object | array | scalar |
|---|---|---|---|
| read value | `get(k)` / `get_or(k,d)` | `at(i)` | `value` |
| navigate | `child(k)` | `child_at(i)` | — |
| inspect | `keys()`, `items()`, `has(k)` | `len()` | — |
| create child | `add`, `add_object`, `add_array` | `append`, `append_object`, `append_array`, `insert` | — |
| modify leaf | `set(k, scalar)` | `set(i, scalar)` | (via parent) |
| delete | `remove(k)`, child `.drop()` | `remove(i)` | — |
| emit | `to_json/yaml/toml/xml`, `to_format`, `to_data` | … | … |
| dunders | `len`, `iter` (keys), `in` (keys), `==` | `len`, `iter` (values), `in` (values), `==` | `==` only; `len`/`iter` raise, `in` is always `False` |
