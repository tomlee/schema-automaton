#!/usr/bin/env python3
"""A 60-second tour of dataspec. Run: python3 examples/quickstart.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dataspec import (
    read_json, write_toml, write_yaml, write_xml, read_xml,
    parse_schema, infer, to_dsl,
)


def main():
    print("== 1. Read a format into a Document (plain Python data) ==")
    data = read_json('{"name": "Ann", "age": 30, "tags": ["x", "y"], '
                     '"address": {"city": "HK"}}')
    print(data)

    print("\n== 2. Write the same Document to other formats ==")
    print("-- TOML --");  print(write_toml(data))
    print("-- YAML --");  print(write_yaml(data), end="")
    print("-- XML  --");  print(write_xml(data, root="person"))

    print("\n== 3. Validate against a Schema ==")
    schema = parse_schema("""
        root {
            name:    string,
            age:     integer,
            tags:    [string],
            address: { city: string }?,
        }
    """)
    print("valid doc:", schema.validate(data))
    bad = read_json('{"name": 1, "tags": ["x"]}')
    print(schema.validate(bad))

    print("\n== 4. Infer a Schema from samples, print it as DSL ==")
    learned = infer([
        read_json('{"id": 1, "email": "a@x.io", "roles": ["admin"]}'),
        read_json('{"id": 2, "roles": []}'),   # no email -> optional
    ])
    print(to_dsl(learned), end="")

    print("\n== 5. Check version compatibility ==")
    v1 = parse_schema("root { host: string, port: integer }")
    v2 = parse_schema("root { host: string, port: integer, tls?: boolean }")
    print("v1 docs valid under v2 (backward compatible):", v1.compatible_with(v2))

    print("\n== 6. XML round-trips back to the same data ==")
    print(read_xml(write_xml(data, root="person")) == data)


if __name__ == "__main__":
    main()
