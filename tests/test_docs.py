"""Executable check of the snippets shown in README/docs (run via pytest)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tomllib
import dataspec as ds
from dataspec import Schema, ObjectType, ArrayType, ScalarType, Field, STRING, INTEGER


def test_readme_at_a_glance():
    data = ds.read_json('{"name": "Ann", "age": 30, "tags": ["x", "y"]}')
    assert ds.infer([data]).to_dsl().strip() == \
        "root { name: string, age: integer, tags: [string] }"


def test_readme_compatibility():
    v1 = ds.parse_schema("root { host: string, port: integer }")
    v2 = ds.parse_schema("root { host: string, port: integer, tls?: boolean }")
    assert v1.compatible_with(v2)
    assert not v2.compatible_with(v1)


def test_usage_programmatic_schema():
    s = Schema(ObjectType({
        "name": Field(ScalarType({STRING}), True),
        "age": Field(ScalarType({INTEGER}), False),
    }))
    assert s.validate({"name": "A"}).ok
    assert not s.validate({"age": 1}).ok


def test_formats_null_option_c():
    assert tomllib.loads(ds.write_toml({"a": 1, "b": None})) == {"a": 1}


def test_quickstart_runs():
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, os.path.join(root, "examples", "quickstart.py")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
