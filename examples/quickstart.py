#!/usr/bin/env python3
"""A 60-second tour of dataspec. Run: python3 examples/quickstart.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dataspec import Doc, arr, doc, infer, obj, optional, schema, t


def main():
    print("== 1. Import data into a Document (a guarded data structure) ==")
    d = Doc.from_json('{"name": "Ann", "age": 30, "tags": ["x", "y"], '
                      '"address": {"city": "London"}}')
    print("kind:", d.kind, "| keys:", d.keys())

    print("\n== 2. Navigate and edit through the API ==")
    print("city:", d.child("address").get("city"))
    d.child("address").set("city", "NY")           # modify a scalar leaf
    d.add("active", True)                           # add a new field
    print("city now:", d.child("address").get("city"), "| active:", d.get("active"))

    print("\n== 3. Serialize the same Document to any format ==")
    print("-- TOML --"); print(d.to_toml())
    print("-- YAML --"); print(d.to_yaml(), end="")

    print("\n== 4. Validate against a Schema (built in Python) ==")
    s = schema(obj(
        name    = t.string,
        age     = t.integer,
        tags    = arr(t.string),
        address = obj(city=t.string),
        active  = optional(t.boolean),
    ))
    print("validate:", s.validate(d))

    print("\n== 5. Infer a Schema from samples ==")
    learned = infer([
        doc({"id": 1, "email": "a@x.io", "roles": ["admin"]}),
        doc({"id": 2, "roles": []}),               # no email -> optional
    ])
    print(learned.to_dsl(), end="")


if __name__ == "__main__":
    main()
