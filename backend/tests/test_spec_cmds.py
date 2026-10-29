import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from must_sim import commands as cmd
from must_sim import spec


def carrier(**kw):
    base = dict(number=1, enabled=True, waveform="pcm_psk", bit_rate_kbps=256, frame_length=128, freq_offset_hz=0, power_dbm=-30)
    base.update(kw)
    return base


ch = carrier


def test_valid_carrier_and_derived_fields():
    c, errs = spec.normalize_carrier(carrier(waveform="pcm_psk_pm", subcarrier_khz=64, pcm_code="NRZ-S"))
    assert not errs and c.pcm_code == "NRZ-S" and c.subcarrier_khz == 64
    c, errs = spec.normalize_carrier(carrier(waveform="pcm_psk", subcarrier_khz=99, pcm_code="NRZ-L"))
    assert not errs and c.pcm_code == "NRZ-L" and c.subcarrier_khz == 0 and c.conv_coding is True
    c, _ = spec.normalize_carrier(carrier(waveform="cdma", pcm_code="NRZ-S"))
    assert c.pcm_code == "NRZ-S" and c.conv_coding is True  # selectable on any waveform, convolutional code always on


@pytest.mark.parametrize(
    "bad,word",
    [
        (dict(bit_rate_kbps=100), "bit rate"),
        (dict(waveform="pcm_psk_pm", subcarrier_khz=10), "subcarrier"),
        (dict(frame_length=64), "frame length"),
        (dict(power_dbm=21), "power"),
        (dict(power_dbm=-151), "power"),
        (dict(freq_offset_hz=50_000_001), "offset"),
        (dict(freq_offset_hz=-50_000_001), "offset"),
        (dict(number=13), "carrier number"),
        (dict(number=0), "carrier number"),
        (dict(waveform="nope"), "unknown waveform"),
    ],
)
def test_rejects_out_of_range(bad, word):
    _, errs = spec.normalize_carrier(carrier(**bad))
    assert errs and any(word in e.lower() for e in errs)


def test_frequency_offset_limits_and_non_integers():
    # Exactly at limits: accepted
    for off in (-50_000_000, 50_000_000, 0, -44_000_000, 44_000_000, -12_500_000, 8_000_000):
        c, errs = spec.normalize_carrier(carrier(freq_offset_hz=off))
        assert not errs, f"Unexpected error for offset {off}: {errs}"
        assert c.freq_offset_hz == off

    # Beyond limits: rejected
    for off in (-50_000_001, 50_000_001, -100_000_000, 100_000_000):
        _, errs = spec.normalize_carrier(carrier(freq_offset_hz=off))
        assert errs and any("offset" in e.lower() for e in errs)

    # Non-integers: rejected with a clear message
    for bad_val in (12.5, -12.5, 12500000.5, "12.5", "-12500000.5", "abc", True, False):
        _, errs = spec.normalize_carrier(carrier(freq_offset_hz=bad_val))
        assert errs and any("whole number of hz" in e.lower() for e in errs), f"Did not reject {bad_val} as non-integer: {errs}"


def test_power_limits_accepted_and_rejected():
    for p in (-150, 20, 0, -60):
        assert not spec.normalize_carrier(carrier(power_dbm=p))[1]
    for p in (-151, 21):
        assert spec.normalize_carrier(carrier(power_dbm=p))[1]
    for bad_p in (3.5, "3.5", "loud", True):
        assert spec.normalize_carrier(carrier(power_dbm=bad_p))[1]


def test_all_twelve_active_allowed():
    all_12 = [carrier(number=n, freq_offset_hz=-44_000_000 + (n - 1) * 8_000_000, enabled=True) for n in range(1, 13)]
    carriers, errs = spec.validate_set(all_12)
    assert not errs
    assert len(carriers) == 12 and sum(c.enabled for c in carriers) == 12

    # Duplicates rejected
    dup = [carrier(number=1), carrier(number=1)]
    assert any("more than once" in e for e in spec.validate_set(dup)[1])


def test_carrier_payload_roundtrip_signed_offset_both_byte_orders():
    # Test signed negative offset, positive offset, and power below int8
    test_cases = [
        (-44_000_000, -150, 1),
        (-12_500_000, -60, 2),
        (0, 0, 6),
        (8_000_000, 20, 10),
        (50_000_000, -90, 12),
        (-50_000_000, 10, 7),
    ]
    for off, pwr, num in test_cases:
        c, _ = spec.normalize_carrier(carrier(number=num, waveform="pcm_psk_pm", subcarrier_khz=200, pcm_code="NRZ-S", power_dbm=pwr, freq_offset_hz=off))
        for order in ("big", "little"):
            payload = cmd.carrier_config(c, order)
            assert len(payload) == 17, f"Payload must be 17 bytes, got {len(payload)}"
            d = cmd.decode_carrier(payload, order)
            assert d["number"] == num
            assert d["freq_offset_hz"] == off
            assert d["power_dbm"] == pwr
            assert d["waveform"] == "pcm_psk_pm"
            assert d["pcm_code"] == "NRZ-S"
            assert d["subcarrier_khz"] == 200


def test_iq_payload_sizes():
    p = cmd.iq_data(3, 5, [1, -2, 3], [4, 5, -32768], "big")
    assert len(p) == 7 + 4 * 3
    assert cmd.iq_begin(1, 1_000_000, 5000, "big") == bytes([1]) + (1_000_000).to_bytes(4, "big") + (5000).to_bytes(4, "big")


def test_default_command_table_loads():
    c = cmd.load_config()
    assert c.commands["CARRIER_CONFIG"] == 16 and c.byte_order == "big"
    assert c.command_name(1) == "RF_CONTROL"


def test_default_carriers_respect_limits():
    crs, errs = spec.validate_set(spec.default_carriers())
    assert not errs and len(crs) == 12 and sum(c.enabled for c in crs) == 3
    # Check default carrier offsets (-44 MHz to +44 MHz with 8 MHz steps)
    offsets = [c.freq_offset_hz for c in crs]
    assert offsets[0] == -44_000_000
    assert offsets[-1] == 44_000_000
    assert offsets[1] - offsets[0] == 8_000_000
