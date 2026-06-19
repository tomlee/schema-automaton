#!/usr/bin/env python3
"""Build a Document from scratch with the Doc API, then serialize it.

Shows the "data DOM": construct, navigate, and edit a format-neutral structure
through a guarded API, and emit it to any format on demand.

Run: python3 examples/build_document.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dataspec import DocumentError, doc


def main():
    # Build top-down: create containers, hold cursors, fill them in.
    d = doc()                                  # empty object
    d.add("name", "Ann")
    d.add("age", 30)

    address = d.add_object("address")          # returns a cursor to the new object
    address.add("city", "London")
    address.add("zip", "999")

    tags = d.add_array("tags")                 # returns a cursor to the new array
    tags.append("x")
    tags.append("y")

    print("== built document ==")
    print(d.to_json(indent=2))

    print("\n== navigate (one level at a time) ==")
    print("city:", d.child("address").get("city"))
    print("tags[0]:", d.child("tags").at(0))
    print("keys:", d.keys())

    print("\n== edit: set a scalar, remove a subtree ==")
    d.child("address").set("city", "NY")       # set only modifies a scalar leaf
    d.remove("age")                            # remove drops the whole subtree
    print(d.to_toml())

    print("== the guard prevents malformed data ==")
    for bad in ({1: "x"}, {"f": {1, 2}}):
        try:
            doc(bad)
        except DocumentError as e:
            print("rejected:", e)

    # set() refuses to overwrite a subtree (reshaping must be explicit)
    try:
        d.set("address", "oops")
    except DocumentError as e:
        print("rejected:", e)


if __name__ == "__main__":
    main()
