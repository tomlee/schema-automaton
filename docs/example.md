# A worked example

The other pages explain dataspec's pieces one at a time. This page puts them
together: one realistic schema, real documents in every supported format —
some accepted, some rejected — and a walkthrough of the three schema
operations (`validate`, `compatible_with`, `normalize`) doing real work
against it.

Every code block on this page is verified against the library, not
illustrative pseudocode.

## The scenario

An e-commerce service exchanges **order** documents. Each order has an id, a
status, a total, a shipping address, at least one line item, an optional
coupon code, and a bag of arbitrary tags:

```python
{
    "order": {
        "id": "A1001",
        "status": "shipped",
        "total": 29.97,
        "address": {"street": "1 Main St", "city": "London"},
        "items": [{"sku": "WIDGET", "qty": 3, "price": 9.99}],
        "tags": {"region": "EU"},
    }
}
```

The whole document sits under one top-level key (`order`) rather than putting
its fields directly at the root. That's deliberate, not decorative — see
[Why one top-level key](#why-one-top-level-key) below.

## The schema

As DSL text:

```
type Address = { street: string, city: string }
type LineItem = { sku: string, qty: integer, price: number }

root {
    order: {
        id:      string,
        status:  "pending" | "shipped" | "cancelled",
        total:   number,
        address: Address,
        items:   [LineItem]+,          # at least one line item
        coupon?: string,               # optional
        tags:    { [string]: string }, # arbitrary extra keys -> string
    },
}
```

Or the same schema with the [builder](schema.md#the-python-builder):

```python
from dataspec import arr, doc, enum, mapping, obj, optional, parse_schema, schema, t

address_t = obj(street=t.string, city=t.string)
line_item_t = obj(sku=t.string, qty=t.integer, price=t.number)
order_t = obj(
    id=t.string,
    status=enum("pending", "shipped", "cancelled"),
    total=t.number,
    address=address_t,
    items=arr(line_item_t, min=1),
    coupon=optional(t.string),
    tags=mapping(t.string),
)
s = schema(obj(order=order_t))
```

Both produce the identical schema (`parse_schema(DSL).equivalent(s)` is
`True`); the rest of this page uses `s` to mean either.

## Accepted documents, in every format

The same order, read from each format, produces the identical `Doc` — and
`s.validate(...)` accepts all four:

```python
from dataspec import read_json, read_toml, read_xml, read_yaml

json_doc = read_json('''
{"order": {"id": "A1001", "status": "shipped", "total": 29.97,
 "address": {"street": "1 Main St", "city": "London"},
 "items": [{"sku": "WIDGET", "qty": 3, "price": 9.99},
           {"sku": "GADGET", "qty": 1, "price": 9.99}],
 "tags": {"region": "EU"}}}
''')

yaml_doc = read_yaml('''
order:
  id: A1001
  status: shipped
  total: 29.97
  address:
    street: 1 Main St
    city: London
  items:
    - sku: WIDGET
      qty: 3
      price: 9.99
    - sku: GADGET
      qty: 1
      price: 9.99
  tags:
    region: EU
''')

toml_doc = read_toml('''
[order]
id = "A1001"
status = "shipped"
total = 29.97

[order.address]
street = "1 Main St"
city = "London"

[[order.items]]
sku = "WIDGET"
qty = 3
price = 9.99

[[order.items]]
sku = "GADGET"
qty = 1
price = 9.99

[order.tags]
region = "EU"
''')

xml_doc = read_xml(
    "<order><id>A1001</id><status>shipped</status><total>29.97</total>"
    "<address><street>1 Main St</street><city>London</city></address>"
    "<items><sku>WIDGET</sku><qty>3</qty><price>9.99</price></items>"
    "<items><sku>GADGET</sku><qty>1</qty><price>9.99</price></items>"
    "<tags><region>EU</region></tags></order>")

json_doc == yaml_doc == toml_doc == xml_doc      # True -- identical Document
s.validate(doc(json_doc)).ok                     # True
s.validate(doc(yaml_doc)).ok                     # True
s.validate(doc(toml_doc)).ok                     # True
s.validate(doc(xml_doc)).ok                      # True
```

## Rejected documents

A document with a bad enum value and an empty `items` array — invalid in any
format, since the schema doesn't care how the data arrived:

```python
bad = doc({
    "order": {
        "id": "A1002",
        "status": "lost",          # not one of the enum values
        "total": 10,
        "address": {"street": "2 Main St", "city": "London"},
        "items": [],                # violates the [LineItem]+ minimum
        "tags": {},
    }
})
s.validate(bad)
# invalid:
#   at $.order.status: 'lost' not one of ['cancelled', 'pending', 'shipped']
#   at $.order.items: array length 0 is not at least 1
```

### A format-specific rejection: XML's single-item ambiguity

This one is worth seeing because it isn't a data problem — it's a real,
documented XML limitation interacting with this exact schema. XML represents
a repeated element as a list only when it actually repeats; a single
`<items>` element is indistinguishable from "not an array at all" on read
(see [XML](formats/xml.md)):

```python
one_item_xml = read_xml(
    "<order><id>A1003</id><status>pending</status><total>9.99</total>"
    "<address><street>3 Main St</street><city>London</city></address>"
    "<items><sku>WIDGET</sku><qty>1</qty><price>9.99</price></items>"
    "<tags></tags></order>")

s.validate(doc(one_item_xml))
# invalid:
#   at $.order.items: expected array, got object
#   at $.order.tags: expected object, got string
```

Two distinct, documented XML quirks fire at once here: a single `<items>`
reads back as an object, not a one-element list (the array ambiguity above),
and an empty `<tags></tags>` reads back as `""`, not `{}` (XML can't tell
"empty object" and "empty string" apart on read — see
[XML's container-empty-ambiguous case](formats/xml.md)). Neither is a bug;
both are why round-tripping through XML needs a little more care than the
other three formats when arity or emptiness matters.

## Using `compatible_with`: is a schema change backward-compatible?

Say `coupon` didn't exist yet — that's `V1` — and you're adding it as an
optional field — that's `V2` (the schema above):

```python
V1 = '''
type Address = { street: string, city: string }
type LineItem = { sku: string, qty: integer, price: number }
root {
    order: {
        id: string,
        status: "pending" | "shipped" | "cancelled",
        total: number,
        address: Address,
        items: [LineItem]+,
        tags: { [string]: string },
    },
}
'''
v1 = parse_schema(V1)
v2 = s   # the schema with coupon? above

v1.compatible_with(v2)      # True  -- every old (v1-shaped) document is still valid under v2
v2.compatible_with(v1)      # False -- a v2 document WITH a coupon isn't valid under v1
```

Read `a.compatible_with(b)` as "every document `a` accepts, `b` also
accepts" — here, every order written before the `coupon` field existed still
validates against the new schema:

```python
old_order = doc({"order": {"id": "A1", "status": "pending", "total": 5,
                            "address": {"street": "x", "city": "y"},
                            "items": [{"sku": "s", "qty": 1, "price": 1.0}],
                            "tags": {}}})
v1.validate(old_order).ok      # True
v2.validate(old_order).ok      # True -- still valid; coupon is optional, not required
```

That's the practical use: when you change a schema, check `old.compatible_with(new)`
in CI. If it's `False`, the change can break consumers still sending the old
shape. See [Comparing schemas](operations.md) for the full list of changes
that stay compatible (widening a scalar, loosening array bounds, adding an
optional field, …).

## Using `normalize`: collapsing duplicate named types

If a schema accumulates two named types that turned out structurally
identical — easy to happen when types are merged from different sources —
`normalize()` collapses them:

```python
dup = parse_schema('''
    type Address = { street: string, city: string }
    type ShipTo  = { street: string, city: string }
    root { billing: Address, shipping: ShipTo }
''')

sorted(dup.types)                  # ['Address', 'ShipTo']
n = dup.normalize()
sorted(n.types)                    # ['Address'] -- ShipTo merged into it
dup.equivalent(n)                  # True -- same language, just one fewer named type
```

Useful before printing a schema (`to_dsl()`) or comparing two schemas that
were assembled independently, where superficial duplication shouldn't count
as a real difference.

## Why one top-level key

The order document is `{"order": {...}}`, not `{"id": ..., "status": ...}`
directly. An XML document has exactly one document element, so a Document
needs exactly one top-level key to have a lossless, single-document XML
representation — the document element's tag *is* that key (see
[XML is single-rooted](formats/xml.md#xml-is-single-rooted)). Structuring the
schema this way from the start means the same Document, and the same schema,
works unmodified across all four formats, which is what made every example
above possible without a format-specific wrapper step.

## See also

- [Schemas](schema.md) — the full DSL and builder reference.
- [Documents](document.md) — the `Doc` API used to build and navigate documents.
- [Comparing schemas](operations.md) — `compatible_with` / `equivalent` / `normalize` in depth.
- [Formats](formats/overview.md) — what each format can and can't represent.
- [Inferring schemas](infer.md) — draft a schema like this one from examples instead of writing it by hand.
