"""Execute the key snippets shown in the docs, so they can't silently rot."""
import pytest

import omnist as ds
from omnist import (
    Doc,
    Format,
    WriteError,
    WriteReport,
    doc,
    field,
    infer,
    nullable,
    parse_schema,
    read_json,
    read_oml,
    read_toml,
    read_xml,
    read_yaml,
    record,
    ref,
    register_format,
    schema,
    t,
)


def test_readme_at_a_glance():
    s = parse_schema('record Member { "name": string, "role": string }\n'
                     'record Team { "name": string, "members" [1,]: Member }\nroot Team')
    assert s.validate(doc({"name": "X",
                           "members": [{"name": "Ann", "role": "dev"}]})).ok
    assert ds.__version__ == "0.1.3"


def test_readme_60_second_tour_infer():
    assert infer([doc({"id": 1, "tags": ["a"]})]).to_dsl() == (
        'record Root {\n    "id": integer,\n    "tags": string,\n}\nroot Root\n')


def test_guide_documents():
    d = doc({"name": "Ann", "tag": ["x", "y"]})
    assert d.labels() == ["name", "tag"]
    assert d.count("tag") == 2
    assert d.get_one("name").value == "Ann"
    assert [c.value for c in d.get("tag")] == ["x", "y"]
    assert d.to_data() == [("name", "Ann"), ("tag", "x"), ("tag", "y")]
    assert d.to_grouped() == {"name": "Ann", "tag": ["x", "y"]}


def test_guide_oml_native_format():
    import datetime
    d = Doc.from_oml('\nname: "Ann"\ntag: "x"\ntag: "y"\njoined: 2024-01-01\n')
    assert d.to_grouped() == {"name": "Ann", "tag": ["x", "y"],
                              "joined": datetime.date(2024, 1, 1)}
    assert d.to_oml() == 'name: "Ann"\ntag: "x"\ntag: "y"\njoined: 2024-01-01'


def test_formats_oml_maps_to_the_same_document_as_the_builder():
    import datetime
    node = read_oml('''
name: "Ann"
role: "dev"
joined: 2024-01-01
tag: "x"
tag: "y"
manager: null
''')
    built = doc({
        "name": "Ann",
        "role": "dev",
        "joined": datetime.date(2024, 1, 1),
        "tag": ["x", "y"],
        "manager": None,
    })
    assert node == built.to_data()


def test_schema_page_dsl_shape_and_builder_equivalence():
    DSL = '''
    record Address { "street": string, "city": string }

    record User {
        "name":          string,
        "nickname" [0,1]: string,
        "emails" [1,]:    string,
        "address":       Address,
        "note":          string?,
    }
    root User
    '''
    s = parse_schema(DSL)
    assert s.validate(doc({"name": "Ann", "emails": ["a@x.com"],
                           "address": {"street": "1 Main", "city": "London"},
                           "note": None})).ok

    address = record(field("street", t.string), field("city", t.string))
    user = record(
        field("name",     t.string),
        field("nickname", t.string, min=0, max=1),
        field("emails",   t.string, min=1, max=None),
        field("address",  ref("Address")),
        field("note",     nullable(t.string)),
    )
    s2 = schema(ref("User"), User=user, Address=address)
    assert s.equivalent(s2)


def test_schema_page_validation_errors():
    DSL = '''
    record Address { "street": string, "city": string }
    record User {
        "name":          string,
        "nickname" [0,1]: string,
        "emails" [1,]:    string,
        "address":       Address,
        "note":          string?,
    }
    root User
    '''
    s = parse_schema(DSL)
    bad = doc({"emails": [], "address": {"street": "x", "city": "y"}})
    msgs = {e.message for e in s.validate(bad).errors}
    assert any("'name' occurs 0 time(s), expected exactly 1" in m for m in msgs)
    assert any("'emails' occurs 0 time(s), expected at least 1" in m for m in msgs)
    assert any("'note' occurs 0 time(s), expected exactly 1" in m for m in msgs)


def test_schema_page_operations_and_infer():
    v1 = parse_schema('record R { "host": string }\nroot R')
    v2 = parse_schema('record R { "host": string, "port" [0,1]: integer }\nroot R')
    assert v1.compatible_with(v2)
    assert not v2.compatible_with(v1)

    assert infer([doc({"host": "b", "port": 80}), doc({"host": "a"})]).to_dsl() == (
        'record Root {\n    "host": string,\n    "port" [0,1]: integer,\n}\nroot Root\n')


def test_guide_editing():
    d = doc({"name": "Ann"})
    d.add("tag", "x").add("tag", "y")
    d.set("name", "Bob")
    d.remove("tag")
    assert d.to_grouped() == {"name": "Bob"}


def test_guide_builder_matches_dsl():
    address = record(field("street", t.string), field("city", t.string))
    user = record(field("name", t.string),
                  field("emails", t.string, min=1, max=None),
                  field("address", ref("Address")),
                  field("status", t.string))
    s = schema(ref("User"), User=user, Address=address)
    dsl = parse_schema('record Address { "street": string, "city": string }\n'
                       'record User { "name": string, "emails" [1,]: string, '
                       '"address": Address, "status": string }\nroot User')
    assert s.equivalent(dsl)


def test_guide_validation_error():
    r = parse_schema('record R { "items" [1,]: integer }\nroot R').validate(
            doc({"items": []}))
    assert not r.ok
    assert r.errors[0].path == "$" and "at least 1" in r.errors[0].message


def test_guide_operations_are_methods():
    v1 = parse_schema('record R { "host": string }\nroot R')
    v2 = parse_schema('record R { "host": string, "port" [0,1]: integer }\nroot R')
    assert v1.compatible_with(v2)
    assert not v2.compatible_with(v1)
    assert not v1.equivalent(v2)


def test_readme_schema_directed_deserialization():
    import datetime
    s2 = parse_schema('record R { "d": date }\nroot R')
    assert read_json('{"d": "2024-01-01"}', schema=s2) == \
        [("d", datetime.date(2024, 1, 1))]


def test_guide_infer():
    s = infer([doc({"id": 1, "tags": ["a"]}), doc({"id": 2, "tags": ["b", "c"]})])
    assert s.to_dsl() == ('record Root {\n    "id": integer,\n'
                          '    "tags" [0,]: string,\n}\nroot Root\n')


def test_guide_real_life_example():
    ORDER = '''
    record Address  { "street": string, "city": string }
    record LineItem { "sku": string, "qty": integer, "price": number }
    record Order {
        "id":       string,
        "status":   string,
        "total":    number,
        "address":  Address,
        "items" [1,]: LineItem,
        "coupon" [0,1]: string,
    }
    root Order
    '''
    s = parse_schema(ORDER)

    good = Doc.from_oml('''
id: "A1"
status: "shipped"
total: 29.97
address: { street: "1 Main St"; city: "London" }
items: { sku: "W"; qty: 3; price: 9.99 }
''')
    assert s.validate(good).ok

    bad = Doc.from_oml('''
id: "A2"
status: "shipped"
total: "ten"
address: { street: "x"; city: "y" }
''')
    msgs = {e.message for e in s.validate(bad).errors}
    assert any("expected number, got string" in m for m in msgs)
    assert any("at least 1" in m for m in msgs)


def test_example_all_formats_one_document():
    s = parse_schema('''
        record Address  { "street": string, "city": string }
        record LineItem { "sku": string, "qty": integer, "price": number }
        record Order {
            "id": string,
            "status": string,
            "total": number,
            "address": Address,
            "items" [1,]: LineItem,
            "coupon" [0,1]: string,
        }
        record Root { "order": Order }
        root Root
    ''')
    j = read_json('{"order":{"id":"A1","status":"shipped","total":29.97,'
                  '"address":{"street":"1 Main","city":"London"},'
                  '"items":[{"sku":"W","qty":3,"price":9.99},'
                  '{"sku":"G","qty":1,"price":9.99}]}}')
    y = read_yaml("order:\n  id: A1\n  status: shipped\n  total: 29.97\n"
                  "  address: {street: 1 Main, city: London}\n"
                  "  items:\n    - {sku: W, qty: 3, price: 9.99}\n"
                  "    - {sku: G, qty: 1, price: 9.99}\n")
    tm = read_toml('[order]\nid="A1"\nstatus="shipped"\ntotal=29.97\n'
                   '[order.address]\nstreet="1 Main"\ncity="London"\n'
                   '[[order.items]]\nsku="W"\nqty=3\nprice=9.99\n'
                   '[[order.items]]\nsku="G"\nqty=1\nprice=9.99\n')
    x = read_xml("<order><id>A1</id><status>shipped</status><total>29.97</total>"
                 "<address><street>1 Main</street><city>London</city></address>"
                 "<items><sku>W</sku><qty>3</qty><price>9.99</price></items>"
                 "<items><sku>G</sku><qty>1</qty><price>9.99</price></items></order>")
    assert j == y == tm == x
    assert all(s.validate(Doc(d)).ok for d in (j, y, tm, x))


def test_example_doc_all_formats_one_document_incl_oml():
    s = parse_schema('''
        record Address  { "street": string, "city": string }
        record LineItem { "sku": string, "qty": integer, "price": number }
        record Order {
            "id": string,
            "status": string,
            "total": number,
            "address": Address,
            "items" [1,]: LineItem,
            "coupon" [0,1]: string,
        }
        record Root { "order": Order }
        root Root
    ''')
    j = read_json('{"order":{"id":"A1","status":"shipped","total":29.97,'
                  '"address":{"street":"1 Main","city":"London"},'
                  '"items":[{"sku":"W","qty":3,"price":9.99},'
                  '{"sku":"G","qty":1,"price":9.99}]}}')
    o = read_oml('''
order: {
    id: "A1"
    status: "shipped"
    total: 29.97
    address: { street: "1 Main"; city: "London" }
    items: { sku: "W"; qty: 3; price: 9.99 }
    items: { sku: "G"; qty: 1; price: 9.99 }
}
''')
    assert j == o
    assert s.validate(Doc(o)).ok
    assert Doc(o).to_json() == (
        '{"order": {"id": "A1", "status": "shipped", "total": 29.97, '
        '"address": {"street": "1 Main", "city": "London"}, '
        '"items": [{"sku": "W", "qty": 3, "price": 9.99}, '
        '{"sku": "G", "qty": 1, "price": 9.99}]}}')

    bad = Doc.from_oml('''
order: {
    id: "A2"
    status: "shipped"
    total: "ten"
    address: { street: "x"; city: "y" }
}
''')
    msgs = {e.message for e in s.validate(bad).errors}
    assert any("expected number, got string" in m for m in msgs)
    assert any("at least 1" in m for m in msgs)


def test_example_rejected_order():
    s = parse_schema('record LineItem { "sku": string }\n'
                     'record Order { "status": integer, '
                     '"items" [1,]: LineItem }\n'
                     'record Root { "order": Order }\nroot Root')
    bad = Doc.from_json('{"order":{"status":"lost","items":[]}}')
    msgs = {e.message for e in s.validate(bad).errors}
    assert any("expected integer" in m for m in msgs)
    assert any("at least 1" in m for m in msgs)


def test_formats_docs_snippets():
    from omnist import write_json
    assert write_json([("tag", "x"), ("tag", "y")]) == '{"tag": ["x", "y"]}'
    assert write_json([("tag", "x")]) == '{"tag": "x"}'
    assert read_xml("<t><m>a</m><x>1</x><m>b</m></t>") == \
        [("t", [("m", "a"), ("x", 1), ("m", "b")])]      # interleaving preserved


def test_api_docs_schema_directed_deserialization():
    import datetime
    s = parse_schema('record R { "d": date, "n": number }\nroot R')
    node = read_json('{"d": "2024-01-01", "n": 3}', schema=s)
    assert node == [("d", datetime.date(2024, 1, 1)), ("n", 3.0)]


def test_api_docs_adjustment_reports():
    d = doc({"a": 1, "b": None})
    assert d.to_toml() == "a = 1\n"
    rep = WriteReport()
    d.to_toml(report=rep)
    assert [(a.code, a.severity) for a in rep] == [("null.omitted", "warning")]
    assert [(a.code, a.severity) for a in d.check_toml()] == \
        [(a.code, a.severity) for a in rep]
    with pytest.raises(WriteError):
        d.to_toml(strict=True)


def test_api_docs_format_registry():
    register_format(Format(
        name="lines",
        read=lambda text: [("n", int(x)) for x in text.split()],
        write=lambda node, **opts: " ".join(str(v) for _, v in node),
    ))
    assert Doc.from_format("lines", "1 2 3").to_format("lines") == "1 2 3"


def test_api_docs_version():
    assert ds.__version__ == "0.1.3"


def test_api_docs_schema_raises():
    from omnist import SchemaError
    from omnist.canonical.schema import Ref, Scalar, Schema

    # root isn't a Ref
    try:
        Schema(Scalar("string"))
        assert False, "expected SchemaError"
    except SchemaError:
        pass

    # an env entry isn't a Record
    try:
        Schema(Ref("R"), {"R": Scalar("string")})
        assert False, "expected SchemaError"
    except SchemaError:
        pass

    # a Ref names an entry not present in env
    try:
        Schema(Ref("R"), {})
        assert False, "expected SchemaError"
    except SchemaError:
        pass


def test_api_docs_string_ambiguous_adjustment():
    d = doc({"x": "42"})
    rep = WriteReport()
    d.to_xml(report=rep)
    assert [(a.code, a.severity) for a in rep] == [("string.ambiguous", "warning")]


def test_model_docs_count1_no_schema_param():
    import inspect

    from omnist import write_json, write_toml, write_xml, write_yaml
    for fn in (write_json, write_yaml, write_toml, write_xml):
        assert "schema" not in inspect.signature(fn).parameters
    assert write_json([("tag", "x")]) == '{"tag": "x"}'
    assert write_json([("tag", "x"), ("tag", "y")]) == '{"tag": ["x", "y"]}'


def test_model_docs_appendix_worked_example():
    s = parse_schema('''
record Member {
    "name": string,
    "role": string,
}
record Team {
    "name":         string,
    "members" [0,]: Member,
}
root Team
''')
    node = [("name", "Platform"),
            ("members", [("name", "Ann"), ("role", "dev")]),
            ("members", [("name", "Bob"), ("role", "pm")])]
    d = Doc(node)
    assert s.validate(d).ok
    assert d.to_json() == (
        '{"name": "Platform", "members": '
        '[{"name": "Ann", "role": "dev"}, {"name": "Bob", "role": "pm"}]}')
