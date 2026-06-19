# Documents (the `Doc` API)

A **Document** is a tree of objects, arrays, and scalars. `Doc` is the guarded
data structure you use to build, navigate, edit, and serialize one. Think of it
as a format-neutral DOM: the same `Doc` can be written to JSON, YAML, TOML, or
XML, and reading any of those gives you a `Doc`.

The point of going through `Doc` rather than poking at raw dicts and lists is
**safety**: every value you put in is checked against the Document model and
copied in, so the structure can never drift into something unserializable.

## Creating a Doc

```python
from dataspec import Doc, doc

doc()                                  # an empty object
doc({"name": "Ann", "tags": ["x"]})    # import a Python value (validated, copied)
doc([1, 2, 3])                         # an array document
doc(42)                                # a scalar document

Doc.from_json('{"a": 1}')              # import from a format string
Doc.from_yaml(text); Doc.from_toml(text); Doc.from_xml(text)
Doc.from_format("json", text)          # generic (works for plugin formats too)
```

`doc(value)` and `Doc.from_data(value)` are the same thing. Tuples are accepted
and become lists; anything outside the Document model raises `DocumentError`
(see [The guard](#the-guard)).

### Building one piece at a time

You don't need an existing value or format string at all — start from `doc()`
(an empty object) and build it up with the editing API (see
[Editing](#editing)):

```python
d = doc()                          # empty object
d.add("name", "Ann")

address = d.add_object("address")  # add an empty object, get a cursor to it
address.add("city", "HK")

items = d.add_array("items")       # add an empty array, get a cursor to it
item = items.append_object()       # append an object, get a cursor to it
item.add("id", 1)

d.to_data()                        # {"name": "Ann",
                                    #  "address": {"city": "HK"},
                                    #  "items": [{"id": 1}]}
```

This is the same `Doc` you'd get from
`doc({"name": "Ann", "address": {"city": "HK"}, "items": [{"id": 1}]})` or the
equivalent JSON via `Doc.from_json(...)` — three different starting points, one
guarded result.

## Navigating

You move **one level at a time** — there are no deep paths, which keeps
navigation unambiguous even when repeated keys have produced arrays.

```python
d = doc({"name": "Ann", "address": {"city": "HK"}, "items": [{"id": 1}]})

d.kind                      # "object" | "array" | "scalar"
d.keys()                    # ["name", "address", "items"]
d.has("name")               # True
d.get("name")               # "Ann"           (scalar value)
d.get("address")            # {"city": "HK"}   (a detached snapshot copy)
d.get_or("missing", None)   # default if absent

d.child("address")          # a live cursor into the object
d.child("address").get("city")          # "HK"
d.child("items").child_at(0).get("id")  # 1
```

Two getters, by intent:

- **`get(key)` / `at(index)`** return a **snapshot** — a plain value, and a
  *detached copy* for containers. Safe to read or hand off; editing it won't
  touch the document.
- **`child(key)` / `child_at(index)`** return a **live cursor** (`Doc`) you can
  navigate and edit further. They error on a scalar (you can't navigate into a
  value — use `get`/`at`).

A cursor knows where it is: `.parent`, `.key`, and `.path` (e.g. `"$.items[0]"`,
the same path style as validation errors).

## Editing

Mutation happens on the node you hold, one level at a time. Three verbs with
sharp, non-overlapping jobs:

```python
d.add("age", 30)                 # create a new child (key must not exist)
d.set("age", 31)                 # modify an existing scalar leaf, in place
d.remove("age")                  # delete the whole subtree at a key

o = d.add_object("address")      # add an empty object, return a cursor to it
o.add("city", "HK")
a = d.add_array("tags")          # add an empty array, return a cursor
a.append("x"); a.append("y")
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
d.to_json(indent=2); d.to_yaml(); d.to_toml(); d.to_xml(root="record")
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

Errors carry the path to the offender (`"$.a.b[1]: ..."`). Copy-in also means
outside references can't corrupt the document after the fact:

```python
src = {"xs": [1, 2]}
d = doc(src)
src["xs"].append(99)     # mutate the original
d.get("xs")              # [1, 2] — the Doc is unaffected
```

The guard checks **structure only** — that this is a legal Document. Whether it
matches an *expected shape* is a separate question, answered by a
[Schema](schema.md): `schema.validate(d)`.

## Dunders

`Doc` behaves like the container it wraps where it's unambiguous:

```python
len(d)                   # number of keys / elements
for k in d: ...          # objects iterate keys; arrays iterate element snapshots
"name" in d              # membership (keys for objects, values for arrays)
doc({"a": 1}) == {"a": 1}   # compares by data (against a Doc or plain value)
```

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
