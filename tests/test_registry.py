"""The format registry: built-ins plus registering a new format as a plugin."""
import threading

import pytest

from dataspec import (
    Doc,
    Format,
    WriteError,
    WriteReport,
    doc,
    finish_write,
    formats,
    get_format,
    register_format,
)


class TestRegistry:
    def test_builtins_registered(self):
        assert set(formats()) >= {"json", "yaml", "toml", "xml"}

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError):
            get_format("does-not-exist")

    def test_get_returns_format(self):
        fmt = get_format("json")
        assert fmt.name == "json" and ".json" in fmt.extensions


class TestPluginFormat:
    def test_register_and_use_a_new_format(self):
        # a trivial "lines" format: one scalar per line, objects/arrays unsupported
        def read(text):
            return [int(x) for x in text.split() if x]

        def write(data, *, strict=False, report=None, **opts):
            return " ".join(str(x) for x in data)

        def check(data, **opts):
            return WriteReport()

        register_format(Format("lines", read, write, check, (".lines",)))

        assert "lines" in formats()
        d = Doc.from_format("lines", "1 2 3")
        assert d.to_data() == [1, 2, 3]
        assert d.to_format("lines") == "1 2 3"

    def test_doc_dispatches_through_registry(self):
        # to_format on an unknown name surfaces the registry error
        with pytest.raises(KeyError):
            doc({"a": 1}).to_format("nope")

    def test_concurrent_registration_does_not_corrupt_the_registry(self):
        # Registering from many threads at once must not raise or drop an
        # entry -- register_format/get_format/formats() share a lock.
        def read(text):
            return text

        def write(data, **opts):
            return str(data)

        def check(data, **opts):
            return WriteReport()

        names = [f"concurrent-{i}" for i in range(50)]
        errors = []

        def register(name):
            try:
                register_format(Format(name, read, write, check))
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=register, args=(n,)) for n in names]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert set(names) <= set(formats())
        for name in names:
            assert get_format(name).name == name


class TestFinishWrite:
    def test_lenient_returns_text_regardless_of_adjustments(self):
        rep = WriteReport()
        rep.add("$.a", "some.code", "adjusted", "warning")
        assert finish_write("text", rep) == "text"

    def test_report_collects_adjustments_without_raising(self):
        rep = WriteReport()
        rep.add("$.a", "some.code", "adjusted", "error")
        collected = WriteReport()
        assert finish_write("text", rep, report=collected) == "text"
        assert collected.adjustments == rep.adjustments

    def test_strict_raises_on_any_adjustment_regardless_of_severity(self):
        rep = WriteReport()
        rep.add("$.a", "some.code", "adjusted", "warning")
        with pytest.raises(WriteError) as exc_info:
            finish_write("text", rep, strict=True)
        assert exc_info.value.report is rep

    def test_strict_passes_through_when_no_adjustments(self):
        assert finish_write("text", WriteReport(), strict=True) == "text"
