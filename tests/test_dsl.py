"""DSL parse + serialize round-trip."""
import pytest

from dataspec import parse_schema, to_dsl


CASES = [
    "root string",
    "root string?",
    "root integer | string",
    'root "a" | "b" | "c"',
    "root { name: string, age?: integer }",
    "root { a: integer, ... }",
    "root [string]",
    "root [integer]+",
    "root [integer]{2,5}",
    "root [integer]{3}",
    "root { user: { name: string }? }",
    "root { tags: [string], scores: [number]+ }",
    "root { when: datetime, day: date, at: time }",
    "type Point = { x: number, y: number }\nroot { a: Point, b: Point }",
    "type Tree = { value: integer, kids: [Tree] }\nroot Tree",
]


@pytest.mark.parametrize("text", CASES)
def test_round_trip_equivalent(text):
    s = parse_schema(text)
    s2 = parse_schema(to_dsl(s))
    assert s.equivalent(s2), f"\noriginal: {text}\nserialized: {to_dsl(s)}"


def test_to_dsl_readable():
    dsl = to_dsl(parse_schema("root { name: string, age?: integer, tags: [string]+ }"))
    assert "name: string" in dsl
    assert "age?: integer" in dsl
    assert "[string]+" in dsl
