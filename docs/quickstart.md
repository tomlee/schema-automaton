# Quickstart

```bash
pip install omnist            # core + JSON
pip install omnist[all]       # + pyyaml, tomli_w, defusedxml -- YAML/TOML-write/XML
```

The shortest possible tour -- one OML snippet, one schema, one validation,
one inference. For the fuller order/address/line-item walkthrough, see
[A real-life example](example.md).

```python
from omnist import Doc, parse_schema, infer, doc

# 1. A document, in OML -- omnist's own format (see formats/oml.md)
d = Doc.from_oml('name: "Ann"')

# 2. A schema, in OSD (see schema.md)
s = parse_schema('record Person { "name": string }\nroot Person')

# 3. Validate the document against the schema
s.validate(d).ok    # True

# 4. Infer a schema from example documents instead of writing one by hand
infer([doc({"name": "Ann"}), doc({"name": "Bo"})]).to_osd()
# 'record Root {\n    "name": string,\n}\nroot Root\n'
```

That's it -- a Document, a Schema, `validate()`, and `infer()`. From here:

- [User guide](guide.md) -- the full practical tour.
- [A real-life example](example.md) -- a multi-field order schema across formats.
- [The Schema model & OSD](schema.md) -- OSD in depth.
- [docs/layout.md](layout.md) -- how the repo itself is organized.
