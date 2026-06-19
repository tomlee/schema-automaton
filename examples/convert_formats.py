#!/usr/bin/env python3
"""Convert one document between all four formats, and show the null rule.

Run: python3 examples/convert_formats.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dataspec import (
    read_json, write_yaml, write_toml, write_xml, WriteError,
)


def main():
    doc = read_json('{"name": "Ann", "age": 30, "tags": ["x", "y"], '
                    '"address": {"city": "HK"}}')

    print("-- YAML --");  print(write_yaml(doc), end="")
    print("-- TOML --");  print(write_toml(doc))
    print("-- XML  --");  print(write_xml(doc, root="person"))

    print("\n-- null handling --")
    print("TOML drops a null field:", write_toml({"a": 1, "b": None}).strip())
    try:
        write_toml({"xs": [1, None, 2]})
    except WriteError as e:
        print("TOML refuses null in an array:", e)


if __name__ == "__main__":
    main()
