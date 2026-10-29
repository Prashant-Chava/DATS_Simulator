import { useEffect } from "react";
import { useStore } from "./store";
import { TopBar } from "./components/TopBar";
import { ConnectionPanel } from "./components/ConnectionPanel";
import { SystemPanel } from "./components/SystemPanel";
import { WaveformSource } from "./components/WaveformSource";
import { AntennaPanel } from "./components/AntennaPanel";
import { VisualizationPanel } from "./components/VisualizationPanel";
import { CarrierTable } from "./components/CarrierTable";
import { PacketLog } from "./components/PacketLog";
import { Toasts } from "./components/Toasts";

export default function App() {
  const init = useStore((s) => s.init);
  const spec = useStore((s) => s.spec);
  const status = useStore((s) => s.status);
  const formMode = useStore((s) => s.formMode);
  const fatal = useStore((s) => s.fatal);

  useEffect(() => {
    void init();
  }, [init]);

  if (fatal)
    return (
      <div className="fatal">
        <h1>DATS Simulator</h1>
        <p>{fatal}</p>
        <button className="btn btn-primary" onClick={() => void init()}>
          Try again
        </button>
      </div>
    );
  if (!spec || !status)
    return (
      <div className="fatal">
        <p>Loading…</p>
      </div>
    );

  const onAir = status.mode === "radiation" && status.rf_on === true;
  return (
    <div className="app" data-mode={formMode} data-onair={onAir}>
      <TopBar />
      <div className="workspace">
        <aside className="rail">
          <ConnectionPanel />
          <SystemPanel />
          {formMode === "simulation" ? <WaveformSource /> : <AntennaPanel />}
        </aside>
        <main className="main">
          <VisualizationPanel />
          <CarrierTable />
          <PacketLog />
        </main>
      </div>
      <Toasts />
    </div>
  );
}
