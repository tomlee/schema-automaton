#!/usr/bin/env python3
"""The redesigned (canonical) model end to end: edge-list Document,
record/Ref schema with exactly seven scalars, field cardinality, validation,
operations, and codecs.

This exercises ``omnist.canonical`` — the implementation of the design in
``docs/design/model.md``.  It lives alongside the current v0.1 package.

Run: python3 examples/canonical_model.py
"""
from omnist import (
    Doc,
    doc,
    parse_schema,
    read_json,
    read_oml,
    read_toml,
    read_xml,
    read_yaml,
    to_osd,
)

SCHEMA = """
record Member {
    "name": string,
    "role": string,
}
record Team {
    "name":         string,
    "members" [1,]: Member,        # at least one member (array of records)
    "lead" [0,1]:   string,        # optional
}
root Team
"""


def main():
    s = parse_schema(SCHEMA)

    print("== schema round-trips through to_osd ==")
    print("equivalent:", s.equivalent(parse_schema(to_osd(s))))

    print("\n== the Team, in OML (omnist's own format) ==")
    o = read_oml('name: "Platform"\n'
                 'members: { name: "Ann"; role: "dev" }\n'
                 'members: { name: "Bob"; role: "pm" }\n')
    print("valid:", s.validate(Doc(o)).ok)

    print("\n== and the identical Document from JSON/YAML/TOML, too ==")
    j = read_json('{"name":"Platform","members":[{"name":"Ann","role":"dev"},'
                  '{"name":"Bob","role":"pm"}]}')
    y = read_yaml("name: Platform\nmembers:\n  - name: Ann\n    role: dev\n"
                  "  - name: Bob\n    role: pm\n")
    t = read_toml('name = "Platform"\n[[members]]\nname = "Ann"\nrole = "dev"\n'
                  '[[members]]\nname = "Bob"\nrole = "pm"\n')
    print("oml == json == yaml == toml:", o == j == y == t)

    print("\n== XML keeps the document element as one top-level edge ==")
    x = read_xml("<team><name>Platform</name>"
                 "<member><name>Ann</name><role>dev</role></member>"
                 "<member><name>Bob</name><role>pm</role></member></team>")
    print("xml document:", x)

    print("\n== a rejected document, errors at exact paths ==")
    bad = doc({"name": "Platform", "members": [{"name": 7, "role": "boss"}]})
    print(s.validate(bad))

    print("\n== compatible_with: adding an optional field is backward-compatible ==")
    v1 = parse_schema('record Team { "name": string, "members" [1,]: string }\nroot Team')
    v2 = parse_schema('record Team { "name": string, "members" [1,]: string, '
                      '"lead" [0,1]: string }\nroot Team')
    print("v1.compatible_with(v2):", v1.compatible_with(v2))
    print("v2.compatible_with(v1):", v2.compatible_with(v1))

    print("\n== normalize merges structurally identical named records ==")
    dup = parse_schema('record A { "x": integer }\nrecord B { "x": integer }\n'
                       'record R { "a": A, "b": B }\nroot R')
    n = dup.normalize()
    print("definitions before:", sorted(dup.env), "after:", sorted(n.env))
    print("equivalent:", dup.equivalent(n))


if __name__ == "__main__":
    main()
