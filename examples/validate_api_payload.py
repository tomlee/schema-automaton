#!/usr/bin/env python3
"""Validate an incoming JSON payload against a schema and report errors.

Run: python3 examples/validate_api_payload.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataspec import read_json, parse_schema

SCHEMA = parse_schema("""
    root {
        id:      integer,
        email:   string,
        roles:   [string]+,          # at least one role
        active:  boolean,
        profile: { name: string, age?: integer }?,
    }
""")


def handle(raw_json: str) -> None:
    doc = read_json(raw_json)
    result = SCHEMA.validate(doc)
    if result:
        print("OK  ", doc.get("email"))
    else:
        print("FAIL", doc.get("email", "?"))
        for err in result.errors:
            print(f"     {err.path}: {err.message}")


def main():
    handle('{"id": 1, "email": "a@x.io", "roles": ["admin"], "active": true}')
    handle('{"id": "two", "email": "b@x.io", "roles": [], "active": "yes"}')


if __name__ == "__main__":
    main()
