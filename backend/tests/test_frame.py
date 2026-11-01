import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from must_sim.frame import EOP, KIND_ACK, KIND_DATA, SOP, Frame, FrameError, FrameParser, encode, xor_checksum


def make(**kw):
    base = dict(command_id=0x31, payload=b"\x01", counter=1, src_id=1, dest_id=2, timestamp=1760264400000000000)
    base.update(kw)
    return Frame(**base)


def test_layout_matches_idd_offsets():
    raw = encode(make(), "little")
    assert raw[0:4] == SOP and raw[-4:] == EOP
    assert len(raw) == 30 + 1  # 26 header + 1 payload + 4 EOP
    assert raw[4] == 1 and raw[5] == 2  # source, then destination
    assert raw[6] == 0 and raw[7] == 0  # source subsystem, destination subsystem
    assert raw[8] == 0 and raw[9] == 0  # source sub-subsystem, destination sub-subsystem
    assert raw[10] == 0x31 and raw[11] == 1  # command ID, then counter
    assert raw[12] == 0x00 and raw[13] == 0x00  # data/ack (0x00), reserved (0x00)
    assert int.from_bytes(raw[14:22], "little") == 1760264400000000000
    assert int.from_bytes(raw[22:26], "little") == 1  # 4-byte length
    assert raw[26] == 0x01  # data packet starts at byte 26


def test_known_frame_bytes():
    raw = encode(make(payload=b"\xAA\xBB"), "little")
    assert raw[0:4] == bytes.fromhex("B1 B1 B1 B1")
    assert raw[4:14] == bytes.fromhex("01 02 00 00 00 00 31 01 00 00")
    assert raw[22:26] == (2).to_bytes(4, "little")
    assert raw[26:28] == b"\xAA\xBB"
    assert raw[28:32] == bytes.fromhex("E1 E1 E1 E1")


def test_roundtrip_both_byte_orders():
    for order in ("big", "little"):
        f = make(payload=b"hello", counter=77, kind=KIND_ACK, timestamp=123456789012345)
        out = FrameParser(order).feed(encode(f, order))
        assert out == [f]


def test_frame_split_across_reads():
    raw = encode(make(payload=bytes(100)), "little")
    p = FrameParser("little")
    got = []
    for k in range(0, len(raw), 7):
        got += p.feed(raw[k : k + 7])
    assert len(got) == 1 and isinstance(got[0], Frame)


def test_two_frames_in_one_read():
    a, b = encode(make(counter=1), "little"), encode(make(counter=2), "little")
    out = FrameParser("little").feed(a + b)
    assert [f.counter for f in out] == [1, 2]


def test_garbage_before_frame_is_reported_then_frame_parsed():
    out = FrameParser("little").feed(b"\x00\x01\x02\x03\x04\x05" + encode(make(), "little"))
    assert isinstance(out[0], FrameError) and isinstance(out[-1], Frame)


def test_missing_eop_resyncs():
    bad = bytearray(encode(make(counter=1), "little"))
    bad[-1] = 0x00
    good = encode(make(counter=2), "little")
    out = FrameParser("little").feed(bytes(bad) + good)
    assert any(isinstance(x, FrameError) for x in out)
    assert [x.counter for x in out if isinstance(x, Frame)] == [2]


def test_counter_wraps_to_one_byte():
    assert encode(make(counter=257), "little")[11] == 1
