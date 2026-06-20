#!/usr/bin/env python3
"""The full worked example from docs/example.md: one schema, real documents
in every format (some accepted, some rejected), and the three schema
operations (validate, compatible_with, normalize) used the way you'd
actually use them. Run this to confirm the doc's output is real.

Run: python3 examples/worked_example.py
"""
from dataspec import (
    arr,
    doc,
    enum,
    mapping,
    obj,
    optional,
    parse_schema,
    read_json,
    read_toml,
    read_xml,
    read_yaml,
    schema,
    t,
)

DSL = """
type Address = { street: string, city: string }
type LineItem = { sku: string, qty: integer, price: number }

root {
    order: {
        id:      string,
        status:  "pending" | "shipped" | "cancelled",
        total:   number,
        address: Address,
        items:   [LineItem]+,
        coupon?: string,
        tags:    { [string]: string },
    },
}
"""


def builder_schema():
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
    return schema(obj(order=order_t))


def accepted_documents(s):
    print("== the same order, accepted from every format ==")
    json_doc = read_json("""
        {"order": {"id": "A1001", "status": "shipped", "total": 29.97,
         "address": {"street": "1 Main St", "city": "London"},
         "items": [{"sku": "WIDGET", "qty": 3, "price": 9.99},
                   {"sku": "GADGET", "qty": 1, "price": 9.99}],
         "tags": {"region": "EU"}}}
    """)
    yaml_doc = read_yaml("""
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
    """)
    toml_doc = read_toml("""
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
    """)
    xml_doc = read_xml(
        "<order><id>A1001</id><status>shipped</status><total>29.97</total>"
        "<address><street>1 Main St</street><city>London</city></address>"
        "<items><sku>WIDGET</sku><qty>3</qty><price>9.99</price></items>"
        "<items><sku>GADGET</sku><qty>1</qty><price>9.99</price></items>"
        "<tags><region>EU</region></tags></order>")

    assert json_doc == yaml_doc == toml_doc == xml_doc
    for name, d in [("json", json_doc), ("yaml", yaml_doc), ("toml", toml_doc), ("xml", xml_doc)]:
        result = s.validate(doc(d))
        print(f"  {name}: {result.ok}")
        assert result.ok


def rejected_documents(s):
    print("\n== a document with two unrelated problems ==")
    bad = doc({
        "order": {
            "id": "A1002",
            "status": "lost",
            "total": 10,
            "address": {"street": "2 Main St", "city": "London"},
            "items": [],
            "tags": {},
        }
    })
    print(s.validate(bad))

    print("\n== a format-specific rejection: XML's single-item ambiguity ==")
    one_item_xml = read_xml(
        "<order><id>A1003</id><status>pending</status><total>9.99</total>"
        "<address><street>3 Main St</street><city>London</city></address>"
        "<items><sku>WIDGET</sku><qty>1</qty><price>9.99</price></items>"
        "<tags></tags></order>")
    print(s.validate(doc(one_item_xml)))


def compatible_with_demo(v2):
    print("\n== compatible_with: was adding `coupon?` backward-compatible? ==")
    v1 = parse_schema("""
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
    """)
    print("v1.compatible_with(v2):", v1.compatible_with(v2))
    print("v2.compatible_with(v1):", v2.compatible_with(v1))

    old_order = doc({
        "order": {"id": "A1", "status": "pending", "total": 5,
                  "address": {"street": "x", "city": "y"},
                  "items": [{"sku": "s", "qty": 1, "price": 1.0}],
                  "tags": {}}
    })
    print("v1 accepts an old order:", v1.validate(old_order).ok)
    print("v2 accepts that same old order:", v2.validate(old_order).ok)


def normalize_demo():
    print("\n== normalize: collapsing structurally identical named types ==")
    dup = parse_schema("""
        type Address = { street: string, city: string }
        type ShipTo  = { street: string, city: string }
        root { billing: Address, shipping: ShipTo }
    """)
    print("before:", sorted(dup.types))
    n = dup.normalize()
    print("after: ", sorted(n.types))
    print("equivalent:", dup.equivalent(n))


def main():
    s_dsl = parse_schema(DSL)
    s_builder = builder_schema()
    print("DSL and builder schemas are equivalent:", s_dsl.equivalent(s_builder))

    accepted_documents(s_dsl)
    rejected_documents(s_dsl)
    compatible_with_demo(s_dsl)
    normalize_demo()


if __name__ == "__main__":
    main()
