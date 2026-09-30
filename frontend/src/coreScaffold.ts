import type { CoreAtomMode } from "./types";

export const CORE_MODE_ORDER: CoreAtomMode[] = ["exact", "group", "hetero", "any"];

/** Toolbar chip labels (header uses full query text from depict API). */
export const CORE_MODE_CHIP: Record<CoreAtomMode, string> = {
  exact: "Exact",
  group: "Group",
  hetero: "Het",
  any: "Any",
};

export function parseAtomModes(raw: Record<string, string> | undefined): Record<number, CoreAtomMode> {
  const out: Record<number, CoreAtomMode> = {};
  for (const [key, value] of Object.entries(raw ?? {})) {
    const idx = Number(key);
    if (!Number.isFinite(idx)) continue;
    if (CORE_MODE_ORDER.includes(value as CoreAtomMode)) out[idx] = value as CoreAtomMode;
  }
  return out;
}

export function defaultCoreAtomMode(atomicNum: number, aromatic: boolean): CoreAtomMode {
  if (aromatic && [7, 8, 15, 16].includes(atomicNum)) return "group";
  return "exact";
}

export function atomModesPayload(modes: Record<number, CoreAtomMode>): Record<string, string> {
  return Object.fromEntries(Object.entries(modes).map(([k, v]) => [String(k), v]));
}

export function nextCoreAtomMode(current: CoreAtomMode): CoreAtomMode | null {
  const idx = CORE_MODE_ORDER.indexOf(current);
  if (idx < 0 || idx + 1 >= CORE_MODE_ORDER.length) return null;
  return CORE_MODE_ORDER[idx + 1];
}
