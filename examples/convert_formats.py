#!/usr/bin/env python3
"""Convert one document between all four formats, and show the adjustment report.

Run: python3 examples/convert_formats.py
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dataspec import Doc, WriteError, WriteReport, check_toml, doc


def main():
    d = Doc.from_json('{"name": "Ann", "age": 30, "tags": ["x", "y"], '
                      '"address": {"city": "London"}}')

    print("-- YAML --");  print(d.to_yaml(), end="")
    print("-- TOML --");  print(d.to_toml())
    # XML needs exactly one top-level element, so a multi-key Document like
    # this one is written under an explicit key naming the document element
    # -- the key becomes <person>, not a discardable wrapper.
    print("-- XML  --");  print(doc({"person": d.to_data()}).to_xml())

    print("\n-- lenient by default --")
    # TOML has no null: the null field is dropped, the null array item too.
    rep = WriteReport()
    out = doc({"a": 1, "b": None, "xs": [1, None, 2]}).to_toml(report=rep)
    print("output:\n" + out.rstrip())
    print("adjustments:")
    for adj in rep:
        print(f"  [{adj.severity}] {adj.path}: {adj.message}")

    print("\n-- inspect before writing (check_*) --")
    rep = check_toml(doc({"xs": [1, None, 2]}).to_data())
    print("safe to write losslessly?", bool(rep))   # False: an error-level drop

    print("\n-- strict: refuse anything lossy --")
    try:
        doc({"xs": [1, None, 2]}).to_toml(strict=True)
    except WriteError as e:
        print("WriteError:", e)


if __name__ == "__main__":
    main()
