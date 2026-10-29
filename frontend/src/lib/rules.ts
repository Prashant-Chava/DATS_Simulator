import type { Carrier, Spec } from "../types";

/** Apply the settings that follow from the waveform, the same way the backend does. */
export function withWaveformRules(ch: Carrier, spec: Spec): Carrier {
  const wf = spec.waveforms.find((w) => w.id === ch.waveform);
  if (!wf) return ch;
  const out: Carrier = { ...ch, pcm_code: ch.pcm_code || "NRZ-L", conv_coding: true };
  if (wf.uses.bit_rate) {
    if (!spec.bit_rates_kbps.includes(out.bit_rate_kbps)) out.bit_rate_kbps = 256;
  } else out.bit_rate_kbps = 0;
  if (wf.uses.subcarrier) {
    if (out.subcarrier_khz < spec.subcarrier_khz[0] || out.subcarrier_khz > spec.subcarrier_khz[1]) out.subcarrier_khz = 64;
  } else out.subcarrier_khz = 0;
  if (wf.uses.frame_length) {
    if (out.frame_length < spec.frame_length_bytes[0] || out.frame_length > spec.frame_length_bytes[1]) out.frame_length = spec.frame_length_bytes[0];
  } else out.frame_length = 0;
  return out;
}

export type Issues = Partial<Record<"bit_rate_kbps" | "subcarrier_khz" | "frame_length" | "freq_offset_hz" | "power_dbm", string>>;

export function carrierIssues(ch: Carrier, spec: Spec): Issues {
  const wf = spec.waveforms.find((w) => w.id === ch.waveform);
  const out: Issues = {};
  if (!wf) return out;
  const int = Number.isInteger;
  if (wf.uses.bit_rate && !spec.bit_rates_kbps.includes(ch.bit_rate_kbps)) out.bit_rate_kbps = `Use one of ${spec.bit_rates_kbps.join(", ")} kbps`;
  const [sl, sh] = spec.subcarrier_khz;
  if (wf.uses.subcarrier && (!int(ch.subcarrier_khz) || ch.subcarrier_khz < sl || ch.subcarrier_khz > sh)) out.subcarrier_khz = `Subcarrier must be ${sl} to ${sh} kHz`;
  const [fl, fh] = spec.frame_length_bytes;
  if (wf.uses.frame_length && (!int(ch.frame_length) || ch.frame_length < fl || ch.frame_length > fh)) out.frame_length = `Frame length must be ${fl} to ${fh} bytes`;
  const [ol, oh] = spec.offset_hz;
  if (!int(ch.freq_offset_hz) || ch.freq_offset_hz < ol || ch.freq_offset_hz > oh) out.freq_offset_hz = `Frequency offset must be a whole number between ${ol.toLocaleString()} and +${oh.toLocaleString()} Hz`;
  const [pl, ph] = spec.power_dbm;
  if (!int(ch.power_dbm) || ch.power_dbm < pl || ch.power_dbm > ph) out.power_dbm = `Power must be ${pl} to +${ph} dBm in 1 dB steps`;
  return out;
}

export const channelIssues = carrierIssues;

export function sameCarrier(a: Carrier, b: Carrier): boolean {
  return (
    a.enabled === b.enabled &&
    a.waveform === b.waveform &&
    a.bit_rate_kbps === b.bit_rate_kbps &&
    a.subcarrier_khz === b.subcarrier_khz &&
    a.pcm_code === b.pcm_code &&
    a.conv_coding === b.conv_coding &&
    a.frame_length === b.frame_length &&
    a.freq_offset_hz === b.freq_offset_hz &&
    a.power_dbm === b.power_dbm
  );
}

export const sameChannel = sameCarrier;

/** Rough occupied bandwidth in kHz, for the band preview only (not a measurement). */
export function occupiedKhz(ch: Carrier, spec: Spec, iqRate?: number | null): number {
  switch (ch.waveform) {
    case "pcm_fsk":
    case "pcm_psk":
      return 2 * ch.bit_rate_kbps;
    case "pcm_psk_pm":
      return 2 * (ch.subcarrier_khz + ch.bit_rate_kbps);
    case "cdma":
      return 2 * spec.spreading_rate_mcps * 1000;
    case "iq_data":
      return iqRate ? (iqRate / 1000) * 0.8 : 2000;
    default:
      return 500;
  }
}
