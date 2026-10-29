import { create } from "zustand";
import { api, ApiError, type ConnectBody, type SendBody } from "./lib/api";
import { sameCarrier, withWaveformRules } from "./lib/rules";
import type { Analysis, Carrier, LogEntry, Mode, Spec, Status, Toast } from "./types";

interface AppliedConfig {
  mode: Mode;
  carriers: Carrier[];
}

interface State {
  spec: Spec | null;
  status: Status | null;
  wsOpen: boolean;
  formMode: Mode;
  carriers: Carrier[];
  channels: Carrier[]; // alias
  appliedConfig: AppliedConfig | null;
  applied: Carrier[] | null; // alias
  log: LogEntry[];
  analysis: Analysis | null;
  progress: { done: number; total: number } | null;
  toasts: Toast[];
  busy: string | null;
  fatal: string | null;

  init: () => Promise<void>;
  toast: (kind: Toast["kind"], text: string, details?: string[]) => void;
  dismissToast: (id: number) => void;
  clearLog: () => void;

  connect: (b: ConnectBody) => Promise<void>;
  disconnect: () => Promise<void>;
  reloadConfig: () => Promise<void>;
  setMode: (m: Mode) => void;
  setRf: (on: boolean) => Promise<void>;

  editCarrier: (n: number, patch: Partial<Carrier>) => void;
  editChannel: (n: number, patch: Partial<Carrier>) => void;
  copyCarrierToAll: (sourceNumber?: number) => void;
  resetCarriers: () => void;
  resetChannels: () => void;
  allOff: () => void;
  sendConfig: () => Promise<boolean>;
  applyChannels: () => Promise<boolean>;

  upload: (file: File, rate?: number) => Promise<void>;
  setSampleRate: (hz: number | null) => Promise<void>;
  clearWaveform: () => Promise<void>;
  sendWaveform: (carrier: number) => Promise<void>;
}

let toastId = 0;
let ws: WebSocket | null = null;
let retry = 0;

export const useStore = create<State>((set, get) => {
  const run = async <T,>(label: string, fn: () => Promise<T>): Promise<T | undefined> => {
    set({ busy: label });
    try {
      return await fn();
    } catch (e) {
      const err = e as ApiError;
      get().toast("error", err.message || "Something went wrong", err.errors?.length ? err.errors : undefined);
    } finally {
      set({ busy: null });
    }
    return undefined;
  };

  const openWs = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => {
      retry = 0;
      set({ wsOpen: true });
    };
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === "hello") {
        set({ status: { ...get().status, ...m.status }, log: m.history as LogEntry[] });
      } else if (m.type === "status") {
        set({ status: { ...get().status, ...m.status } });
      } else if (m.type === "log") {
        set({ log: [...get().log, m.entry as LogEntry].slice(-1000) });
      } else if (m.type === "progress") {
        set({ progress: m.done >= m.total || m.finished ? null : { done: m.done, total: m.total } });
      }
    };
    ws.onclose = () => {
      set({ wsOpen: false });
      retry = Math.min(retry + 1, 6);
      setTimeout(openWs, 500 * retry);
    };
  };

  return {
    spec: null,
    status: null,
    wsOpen: false,
    formMode: "simulation",
    carriers: [],
    channels: [],
    appliedConfig: null,
    applied: null,
    log: [],
    analysis: null,
    progress: null,
    toasts: [],
    busy: null,
    fatal: null,

    init: async () => {
      try {
        const [spec, status, analysis] = await Promise.all([api.spec(), api.status(), api.getWaveform()]);
        const crs = spec.default_carriers ?? spec.default_channels ?? [];
        const m = (status.mode as Mode) ?? "simulation";
        set({
          spec,
          status,
          analysis,
          carriers: crs,
          channels: crs,
          formMode: m,
          appliedConfig: null,
          applied: null,
          fatal: null,
        });
        openWs();
      } catch (e) {
        set({ fatal: (e as Error).message });
      }
    },

    toast: (kind, text, details) => {
      const id = ++toastId;
      set({ toasts: [...get().toasts, { id, kind, text, details }] });
      if (kind === "ok") setTimeout(() => get().dismissToast(id), 4000);
    },
    dismissToast: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
    clearLog: () => set({ log: [] }),

    connect: async (b) => {
      const st = await run("Connecting", () => api.connect(b));
      if (!st) return;
      set({ status: st, appliedConfig: null, applied: null });
      if (st.rf_on !== false) {
        get().toast("warn", "RF state is unknown. Press Stop RF to be sure the output is off.");
      }
    },
    disconnect: async () => {
      const st = await run("Disconnecting", () => api.disconnect());
      if (st) set({ status: st });
    },
    reloadConfig: async () => {
      const st = await run("Reloading", () => api.reloadConfig());
      if (st) {
        set({ status: st });
        get().toast("ok", "Command table reloaded.");
      }
    },

    // Selecting mode only changes the form, nothing is sent immediately
    setMode: (m: Mode) => {
      const status = get().status;
      if (status && status.rf_on !== false && status.connected) {
        get().toast("error", "Stop RF before changing the mode.");
        return;
      }
      set({ formMode: m });
    },

    setRf: async (on) => {
      const r = await run(on ? "Starting RF" : "Stopping RF", () => api.setRf(on));
      if (r && r.ack === "timeout") {
        get().toast("warn", `No ACK for ${on ? "Start" : "Stop"} RF. Check the simulator.`);
      }
    },

    editCarrier: (n, patch) => {
      const spec = get().spec;
      if (!spec) return;
      const nextCarriers = get().carriers.map((c) => {
        if (c.number !== n) return c;
        let next = { ...c, ...patch };
        if (patch.waveform && patch.waveform !== c.waveform) next = withWaveformRules(next, spec);
        return next;
      });
      set({ carriers: nextCarriers, channels: nextCarriers });
    },
    editChannel: (n, patch) => get().editCarrier(n, patch),

    resetCarriers: () => {
      const spec = get().spec;
      if (spec) {
        const crs = spec.default_carriers ?? spec.default_channels ?? [];
        set({ carriers: crs, channels: crs });
      }
    },
    resetChannels: () => get().resetCarriers(),

    allOff: () => {
      const off = get().carriers.map((c) => ({ ...c, enabled: false }));
      set({ carriers: off, channels: off });
    },

    copyCarrierToAll: (sourceNumber = 1) => {
      const spec = get().spec;
      if (!spec) return;
      const carriers = get().carriers;
      const src = carriers.find((c) => c.number === sourceNumber) || carriers[0];
      if (!src) return;
      const nextCarriers = carriers.map((c) => {
        let updated: Carrier = {
          ...c,
          enabled: src.enabled,
          waveform: src.waveform,
          bit_rate_kbps: src.bit_rate_kbps,
          subcarrier_khz: src.subcarrier_khz,
          pcm_code: src.pcm_code,
          conv_coding: src.conv_coding,
          frame_length: src.frame_length,
          power_dbm: src.power_dbm,
        };
        updated = withWaveformRules(updated, spec);
        return updated;
      });
      set({ carriers: nextCarriers, channels: nextCarriers });
      get().toast("ok", `Carrier ${src.number} settings copied to all 12 carriers.`);
    },

    sendConfig: async () => {
      const mode = get().formMode;
      const carriers = get().carriers;
      const r = await run("Sending configuration", () => api.sendConfig({ mode, carriers }));
      if (!r) return false;
      if (r.ok) {
        const appliedCarriers = r.applied_carriers ?? carriers;
        const cfg: AppliedConfig = { mode, carriers: appliedCarriers };
        set({ appliedConfig: cfg, applied: appliedCarriers, carriers: appliedCarriers, channels: appliedCarriers });
        get().toast("ok", "Configuration sent and acknowledged by simulator.");
        return true;
      }
      get().toast("warn", r.message);
      if (r.applied_carriers?.length) {
        set({
          appliedConfig: { mode, carriers: r.applied_carriers },
          applied: r.applied_carriers,
        });
      }
      return false;
    },
    applyChannels: () => get().sendConfig(),

    upload: async (file, rate) => {
      const a = await run("Reading file", () => api.uploadWaveform(file, rate));
      if (a) set({ analysis: a });
    },
    setSampleRate: async (hz) => {
      const a = await run("Updating", () => api.setSampleRate(hz));
      if (a) set({ analysis: a });
    },
    clearWaveform: async () => {
      await run("Clearing", () => api.clearWaveform());
      set({ analysis: null });
    },
    sendWaveform: async (carrier) => {
      const r = await run("Sending waveform", () => api.sendWaveform(carrier));
      if (r && r.ok) {
        get().toast("ok", `Waveform sent to carrier ${carrier} (${r.samples.toLocaleString()} samples).`);
      }
    },
  };
});
