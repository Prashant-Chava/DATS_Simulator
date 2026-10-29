import { useEffect, useState } from "react";
import { useStore } from "../store";
import { useCarrierState } from "../lib/hooks";
import { fmtClock } from "../lib/format";

export function AntennaPanel() {
  const status = useStore((s) => s.status)!;
  const spec = useStore((s) => s.spec)!;
  const cs = useCarrierState();
  const onAir = status.mode === "radiation" && status.rf_on === true;
  const [t0, setT0] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (onAir) {
      setT0((v) => v ?? Date.now());
      const id = setInterval(() => setNow(Date.now()), 1000);
      return () => clearInterval(id);
    }
    setT0(null);
  }, [onAir]);

  return (
    <section className="panel panel-radiation">
      <div className="panel-head">
        <h2>Antenna transmission</h2>
      </div>
      <div className={`airstate ${onAir ? "live" : ""}`}>
        <span className="air-dot" aria-hidden="true" />
        <div>
          <b>{onAir ? "Radiating" : status.rf_on === null ? "State unknown" : "Not radiating"}</b>
          <span className="mono">{onAir && t0 ? fmtClock((now - t0) / 1000) : "00:00:00"}</span>
        </div>
      </div>
      <dl className="facts">
        <div>
          <dt>Carriers</dt>
          <dd className="mono">
            {cs.active} of {spec.num_carriers}
          </dd>
        </div>
        <div>
          <dt>Highest power</dt>
          <dd className="mono">{cs.maxPower === null ? "—" : `${cs.maxPower > 0 ? "+" : ""}${cs.maxPower} dBm`}</dd>
        </div>
      </dl>
      <p className="hint">
        Start RF asks for confirmation. It stays disabled until the configuration has been sent to the simulator.
      </p>
      <details className="more">
        <summary>Antenna (Table 15)</summary>
        <ul className="plain">
          <li>Dual polarization, RCP and LCP</li>
          <li>Gain 10 dB or better, 2.2 to 2.3 GHz</li>
          <li>Cross-polar radiation below 32 dB</li>
          <li>Alignment is manual, in 1° steps over three axes</li>
        </ul>
      </details>
    </section>
  );
}
