"""Simulator subsystem limits (Table 15) and carrier validation.

This file is the single source of truth. The UI loads it from /api/spec, so the
screen and the backend can never disagree about what is allowed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

RF_FREQUENCY_HZ = 2_250_000_000  # L.1
BANDWIDTH_HZ = 100_000_000  # L.2
NUM_CARRIERS = 12  # One channel, up to 12 carriers
NUM_CHANNELS = NUM_CARRIERS  # Alias for backward compatibility
MAX_ACTIVE = 12  # All 12 may be on at once
BIT_RATES_KBPS = [4, 16, 32, 64, 128, 256, 512, 1024, 2048]  # L.8
SUBCARRIER_KHZ = (32, 256)  # L.9
SPREADING_RATE_MCPS = 1.024  # L.11
FRAME_LENGTH_BYTES = (128, 256)  # L.13
POWER_DBM = (-150, 20)  # L.15, 1 dB steps (+20 to -150 dBm)
OFFSET_HZ = (-50_000_000, 50_000_000)  # +-50 MHz about 2.25 GHz in Hz

MODES = ["simulation", "radiation"]  # L.14

# `code` is the value sent in the data packet. `uses` says which settings apply.
WAVEFORMS = {
    "pcm_fsk": dict(code=0, label="PCM/FSK", pcm_code="NRZ-L", uses=dict(bit_rate=True, subcarrier=False, conv_coding=False, frame_length=True)),
    "pcm_psk": dict(code=1, label="PCM/PSK", pcm_code="NRZ-L", uses=dict(bit_rate=True, subcarrier=False, conv_coding=True, frame_length=True)),
    "pcm_psk_pm": dict(code=2, label="PCM/PSK/PM", pcm_code="NRZ-S", uses=dict(bit_rate=True, subcarrier=True, conv_coding=False, frame_length=True)),
    "cdma": dict(code=3, label="CDMA", pcm_code=None, uses=dict(bit_rate=True, subcarrier=False, conv_coding=False, frame_length=True)),
    "iq_data": dict(code=4, label="IQ data", pcm_code=None, uses=dict(bit_rate=False, subcarrier=False, conv_coding=False, frame_length=False)),
}
PCM_CODES = ["NRZ-L", "NRZ-S"]
PCM_CODE_VALUE = {None: 0, "NRZ-L": 0, "NRZ-S": 1}


@dataclass
class Carrier:
    number: int
    enabled: bool = False
    waveform: str = "pcm_psk"
    bit_rate_kbps: int = 256
    subcarrier_khz: int = 0
    pcm_code: str = "NRZ-L"
    conv_coding: bool = True
    frame_length: int = 128
    freq_offset_hz: int = 0
    power_dbm: int = -60

    def as_dict(self) -> dict:
        return asdict(self)


# Alias for backward compatibility
Channel = Carrier


def default_carriers() -> list[dict]:
    """12 carriers spread across the 100 MHz band (-44 MHz to +44 MHz), three switched on."""
    out = []
    for n in range(1, NUM_CARRIERS + 1):
        offset = -44_000_000 + (n - 1) * 8_000_000
        c = Carrier(number=n, freq_offset_hz=offset, conv_coding=True, pcm_code="NRZ-L")
        if n == 1:
            c.enabled, c.waveform, c.bit_rate_kbps = True, "pcm_psk", 256
        elif n == 2:
            c.enabled, c.waveform, c.bit_rate_kbps, c.subcarrier_khz = True, "pcm_psk_pm", 128, 64
            c.pcm_code = "NRZ-S"
        elif n == 3:
            c.enabled, c.waveform, c.bit_rate_kbps = True, "cdma", 128
        out.append(c.as_dict())
    return out


default_channels = default_carriers


def spec_dict() -> dict:
    return dict(
        rf_frequency_hz=RF_FREQUENCY_HZ,
        bandwidth_hz=BANDWIDTH_HZ,
        num_carriers=NUM_CARRIERS,
        num_channels=NUM_CARRIERS,
        max_active=MAX_ACTIVE,
        bit_rates_kbps=BIT_RATES_KBPS,
        subcarrier_khz=list(SUBCARRIER_KHZ),
        spreading_rate_mcps=SPREADING_RATE_MCPS,
        frame_length_bytes=list(FRAME_LENGTH_BYTES),
        power_dbm=list(POWER_DBM),
        offset_hz=list(OFFSET_HZ),
        modes=MODES,
        pcm_codes=PCM_CODES,
        waveforms=[dict(id=k, **v) for k, v in WAVEFORMS.items()],
        default_carriers=default_carriers(),
        default_channels=default_carriers(),
    )


def normalize_carrier(raw: dict) -> tuple[Carrier, list[str]]:
    """Validate one carrier and fill in the settings that follow from the waveform.
    Returns the cleaned carrier and a list of problems."""
    errors: list[str] = []
    raw_num = raw.get("number")
    try:
        n = int(raw_num)
    except (TypeError, ValueError):
        return Carrier(number=0), ["Carrier number is missing."]
    tag = f"Carrier {n}"
    if not 1 <= n <= NUM_CARRIERS:
        errors.append(f"{tag}: carrier number must be 1 to {NUM_CARRIERS}.")

    wf_id = raw.get("waveform", "pcm_psk")
    if wf_id not in WAVEFORMS:
        errors.append(f"{tag}: unknown waveform '{wf_id}'.")
        wf_id = "pcm_psk"
    wf = WAVEFORMS[wf_id]
    uses = wf["uses"]

    def num(key: str, default: int = 0) -> int:
        val = raw.get(key, default)
        if isinstance(val, bool):
            errors.append(f"{tag}: {key.replace('_', ' ')} must be a whole number.")
            return default
        if isinstance(val, float) and not val.is_integer():
            errors.append(f"{tag}: {key.replace('_', ' ')} must be a whole number.")
            return int(val)
        if isinstance(val, str) and ("." in val or "," in val):
            errors.append(f"{tag}: {key.replace('_', ' ')} must be a whole number.")
            return default
        try:
            return int(val)
        except (TypeError, ValueError):
            errors.append(f"{tag}: {key.replace('_', ' ')} must be a whole number.")
            return default

    c = Carrier(number=n, enabled=bool(raw.get("enabled", False)), waveform=wf_id)

    # PCM code is selectable on any waveform (defaults to NRZ-L if unrecognized)
    raw_pcm = raw.get("pcm_code")
    if raw_pcm in ("NRZ-S", "NRZ-L"):
        c.pcm_code = raw_pcm
    elif raw_pcm == 1 or raw_pcm == "1":
        c.pcm_code = "NRZ-S"
    else:
        c.pcm_code = "NRZ-L"

    # Convolutional coding is always on for all waveforms
    c.conv_coding = True

    if uses["bit_rate"]:
        c.bit_rate_kbps = num("bit_rate_kbps", 0)
        if c.bit_rate_kbps not in BIT_RATES_KBPS:
            errors.append(f"{tag}: bit rate {c.bit_rate_kbps} kbps is not allowed. Use one of {', '.join(map(str, BIT_RATES_KBPS))}.")
    else:
        c.bit_rate_kbps = 0

    if uses["subcarrier"]:
        c.subcarrier_khz = num("subcarrier_khz", 0)
        lo, hi = SUBCARRIER_KHZ
        if not lo <= c.subcarrier_khz <= hi:
            errors.append(f"{tag}: subcarrier must be {lo} to {hi} kHz for {wf['label']}.")
    else:
        c.subcarrier_khz = 0

    if uses["frame_length"]:
        c.frame_length = num("frame_length", 0)
        lo, hi = FRAME_LENGTH_BYTES
        if not lo <= c.frame_length <= hi:
            errors.append(f"{tag}: frame length must be {lo} to {hi} bytes.")
    else:
        c.frame_length = 0

    # Frequency offset in Hz: must be whole integer and within +-50,000,000 Hz
    raw_offset = raw.get("freq_offset_hz")
    if raw_offset is None and "freq_offset_khz" in raw:
        raw_offset = raw["freq_offset_khz"] * 1000

    if raw_offset is None:
        errors.append(f"{tag}: frequency offset is missing.")
        c.freq_offset_hz = 0
    elif isinstance(raw_offset, bool):
        errors.append(f"{tag}: frequency offset must be a whole number of Hz.")
        c.freq_offset_hz = 0
    elif isinstance(raw_offset, float) and not raw_offset.is_integer():
        errors.append(f"{tag}: frequency offset must be a whole number of Hz.")
        c.freq_offset_hz = int(raw_offset)
    elif isinstance(raw_offset, str) and ("." in raw_offset or "," in raw_offset):
        errors.append(f"{tag}: frequency offset must be a whole number of Hz.")
        c.freq_offset_hz = 0
    else:
        try:
            c.freq_offset_hz = int(raw_offset)
            lo, hi = OFFSET_HZ
            if not lo <= c.freq_offset_hz <= hi:
                errors.append(f"{tag}: frequency offset must be between {lo:,} and +{hi:,} Hz.")
        except (TypeError, ValueError):
            errors.append(f"{tag}: frequency offset must be a whole number of Hz.")
            c.freq_offset_hz = 0

    # Output power in dBm: whole integer from -150 to +20 dBm
    raw_power = raw.get("power_dbm")
    if raw_power is None:
        errors.append(f"{tag}: output power is missing.")
        c.power_dbm = -60
    elif isinstance(raw_power, bool):
        errors.append(f"{tag}: output power must be a whole number in 1 dB steps.")
        c.power_dbm = -60
    elif isinstance(raw_power, float) and not raw_power.is_integer():
        errors.append(f"{tag}: output power must be a whole number in 1 dB steps.")
        c.power_dbm = int(raw_power)
    elif isinstance(raw_power, str) and ("." in raw_power or "," in raw_power):
        errors.append(f"{tag}: output power must be a whole number in 1 dB steps.")
        c.power_dbm = -60
    else:
        try:
            c.power_dbm = int(raw_power)
            lo, hi = POWER_DBM
            if not lo <= c.power_dbm <= hi:
                errors.append(f"{tag}: output power must be {lo} to +{hi} dBm.")
        except (TypeError, ValueError):
            errors.append(f"{tag}: output power must be a whole number in 1 dB steps.")
            c.power_dbm = -60

    return c, errors


normalize_channel = normalize_carrier


def validate_set(raw_carriers: list[dict]) -> tuple[list[Carrier], list[str]]:
    carriers: list[Carrier] = []
    errors: list[str] = []
    seen: set[int] = set()
    for raw in raw_carriers:
        c, errs = normalize_carrier(raw)
        errors += errs
        if c.number in seen:
            errors.append(f"Carrier {c.number} appears more than once.")
        seen.add(c.number)
        carriers.append(c)
    active = sum(1 for c in carriers if c.enabled)
    if active > MAX_ACTIVE:
        errors.append(f"{active} carriers are switched on. At most {MAX_ACTIVE} can run at the same time.")
    return carriers, errors
