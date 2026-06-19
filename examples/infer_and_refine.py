#!/usr/bin/env python3
"""Infer a schema from samples, print it as DSL, then refine it by hand.

Run: python3 examples/infer_and_refine.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataspec import infer, parse_schema


def main():
    samples = [
        {"id": 1, "status": "open", "tags": ["a", "b"]},
        {"id": 2, "status": "shipped", "tags": []},
        {"id": 3, "status": "open", "tags": ["c"], "note": "rush"},
    ]

    draft = infer(samples)
    print("Inferred draft:")
    print(draft.to_dsl())

    # The draft is a starting point. We know `status` is really an enum and
    # `id` should be positive-but-that's-not-expressible, so we tighten what we
    # can: turn `status` into an enum.
    refined = parse_schema("""
        root {
            id:     integer,
            status: "open" | "shipped" | "cancelled",
            tags:   [string],
            note?:  string,
        }
    """)
    print("Refined schema still accepts every sample:",
          all(refined.accepts(s) for s in samples))


if __name__ == "__main__":
    main()
