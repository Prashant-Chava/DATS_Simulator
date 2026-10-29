import { useStore } from "../store";
import { useCarrierState } from "../lib/hooks";

export function SystemPanel() {
  const spec = useStore((s) => s.spec)!;
  const status = useStore((s) => s.status)!;
  const busy = useStore((s) => s.busy);
  const reload = useStore((s) => s.reloadConfig);
  const cs = useCarrierState();
  const { connected } = status;

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>System</h2>
      </div>
      <dl className="facts">
        <div>
          <dt>RF frequency</dt>
          <dd className="mono">{(spec.rf_frequency_hz / 1e9).toFixed(2)} GHz</dd>
        </div>
        <div>
          <dt>Output bandwidth</dt>
          <dd className="mono">{spec.bandwidth_hz / 1e6} MHz</dd>
        </div>
        <div>
          <dt>Carriers on</dt>
          <dd className="mono">
            {cs.active} of {spec.num_carriers}
          </dd>
        </div>
      </dl>

      <details className="more">
        <summary>Command table</summary>
        <table className="mini">
          <tbody>
            {Object.entries(status.commands).map(([k, v]) => (
              <tr key={k}>
                <td>{k}</td>
                <td className="mono">0x{v.toString(16).toUpperCase().padStart(2, "0")}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="hint">Placeholder IDs. Edit <span className="mono">config/commands.json</span>, disconnect, then reload.</p>
        <button className="btn small" onClick={() => void reload()} disabled={connected || !!busy}>Reload command table</button>
      </details>
    </section>
  );
}
