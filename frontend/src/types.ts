export interface WaveformDef {
  id: string;
  code: number;
  label: string;
  pcm_code: string | null;
  uses: { bit_rate: boolean; subcarrier: boolean; conv_coding: boolean; frame_length: boolean };
}

export interface Carrier {
  number: number;
  enabled: boolean;
  waveform: string;
  bit_rate_kbps: number;
  subcarrier_khz: number;
  pcm_code: string | null;
  conv_coding: boolean;
  frame_length: number;
  freq_offset_hz: number;
  power_dbm: number;
}

export type Channel = Carrier;

export interface Spec {
  rf_frequency_hz: number;
  bandwidth_hz: number;
  num_carriers: number;
  num_channels?: number;
  max_active: number;
  bit_rates_kbps: number[];
  subcarrier_khz: [number, number];
  spreading_rate_mcps: number;
  frame_length_bytes: [number, number];
  power_dbm: [number, number];
  offset_hz: [number, number];
  offset_khz?: [number, number];
  modes: string[];
  pcm_codes?: string[];
  waveforms: WaveformDef[];
  default_carriers: Carrier[];
  default_channels?: Carrier[];
}

export type Mode = "simulation" | "radiation";

export interface Status {
  version?: string;
  connected: boolean;
  protocol: "tcp" | "udp" | null;
  host: string | null;
  port: number | null;
  ack_timeout_s: number;
  byte_order: "big" | "little";
  ids: Record<string, number>;
  commands: Record<string, number>;
  config_path: string;
  mode: Mode;
  clock?: "internal" | "external";
  rf_on: boolean | null; // null = unknown
}

export interface LogEntry {
  id: number;
  ts: string;
  dir: "TX" | "RX" | "SYS" | "ERR";
  summary: string;
  fields: Record<string, string | number>;
  hex: string;
  size: number;
}

export interface FrequencyInfo {
  is_fsk: boolean;
  center: number;
  f_high: number;
  f_low: number;
  deviation: number;
  period_high?: number;
  period_low?: number;
  period?: number;
}

export interface Analysis {
  name: string;
  n_samples: number;
  columns: string;
  has_q: boolean;
  sample_rate: number | null;
  sample_rate_source: "file" | "user" | null;
  duration_s: number | null;
  x_is_time: boolean;
  time: { x: number[]; i: number[]; q: number[] | null; decimated: boolean; points: number; head: { x: number[]; i: number[]; q: number[] | null } };
  spectrum: { freq: number[]; db: number[]; complex: boolean; segment: number; averages: number } | null;
  frequency?: FrequencyInfo | null;
  constellation: { i: number[]; q: number[] } | null;
  stats: { peak: number; rms_i: number; rms_q: number | null; dc_i: number; dc_q: number | null };
  warnings: string[];
}

export interface Toast {
  id: number;
  kind: "error" | "ok" | "warn";
  text: string;
  details?: string[];
}
