import string

from observeagents.ids import new_span_id, new_trace_id

_HEX = set(string.hexdigits.lower())


def test_trace_id_is_32_hex():
    tid = new_trace_id()
    assert len(tid) == 32 and set(tid) <= _HEX


def test_span_id_is_16_hex():
    sid = new_span_id()
    assert len(sid) == 16 and set(sid) <= _HEX


def test_ids_are_unique():
    assert len({new_trace_id() for _ in range(100)}) == 100
    assert len({new_span_id() for _ in range(100)}) == 100
