import { useMemo } from "react";
import { useStore } from "../store";
import { carrierIssues, sameCarrier } from "./rules";

/** Derived facts about the carrier table and form state that several panels need. */
export function useCarrierState() {
  const spec = useStore((s) => s.spec);
  const carriers = useStore((s) => s.carriers);
  const appliedConfig = useStore((s) => s.appliedConfig);
  const formMode = useStore((s) => s.formMode);

  return useMemo(() => {
    const active = carriers.filter((c) => c.enabled);
    const invalid = spec ? carriers.filter((c) => Object.keys(carrierIssues(c, spec)).length > 0).map((c) => c.number) : [];

    const dirtyCarriers = carriers.filter((c) => {
      const a = appliedConfig?.carriers.find((x) => x.number === c.number);
      return !a || !sameCarrier(a, c);
    });

    const isDirty =
      appliedConfig === null ||
      dirtyCarriers.length > 0 ||
      formMode !== appliedConfig.mode;

    const maxPower = active.length ? Math.max(...active.map((c) => c.power_dbm)) : null;

    return {
      active: active.length,
      invalid,
      dirty: dirtyCarriers.map((c) => c.number),
      isDirty,
      neverApplied: appliedConfig === null,
      maxPower,
      overLimit: false, // All 12 may be on simultaneously
    };
  }, [spec, carriers, appliedConfig, formMode]);
}

export const useChannelState = useCarrierState;
