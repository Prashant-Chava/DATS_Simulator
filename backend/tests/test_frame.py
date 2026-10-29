import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from must_sim.frame import EOP, KIND_ACK, SOP, Frame, FrameError, FrameParser, encode, xor_checksum


def make(**kw):
    base = dict(command_id=0x01, payload=b"\x01", counter=1, dest_id=2, src_id=1, timestamp=1760264400)
    base.update(kw)
    return Frame(**base)


def test_layout_matches_idd_offsets():
    raw = encode(make(), "big")
    assert raw[0:4] == SOP and raw[-4:] == EOP
    assert len(raw) == 29 + 1
    assert raw[4] == 2 and raw[5] == 1  # destination, then source
    assert raw[10] == 1 and raw[11] == 0x01  # counter, command
    assert raw[12] == 0 and raw[13] == 0xAA  # reserved, data/ack
    assert int.from_bytes(raw[14:22], "big") == 1760264400
    assert int.from_bytes(raw[22:24], "big") == 1
    assert raw[24] == 0x01  # data packet starts at byte 24


def test_checksum_is_xor_of_whole_frame():
    raw = encode(make(payload=bytes(range(10))), "big")
    n = 10
    expected = 0
    for b in raw[: 24 + n]:  # SOP .. last data byte
        expected ^= b
    assert raw[24 + n] == expected
    # SOP and EOP are 4 equal bytes: including them changes nothing
    assert xor_checksum(raw[: 24 + n]) == xor_checksum(raw[: 24 + n] + EOP)


def test_known_frame_bytes():
    """Byte-for-byte frame for RF start with the example values, checksum over the whole frame."""
    raw = encode(make(), "big")
    body = bytes.fromhex("B1B1B1B1 0201 0000 0000 0101 00AA 00000000 68EB80D0 0001 01".replace(" ", ""))
    x = 0
    for b in body:
        x ^= b
    assert raw == body + bytes([x]) + bytes.fromhex("E1E1E1E1")


def test_roundtrip_both_byte_orders():
    for order in ("big", "little"):
        f = make(payload=b"hello", counter=77, kind=KIND_ACK, timestamp=123456789)
        out = FrameParser(order).feed(encode(f, order))
        assert out == [f]


def test_frame_split_across_reads():
    raw = encode(make(payload=bytes(100)), "big")
    p = FrameParser()
    got = []
    for k in range(0, len(raw), 7):
        got += p.feed(raw[k : k + 7])
    assert len(got) == 1 and isinstance(got[0], Frame)


def test_two_frames_in_one_read():
    a, b = encode(make(counter=1), "big"), encode(make(counter=2), "big")
    out = FrameParser().feed(a + b)
    assert [f.counter for f in out] == [1, 2]


def test_garbage_before_frame_is_reported_then_frame_parsed():
    out = FrameParser().feed(b"\x00\x01\x02\x03\x04\x05" + encode(make(), "big"))
    assert isinstance(out[0], FrameError) and isinstance(out[-1], Frame)


def test_bad_checksum_reported_and_next_frame_survives():
    bad = bytearray(encode(make(counter=1), "big"))
    bad[25] ^= 0xFF
    good = encode(make(counter=2), "big")
    out = FrameParser().feed(bytes(bad) + good)
    assert isinstance(out[0], FrameError) and "Checksum" in out[0].message
    assert isinstance(out[1], Frame) and out[1].counter == 2


def test_missing_eop_resyncs():
    bad = bytearray(encode(make(counter=1), "big"))
    bad[-1] = 0x00
    good = encode(make(counter=2), "big")
    out = FrameParser().feed(bytes(bad) + good)
    assert any(isinstance(x, FrameError) for x in out)
    assert [x.counter for x in out if isinstance(x, Frame)] == [2]


def test_counter_wraps_to_one_byte():
    assert encode(make(counter=257), "big")[10] == 1
