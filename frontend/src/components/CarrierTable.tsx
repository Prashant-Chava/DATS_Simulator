import { useStore } from "../store";
import { useCarrierState } from "../lib/hooks";
import { carrierIssues, sameCarrier } from "../lib/rules";
import type { Carrier } from "../types";

export function CarrierTable() {
  const spec = useStore((s) => s.spec)!;
  const carriers = useStore((s) => s.carriers);
  const appliedConfig = useStore((s) => s.appliedConfig);
  const formMode = useStore((s) => s.formMode);
  const status = useStore((s) => s.status)!;
  const busy = useStore((s) => s.busy);
  const edit = useStore((s) => s.editCarrier);
  const send = useStore((s) => s.sendConfig);
  const reset = useStore((s) => s.resetCarriers);
  const allOff = useStore((s) => s.allOff);
  const copyToAll = useStore((s) => s.copyCarrierToAll);
  const cs = useCarrierState();
  const toggle = (c: Carrier) => {
    edit(c.number, { enabled: !c.enabled });
  };
  const num = (v: string) => (v.trim() === "" ? NaN : Number(v));
  const rfOn = status.rf_on !== false;

  const formatFreqHelper = (offsetHz: number) => {
    if (isNaN(offsetHz) || !Number.isInteger(offsetHz)) return "—";
    const absHz = spec.rf_frequency_hz + offsetHz;
    return `= ${(absHz / 1e9).toFixed(9)} GHz`;
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Carriers</h2>
        <span className="meta">
          <span>{cs.active} of {spec.num_carriers} carriers on</span>
          {cs.invalid.length > 0 && <span className="bad"> · {cs.invalid.length} with invalid values</span>}
          {cs.invalid.length === 0 && cs.isDirty && (
            <span className="warnc"> · {cs.neverApplied ? "not sent yet" : "unsent changes"}</span>
          )}
          {cs.invalid.length === 0 && !cs.isDirty && <span className="okc"> · sent to the simulator</span>}
        </span>
        <div className="head-actions">
          <button
            className="btn small ghost"
            onClick={() => copyToAll(1)}
            disabled={!!busy}
            title="Copy Carrier 1 settings to all 12 carriers"
          >
            Copy to all
          </button>
          <button className="btn small ghost" onClick={allOff} disabled={cs.active === 0 || !!busy}>
            All off
          </button>
          <button className="btn small ghost" onClick={reset} disabled={!!busy}>
            Reset
          </button>
        </div>
      </div>
      {rfOn && status.connected && (
        <p className="note">RF is on. Changes apply to the running output as soon as you press Send.</p>
      )}

      <div className="table-wrap">
        <table className="channels">
          <thead>
            <tr>
              <th className="c-n">Carrier</th>
              <th className="c-on">On</th>
              <th>Waveform</th>
              <th>Bit rate (kbps)</th>
              <th>Subcarrier (kHz)</th>
              <th>PCM code</th>
              <th>Conv. coding</th>
              <th>Frame (bytes)</th>
              <th>Frequency offset (Hz)</th>
              <th>Power (dBm)</th>
            </tr>
          </thead>
          <tbody>
            {carriers.map((c) => {
              const wf = spec.waveforms.find((w) => w.id === c.waveform)!;
              const iss = carrierIssues(c, spec);
              const a = appliedConfig?.carriers.find((x) => x.number === c.number);
              const dirty = !a || !sameCarrier(a, c);
              return (
                <tr key={c.number} className={`${c.enabled ? "" : "off"} ${dirty ? "dirty" : ""}`}>
                  <td className="c-n mono">{c.number}</td>
                  <td className="c-on">
                    <button
                      role="switch"
                      aria-checked={c.enabled}
                      aria-label={`Carrier ${c.number} ${c.enabled ? "on" : "off"}`}
                      className={`switch ${c.enabled ? "on" : ""}`}
                      onClick={() => toggle(c)}
                    >
                      <i />
                    </button>
                  </td>
                  <td>
                    <select
                      value={c.waveform}
                      onChange={(e) => edit(c.number, { waveform: e.target.value })}
                      aria-label={`Carrier ${c.number} waveform`}
                    >
                      {spec.waveforms.map((w) => (
                        <option key={w.id} value={w.id}>
                          {w.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    {wf.uses.bit_rate ? (
                      <select
                        value={c.bit_rate_kbps}
                        onChange={(e) => edit(c.number, { bit_rate_kbps: Number(e.target.value) })}
                        className="mono"
                        aria-label={`Carrier ${c.number} bit rate`}
                        aria-invalid={!!iss.bit_rate_kbps}
                      >
                        {spec.bit_rates_kbps.map((b) => (
                          <option key={b} value={b}>
                            {b}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="na">n/a</span>
                    )}
                  </td>
                  <td>
                    {wf.uses.subcarrier ? (
                      <input
                        type="number"
                        className="mono"
                        value={c.subcarrier_khz}
                        min={spec.subcarrier_khz[0]}
                        max={spec.subcarrier_khz[1]}
                        step={1}
                        onChange={(e) => edit(c.number, { subcarrier_khz: num(e.target.value) })}
                        aria-label={`Carrier ${c.number} subcarrier`}
                        aria-invalid={!!iss.subcarrier_khz}
                        title={iss.subcarrier_khz}
                      />
                    ) : (
                      <span className="na">n/a</span>
                    )}
                  </td>
                  <td>
                    <select
                      value={c.pcm_code ?? "NRZ-L"}
                      onChange={(e) => edit(c.number, { pcm_code: e.target.value })}
                      className="mono"
                      aria-label={`Carrier ${c.number} PCM code`}
                    >
                      {(spec.pcm_codes ?? ["NRZ-L", "NRZ-S"]).map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <label className="check" title="Convolutional coding is always on for all waveforms">
                      <input
                        type="checkbox"
                        checked={true}
                        disabled
                        aria-label={`Carrier ${c.number} convolutional coding (always on)`}
                      />
                      <span className="okc">on</span>
                    </label>
                  </td>
                  <td>
                    {wf.uses.frame_length ? (
                      <input
                        type="number"
                        className="mono"
                        value={c.frame_length}
                        min={spec.frame_length_bytes[0]}
                        max={spec.frame_length_bytes[1]}
                        step={1}
                        onChange={(e) => edit(c.number, { frame_length: num(e.target.value) })}
                        aria-label={`Carrier ${c.number} frame length`}
                        aria-invalid={!!iss.frame_length}
                        title={iss.frame_length}
                      />
                    ) : (
                      <span className="na">n/a</span>
                    )}
                  </td>
                  <td>
                    <div className="freq-cell">
                      <input
                        type="number"
                        className="mono"
                        value={isNaN(c.freq_offset_hz) ? "" : c.freq_offset_hz}
                        min={spec.offset_hz[0]}
                        max={spec.offset_hz[1]}
                        step={1}
                        onChange={(e) => edit(c.number, { freq_offset_hz: num(e.target.value) })}
                        aria-label={`Carrier ${c.number} frequency offset`}
                        aria-invalid={!!iss.freq_offset_hz}
                        title={iss.freq_offset_hz}
                      />
                      <span className="freq-helper">{formatFreqHelper(c.freq_offset_hz)}</span>
                    </div>
                  </td>
                  <td>
                    <input
                      type="number"
                      className="mono"
                      value={isNaN(c.power_dbm) ? "" : c.power_dbm}
                      min={spec.power_dbm[0]}
                      max={spec.power_dbm[1]}
                      step={1}
                      onChange={(e) => edit(c.number, { power_dbm: num(e.target.value) })}
                      aria-label={`Carrier ${c.number} power`}
                      aria-invalid={!!iss.power_dbm}
                      title={iss.power_dbm}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export const ChannelTable = CarrierTable;
