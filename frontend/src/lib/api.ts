import type { Analysis, Carrier, Mode, Spec, Status } from "../types";

export class ApiError extends Error {
  errors: string[];
  constructor(message: string, errors: string[] = []) {
    super(message);
    this.errors = errors;
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("The simulator backend is not reachable. Start it and reload this page.");
  }
  const text = await res.text();
  let body: any = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    /* not json */
  }
  if (!res.ok) {
    const d = body?.detail;
    if (typeof d === "string") throw new ApiError(d);
    if (d && typeof d === "object" && !Array.isArray(d)) throw new ApiError(d.message ?? "Request failed", d.errors ?? []);
    if (Array.isArray(d)) throw new ApiError("The request has invalid values.", d.map((e: any) => e.msg ?? String(e)));
    throw new ApiError(`Request failed (${res.status})`);
  }
  return body as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export interface ConnectBody {
  protocol: "tcp" | "udp";
  host: string;
  port: number;
  ack_timeout_s?: number;
  byte_order?: "big" | "little";
  ids?: Record<string, number>;
}

export interface SendResult {
  ok: boolean;
  message: string;
  sent: string[];
  failed: string | null;
  not_sent: string[];
  applied_carriers: Carrier[];
}

export interface SendBody {
  mode: Mode;
  clock?: string;
  carriers: Carrier[];
}

export const api = {
  spec: () => call<Spec>("/api/spec"),
  status: () => call<Status>("/api/status"),
  connect: (b: ConnectBody) => call<Status>("/api/connect", json(b)),
  disconnect: () => call<Status>("/api/disconnect", { method: "POST" }),
  reloadConfig: () => call<Status>("/api/config/reload", { method: "POST" }),
  sendConfig: (b: SendBody) => call<SendResult>("/api/send", json(b)),
  setMode: (mode: Mode) => call<{ ack: string } & Status>("/api/mode", json({ mode })),
  setRf: (on: boolean) => call<{ ack: string } & Status>("/api/rf", json({ on })),
  applyCarriers: (carriers: Carrier[]) =>
    call<{ ok: boolean; results: { carrier: number; ack: string }[]; applied: Carrier[]; failed: number[] }>("/api/carriers/apply", json({ carriers })),
  applyChannels: (channels: Carrier[]) =>
    call<{ ok: boolean; results: { carrier: number; ack: string }[]; applied: Carrier[]; failed: number[] }>("/api/carriers/apply", json({ carriers: channels })),
  getWaveform: () => call<Analysis | null>("/api/waveform"),
  uploadWaveform: (file: File, sampleRate?: number) => {
    const f = new FormData();
    f.append("file", file);
    if (sampleRate) f.append("sample_rate", String(sampleRate));
    return call<Analysis>("/api/waveform", { method: "POST", body: f });
  },
  setSampleRate: (sample_rate: number | null) =>
    call<Analysis>("/api/waveform", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sample_rate }) }),
  clearWaveform: () => call<{ ok: boolean }>("/api/waveform", { method: "DELETE" }),
  sendWaveform: (carrier: number) => call<{ ok: boolean; samples: number; chunks: number }>("/api/waveform/send", json({ carrier })),
};
