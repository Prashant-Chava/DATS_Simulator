import { useState } from "react";
import { useStore } from "../store";
import { useCarrierState } from "../lib/hooks";
import type { Mode } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";

export function TopBar() {
  const status = useStore((s) => s.status)!;
  const formMode = useStore((s) => s.formMode);
  const busy = useStore((s) => s.busy);
  const wsOpen = useStore((s) => s.wsOpen);
  const setMode = useStore((s) => s.setMode);
  const setRf = useStore((s) => s.setRf);
  const sendConfig = useStore((s) => s.sendConfig);
  const cs = useCarrierState();
  const [ask, setAsk] = useState<null | "send_radiation" | "rf">(null);

  const { connected, rf_on } = status;
  const onAir = status.mode === "radiation" && rf_on === true;

  // Send is blocked if disconnected, busy, any invalid settings, or nothing dirty
  const sendBlocked = !connected || !!busy || cs.invalid.length > 0 || !cs.isDirty;
  const sendHint = !connected
    ? "Connect to the simulator first."
    : cs.invalid.length > 0
    ? "Fix the highlighted carrier settings first."
    : !cs.isDirty
    ? "Settings are already sent to the simulator."
    : "";

  // Start RF is enabled only after a successful Send with no later edits
  const rfBlocked =
    rf_on !== true &&
    rf_on !== null &&
    (!connected || !!busy || cs.isDirty || cs.neverApplied || cs.invalid.length > 0);

  const rfHint = !connected
    ? "Connect to the simulator first."
    : rf_on !== true && cs.invalid.length > 0
    ? "Fix the highlighted carrier settings first."
    : rf_on !== true && (cs.isDirty || cs.neverApplied)
    ? "Send the configuration to the simulator first."
    : "";

  const pickMode = (m: Mode) => {
    if (m === formMode) return;
    setMode(m);
  };

  const pressSend = () => {
    if (sendBlocked) return;
    if (formMode === "radiation") setAsk("send_radiation");
    else void sendConfig();
  };

  const pressRf = () => {
    if (rf_on === true || rf_on === null) {
      void setRf(false);
    } else if (formMode === "radiation") {
      setAsk("rf");
    } else {
      void setRf(true);
    }
  };

  const rfLabel = rf_on === true ? "Stop RF" : rf_on === null ? "Stop RF" : "Start RF";

  return (
    <header className="topbar">
      <div className="brand">
        <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
          <rect width="32" height="32" rx="6" fill="var(--surface-2)" />
          <path
            d="M4 22 L10 22 L13 8 L16 24 L19 12 L22 22 L28 22"
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <h1>DATS Simulator</h1>
      </div>

      <div className="seg" role="radiogroup" aria-label="Mode">
        <button
          role="radio"
          aria-checked={formMode === "simulation"}
          className={formMode === "simulation" ? "on" : ""}
          onClick={() => pickMode("simulation")}
          disabled={!!busy || (rf_on !== false && connected)}
          title={rf_on !== false && connected ? "Stop RF before changing the mode" : ""}
        >
          Simulation
        </button>
        <button
          role="radio"
          aria-checked={formMode === "radiation"}
          className={formMode === "radiation" ? "on" : ""}
          onClick={() => pickMode("radiation")}
          disabled={!connected || !!busy || rf_on !== false}
          title={!connected ? "Connect to the simulator to use Radiation mode" : rf_on !== false ? "Stop RF before changing the mode" : ""}
        >
          Radiation
        </button>
      </div>

      <div className="topbar-right">
        <span className={`pill ${connected ? "pill-ok" : ""}`} role="status">
          <i className="dot" aria-hidden="true" />
          {connected ? `${status.host}:${status.port} ${status.protocol?.toUpperCase()}` : "Not connected"}
          {!wsOpen && <em> · UI offline</em>}
        </span>

        {onAir ? (
          <span className="onair" role="status">
            <i aria-hidden="true" /> On air
          </span>
        ) : rf_on === true ? (
          <span className="pill pill-accent" role="status">
            <i className="dot" aria-hidden="true" /> RF on, not radiating
          </span>
        ) : rf_on === null ? (
          <span className="pill pill-warn" role="status">
            RF state unknown
          </span>
        ) : null}

        <button
          className="btn btn-primary"
          onClick={pressSend}
          disabled={sendBlocked}
          title={sendHint}
        >
          Send
        </button>

        <button
          className={`btn btn-rf ${rf_on === true || rf_on === null ? "btn-stop" : "btn-primary"}`}
          onClick={pressRf}
          disabled={rfBlocked}
          title={rfHint}
        >
          {rfLabel}
        </button>
      </div>

      <ConfirmDialog
        open={ask === "send_radiation"}
        title="Send configuration in Radiation mode?"
        confirmLabel="Send"
        tone="danger"
        onCancel={() => setAsk(null)}
        onConfirm={() => {
          setAsk(null);
          void sendConfig();
        }}
      >
        <p>
          In Radiation mode the simulator will be configured for real transmission through the antenna on {cs.active} carriers. Nothing is transmitted until you press Start RF.
        </p>
      </ConfirmDialog>

      <ConfirmDialog
        open={ask === "rf"}
        title="Start RF in Radiation mode?"
        confirmLabel="Start RF"
        tone="danger"
        onCancel={() => setAsk(null)}
        onConfirm={() => {
          setAsk(null);
          void setRf(true);
        }}
      >
        <p>
          The simulator will transmit on {cs.active} carriers up to {cs.maxPower !== null ? `${cs.maxPower > 0 ? "+" : ""}${cs.maxPower} dBm` : "-60 dBm"} through the antenna.
        </p>
      </ConfirmDialog>
    </header>
  );
}
