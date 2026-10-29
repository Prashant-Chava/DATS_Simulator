import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest

from must_sim import waveform as w


def csv(rows, header=None, sep=","):
    lines = ([sep.join(header)] if header else []) + [sep.join(str(v) for v in r) for r in rows]
    return ("\n".join(lines)).encode()


def tone(n=4096, fs=1e6, f0=100e3):
    t = np.arange(n) / fs
    return np.cos(2 * np.pi * f0 * t), np.sin(2 * np.pi * f0 * t), t


def test_three_columns_time_i_q_gives_rate():
    i, q, t = tone(2000)
    p = w.parse_csv(csv(zip(t, i, q), ["time", "I", "Q"]))
    assert p.columns == "time, I, Q" and p.q is not None
    assert p.file_rate == pytest.approx(1e6, rel=1e-6)


def test_time_unit_from_header():
    i, q, t = tone(500)
    p = w.parse_csv(csv(zip(t * 1e6, i, q), ["time_us", "i", "q"]))
    assert p.file_rate == pytest.approx(1e6, rel=1e-6)


def test_two_columns_and_one_column_and_other_delimiters():
    i, q, _ = tone(100)
    assert w.parse_csv(csv(zip(i, q))).q is not None
    assert w.parse_csv(csv(zip(i, q), sep=";")).q is not None
    assert w.parse_csv(csv(zip(i, q), sep="\t")).q is not None
    assert w.parse_csv(csv(zip(i, q), sep=" ")).q is not None
    one = w.parse_csv(csv([(v,) for v in i]))
    assert one.q is None and len(one.i) == 100


def test_header_names_in_any_order():
    i, q, _ = tone(100)
    p = w.parse_csv(csv(zip(q, i), ["Quadrature", "In-Phase"]))
    assert np.allclose(p.i, i) and np.allclose(p.q, q)


@pytest.mark.parametrize(
    "raw,word",
    [
        (b"", "empty"),
        (b"I,Q\n", "no data"),
        (b"1,2\n3,abc\n", "could not read"),
        (b"1,2\n3,nan\n", "not finite"),
        (b"1,2\n3\n", "could not read"),
        (b"5\n", "at least 2"),
    ],
)
def test_bad_files_give_clear_errors(raw, word):
    with pytest.raises(w.WaveformError) as e:
        w.parse_csv(raw)
    assert word in str(e.value).lower()


def test_spectrum_peak_is_at_the_tone_frequency():
    i, q, _ = tone(8192, 1e6, 100e3)
    a = w.analyze(w.parse_csv(csv(zip(i, q))), sample_rate=1e6)
    f, db = np.array(a["spectrum"]["freq"]), np.array(a["spectrum"]["db"])
    assert f[np.argmax(db)] == pytest.approx(100e3, abs=1e6 / 8192 * 2)
    assert a["spectrum"]["complex"] and db.max() == pytest.approx(0, abs=0.01)


def test_negative_frequency_tone_lands_on_negative_side():
    i, q, _ = tone(8192, 1e6, 100e3)
    a = w.analyze(w.parse_csv(csv(zip(i, -q))), sample_rate=1e6)  # conjugate
    f, db = np.array(a["spectrum"]["freq"]), np.array(a["spectrum"]["db"])
    assert f[np.argmax(db)] < 0


def test_real_only_signal_has_one_sided_spectrum():
    i, _, _ = tone(4096)
    a = w.analyze(w.parse_csv(csv([(v,) for v in i])), sample_rate=1e6)
    assert not a["spectrum"]["complex"] and min(a["spectrum"]["freq"]) >= 0


def test_decimation_keeps_a_single_sample_spike():
    n = 200_000
    i = np.zeros(n)
    i[123_457] = 9.0
    p = w.Parsed(name="x", i=i, q=None, t=None, file_rate=None)
    a = w.analyze(p, 1e6)
    assert a["time"]["decimated"] and a["time"]["points"] <= w.MAX_PLOT_POINTS + 1000
    assert max(a["time"]["i"]) == 9.0
    xs = np.array(a["time"]["x"])
    assert np.isclose(xs[np.argmax(a["time"]["i"])], 123_457 / 1e6)
    assert np.all(np.diff(xs) >= 0)


def test_without_rate_axes_are_samples_and_warns():
    i, q, _ = tone(100)
    a = w.analyze(w.parse_csv(csv(zip(i, q))))
    assert a["sample_rate"] is None and not a["x_is_time"]
    assert any("sample rate" in x.lower() for x in a["warnings"])
    assert a["time"]["x"][:3] == [0.0, 1.0, 2.0]


def test_int16_scaling():
    p = w.Parsed(name="x", i=np.array([0.0, 2.0, -4.0]), q=np.array([1.0, 0.0, 4.0]), t=None, file_rate=None)
    ii, qq, full = w.to_int16(p)
    assert full == 4.0 and ii.tolist() == [0, 16384, -32767] and qq.tolist() == [8192, 0, 32767]
    with pytest.raises(w.WaveformError):
        w.to_int16(w.Parsed(name="z", i=np.zeros(4), q=None, t=None, file_rate=None))


def test_vivado_ila_csv_export():
    ila_text = (
        "Sample in Buffer,Sample in Window,TRIGGER,rfsoc_27dr_bd_i/simulator_top_0_i_out[15:0],rfsoc_27dr_bd_i/simulator_top_0_q_out[15:0],other[31:0]\n"
        "Radix - UNSIGNED,UNSIGNED,UNSIGNED,SIGNED,SIGNED,SIGNED\n"
        "0,0,0,1000,-2000,123456\n"
        "1,1,0,3000,-4000,654321\n"
    )
    p = w.parse_csv(ila_text.encode("utf-8"), name="test_ila.csv")
    assert p.columns == "I, Q"
    assert p.q is not None
    assert np.allclose(p.i, [1000.0, 3000.0])
    assert np.allclose(p.q, [-2000.0, -4000.0])
    a = w.analyze(p, sample_rate=1e6)
    assert a["stats"]["peak"] == 4000.0
    assert a["has_q"] is True


def test_sample_files_if_present():
    samples_dir = os.path.join(os.path.dirname(__file__), "..", "..", "samples")
    for name in ["bpsk.csv", "fsk.csv", "cdma_bpsk.csv"]:
        path = os.path.join(samples_dir, name)
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            raw = f.read()
        p = w.parse_csv(raw, name=name)
        assert p.q is not None
        assert len(p.i) > 100000
        a = w.analyze(p, sample_rate=384e6)
        assert a["has_q"] is True
        assert a["spectrum"] is not None
        assert a["constellation"] is not None
        assert a["stats"]["peak"] > 0
        assert a["frequency"] is not None
        if name == "fsk.csv":
            assert a["frequency"]["is_fsk"] is True
            assert a["frequency"]["f_high"] == pytest.approx(6e6)
            assert a["frequency"]["f_low"] == pytest.approx(3e6)
            assert a["frequency"]["center"] == pytest.approx(4.5e6)
            assert a["frequency"]["deviation"] == pytest.approx(1.5e6)
        elif name in ("bpsk.csv", "cdma_bpsk.csv"):
            assert a["frequency"]["center"] == pytest.approx(4e6)


