#!/usr/bin/env python3
"""Check whether a new schema version is backward-compatible with the old one.

Run: python3 examples/version_check.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataspec import parse_schema


def report(old_text: str, new_text: str, label: str) -> None:
    old = parse_schema(old_text)
    new = parse_schema(new_text)
    safe = old.compatible_with(new)
    print(f"{label}: {'backward-compatible' if safe else 'BREAKING'}")


def main():
    base = "root { host: string, port: integer }"

    report(base, "root { host: string, port: integer, tls?: boolean }",
           "add optional field   ")
    report(base, "root { host: string, port: integer | string }",
           "widen scalar         ")
    report(base, "root { host: string }",
           "remove required field")   # breaking: old docs have `port`
    report(base, "root { host: string, port: string }",
           "retype field         ")   # breaking: integer is not a string


if __name__ == "__main__":
    main()
