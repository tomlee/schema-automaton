"""Execute the key snippets shown in the docs, so they can't silently rot."""
import omnist as ds
from omnist import (
    Doc,
    Format,
    WriteError,
    WriteReport,
    doc,
    field,
    infer,
    parse_schema,
    read_json,
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
    assert ds.__version__ == "0.1.1a9"


def test_guide_documents():
    d = doc({"name": "Ann", "tag": ["x", "y"]})
    assert d.labels() == ["name", "tag"]
    assert d.count("tag") == 2
    assert d.get_one("name").value == "Ann"
    assert [c.value for c in d.get("tag")] == ["x", "y"]
    assert d.to_data() == [("name", "Ann"), ("tag", "x"), ("tag", "y")]
    assert d.to_grouped() == {"name": "Ann", "tag": ["x", "y"]}


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
    try:
        d.to_toml(strict=True)
        assert False, "expected WriteError"
    except WriteError:
        pass


def test_api_docs_format_registry():
    register_format(Format(
        name="lines",
        read=lambda text: [("n", int(x)) for x in text.split()],
        write=lambda node, **opts: " ".join(str(v) for _, v in node),
    ))
    assert Doc.from_format("lines", "1 2 3").to_format("lines") == "1 2 3"
