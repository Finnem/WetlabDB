import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type DragEvent, type PointerEvent } from "react";
import { api } from "../api";
import CoreReferencePanel from "../components/CoreReferencePanel";
import ClickableMol from "../components/ClickableMol";
import {
  atomModesPayload,
  CORE_MODE_CHIP,
  CORE_MODE_ORDER,
  defaultCoreAtomMode,
  nextCoreAtomMode,
  parseAtomModes,
} from "../coreScaffold";
import type {
  Compound,
  SarAssayField,
  SeriesSnapshot,
  AlignmentRunResult,
  AlignmentProjectRecord,
  AlignmentProjectSummary,
  CorePreviewResult,
  CoreAtomMode,
  DepictAtom,
} from "../types";

function compoundName(doc: Compound): string {
  const name = doc.Name;
  if (name != null && String(name).trim()) return String(name);
  return "Untitled";
}

function compoundSmiles(doc: Compound): string {
  return String(doc.SMILES ?? "").trim();
}

const LIVE_ALIGN_MAX = 15;

/** One ChemDraw page: A4 with 36 pt margins. Drawing area 523.32 × 769.92 pt. */
const CHEMDRAW_PAGE = {
  drawWidthPt: 523.32,
  drawHeightPt: 769.92,
  marginPt: 36,
};

type AlignProgress = { phase: string; done: number; total: number };

function alignProgressLabel(progress: AlignProgress): string {
  const { phase, done, total } = progress;
  if (phase === "ingest") return total ? `Reading structures ${done}/${total}` : "Reading structures…";
  if (phase === "mapping") return total ? `Matching scaffolds ${done}/${total}` : "Matching scaffolds…";
  if (phase === "optimize") return "Choosing consistent mappings…";
  if (phase === "layout") return total ? `Aligning structures ${done}/${total}` : "Aligning…";
  return "Aligning…";
}

function alignProgressPct(progress: AlignProgress): number | null {
  if (progress.phase === "optimize" || progress.total <= 0) return null;
  const stages = ["ingest", "mapping", "layout"];
  const idx = stages.indexOf(progress.phase);
  if (idx < 0) return null;
  const slice = 1 / stages.length;
  return Math.min(99, Math.round((idx + progress.done / progress.total) * slice * 100));
}

function previewColumnCount(figure: HTMLElement | null): number | undefined {
  if (!figure) return undefined;
  const cards = Array.from(figure.querySelectorAll<HTMLElement>(".export-mol"));
  if (!cards.length) return undefined;
  const y0 = cards[0].getBoundingClientRect().top;
  const slop = Math.max(12, cards[0].getBoundingClientRect().height * 0.2);
  let count = 0;
  for (const card of cards) {
    if (Math.abs(card.getBoundingClientRect().top - y0) > slop) break;
    count += 1;
  }
  return count || undefined;
}

const MODE_LABEL: Record<string, string> = {
  same_scaffold: "Fixed core",
  ring_atom_replacements: "Ring C/N",
  scaffold_replacement: "Scaffold replacement",
};

function formatWhen(iso: string): string {
  if (!iso) return "";
  const stamp = new Date(iso);
  if (Number.isNaN(stamp.getTime())) return iso;
  return stamp.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function humanizeMatchIssue(raw: string): string {
  const text = raw.trim();
  const lower = text.toLowerCase();
  if (lower.includes("core not found") || lower.includes("missing core")) return "Core not found";
  if (lower.includes("invalid core")) return "Invalid core";
  if (lower.includes("unparseable")) return "Could not parse";
  if (lower.includes("identity changed")) return "Could not keep identity";
  if (!text) return "Did not match";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function parseMatchIssueLine(line: string): [string, string] | null {
  const trimmed = line.trim();
  const refMissing = trimmed.match(/^reference\s+(\S+)\s+missing core/i);
  if (refMissing) return [refMissing[1], "Core not found"];
  const missingRef = trimmed.match(/^missing reference\s+(\S+)/i);
  if (missingRef) return [missingRef[1], "Missing reference"];
  const unparseable = trimmed.match(/^unparseable structure:\s+(\S+)/i);
  if (unparseable) return [unparseable[1], "Could not parse"];
  const colon = trimmed.indexOf(":");
  if (colon <= 0) return null;
  const id = trimmed.slice(0, colon).trim();
  const reason = trimmed.slice(colon + 1).trim();
  if (!id || id.toLowerCase() === "unparseable structure") return null;
  return [id, humanizeMatchIssue(reason)];
}

function unmatchedReasons(result: AlignmentRunResult | null): Map<string, string> {
  const map = new Map<string, string>();
  if (!result) return map;
  const details = result.details ?? {};
  const blob = `${result.user_message || ""} ${asStringList(details.errors).join(" ")}`.toLowerCase();
  let fallback = "Did not match";
  if (blob.includes("unparseable")) fallback = "Could not parse";
  else if (blob.includes("core not found") || blob.includes("missing core")) fallback = "Core not found";
  else if (blob.includes("identity changed")) fallback = "Could not keep identity";
  for (const line of asStringList(details.errors)) {
    const parsed = parseMatchIssueLine(line);
    if (parsed) map.set(parsed[0], parsed[1]);
  }
  for (const id of asStringList(details.unmatched)) {
    if (!map.has(id)) map.set(id, fallback);
  }
  if (map.size === 0 && result.user_message) {
    for (const part of result.user_message.split(";")) {
      const parsed = parseMatchIssueLine(part);
      if (parsed) map.set(parsed[0], parsed[1]);
    }
  }
  return map;
}

function isFailedAlign(status: string): boolean {
  const value = status.toUpperCase();
  return value.includes("INFEASIBLE") || value === "UNSUPPORTED";
}

function globalAlignIssue(result: AlignmentRunResult | null): string {
  if (!result) return "Did not match";
  for (const line of asStringList(result.details?.errors)) {
    if (!parseMatchIssueLine(line) && line.trim()) return humanizeMatchIssue(line);
  }
  if (result.unsupported_reason) return humanizeMatchIssue(result.unsupported_reason);
  return "Did not match";
}

function alignKicker(
  result: AlignmentRunResult | null,
  unmatchedCount: number
): { text: string; fail: boolean } | null {
  if (!result) return null;
  const status = result.status.toUpperCase();
  if (status === "OPTIMAL" || status === "VALID") return { text: "Aligned", fail: false };
  if (status.includes("INFEASIBLE")) {
    if (unmatchedCount === 1) return { text: "1 unmatched", fail: true };
    if (unmatchedCount > 1) return { text: `${unmatchedCount} unmatched`, fail: true };
    return { text: "Could not align", fail: true };
  }
  if (status === "UNSUPPORTED") {
    return { text: result.unsupported_reason || "Needs a core", fail: true };
  }
  return null;
}

export default function Alignment({
  db,
  coll,
  initialSelectedIds,
  onClose,
}: {
  db: string;
  coll: string;
  initialSelectedIds: string[];
  onClose: () => void;
}) {
  const [compounds, setCompounds] = useState<Compound[]>([]);
  const [listQuery, setListQuery] = useState("");
  const [assayFields, setAssayFields] = useState<SarAssayField[]>([]);
  const [selectedAssays, setSelectedAssays] = useState<Set<string>>(() => new Set());
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set(initialSelectedIds));
  const [names, setNames] = useState<Record<string, string>>({});
  const [snapshot, setSnapshot] = useState<SeriesSnapshot | null>(null);
  const [alignResult, setAlignResult] = useState<AlignmentRunResult | null>(null);
  const [savedProject, setSavedProject] = useState<AlignmentProjectRecord | null>(null);
  const [referenceId, setReferenceId] = useState("");
  const [coreSmarts, setCoreSmarts] = useState("");
  const [coreAtoms, setCoreAtoms] = useState<number[]>([]);
  const [coreAtomModes, setCoreAtomModes] = useState<Record<number, CoreAtomMode>>({});
  const [lastCoreAtom, setLastCoreAtom] = useState<number | null>(null);
  const [corePreview, setCorePreview] = useState<CorePreviewResult | null>(null);
  const [editSmarts, setEditSmarts] = useState(false);
  const [scaffoldOn, setScaffoldOn] = useState(false);
  const [rotateOn, setRotateOn] = useState(false);
  const [ignoreBondOrder, setIgnoreBondOrder] = useState(false);
  const [scaffoldElementMode, setScaffoldElementMode] = useState<
    "from_smarts" | "element_agnostic"
  >("from_smarts");
  const [rotationDeg, setRotationDeg] = useState(0);
  const [alignMode, setAlignMode] = useState<
    "same_scaffold" | "ring_atom_replacements" | "scaffold_replacement"
  >("same_scaffold");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [molExporting, setMolExporting] = useState(false);
  const [liveAligning, setLiveAligning] = useState(false);
  const [alignProgress, setAlignProgress] = useState<AlignProgress | null>(null);
  const [poseById, setPoseById] = useState<Record<string, string>>({});
  const [recentProjects, setRecentProjects] = useState<AlignmentProjectSummary[]>([]);
  const rotateDrag = useRef<{ x: number; deg: number } | null>(null);
  const rotationDegRef = useRef(0);
  const userCoreRef = useRef(false);
  const skipLiveAlignRef = useRef(false);
  const selectedListRef = useRef<Compound[]>([]);
  const poseByIdRef = useRef<Record<string, string>>({});
  const figureRef = useRef<HTMLDivElement>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  const pageContentRef = useRef<HTMLDivElement>(null);
  const pageZoomRef = useRef(1);
  const [pageZoom, setPageZoom] = useState(1);
  const [pageSlot, setPageSlot] = useState({ width: 0, height: 0 });
  const [figureOrder, setFigureOrder] = useState<string[]>([]);
  const [orderTouched, setOrderTouched] = useState(false);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dropHint, setDropHint] = useState<{ id: string; after: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.compounds(db, coll), api.sarAssayFields()])
      .then(([compoundBody, assayBody]) => {
        if (cancelled) return;
        setCompounds(compoundBody.compounds);
        const nextNames: Record<string, string> = {};
        for (const doc of compoundBody.compounds) nextNames[doc._id] = compoundName(doc);
        setNames(nextNames);
        setAssayFields(assayBody.assay_fields);
        const first = initialSelectedIds[0] || compoundBody.compounds[0]?._id || "";
        setReferenceId(first);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [db, coll, initialSelectedIds]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const selectedList = useMemo(() => {
    const byId = new Map(compounds.map((c) => [c._id, c]));
    const selected = [...selectedIds].filter((id) => byId.has(id));
    const nameOf = (id: string) => {
      const doc = byId.get(id);
      const named = names[id] ?? (doc ? compoundName(doc) : id);
      return named.trim().toLowerCase();
    };
    const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
    if (!orderTouched) {
      selected.sort((a, b) => collator.compare(nameOf(a), nameOf(b)));
    } else {
      const rank = new Map(figureOrder.map((id, i) => [id, i]));
      selected.sort((a, b) => {
        const ia = rank.has(a) ? rank.get(a)! : Number.MAX_SAFE_INTEGER;
        const ib = rank.has(b) ? rank.get(b)! : Number.MAX_SAFE_INTEGER;
        if (ia !== ib) return ia - ib;
        return collator.compare(nameOf(a), nameOf(b));
      });
    }
    return selected.map((id) => byId.get(id)!);
  }, [compounds, selectedIds, figureOrder, orderTouched, names]);
  selectedListRef.current = selectedList;
  poseByIdRef.current = poseById;

  useEffect(() => {
    if (referenceId && selectedIds.has(referenceId)) return;
    setReferenceId([...selectedIds][0] ?? "");
  }, [selectedIds, referenceId]);

  const filteredList = useMemo(() => {
    const q = listQuery.trim().toLowerCase();
    if (!q) return compounds;
    return compounds.filter((c) => {
      const name = (names[c._id] ?? compoundName(c)).toLowerCase();
      const smiles = compoundSmiles(c).toLowerCase();
      return name.includes(q) || smiles.includes(q);
    });
  }, [compounds, listQuery, names]);

  const matchById = useMemo(() => {
    const map = new Map<string, number[]>();
    for (const row of corePreview?.matches ?? []) map.set(row.id, row.atom_indices);
    return map;
  }, [corePreview]);

  useEffect(() => {
    if (!selectedIds.size) {
      setSnapshot(null);
      return;
    }
    const handle = window.setTimeout(() => {
      api
        .sarSnapshot(db, coll, [...selectedAssays], [...selectedIds])
        .then(setSnapshot)
        .catch((err) => setError(String(err)));
    }, 160);
    return () => window.clearTimeout(handle);
  }, [db, coll, selectedIds, selectedAssays]);

  useEffect(() => {
    if (alignMode !== "same_scaffold" || !selectedList.length || !referenceId) return;
    const ref = selectedList.find((c) => c._id === referenceId);
    const smiles = ref ? compoundSmiles(ref) : "";
    if (!smiles) {
      setCorePreview(null);
      if (!editSmarts && !coreAtoms.length) setCoreSmarts("");
      return;
    }
    const handle = window.setTimeout(() => {
      api
        .sarCorePreview({
          reference_smiles: smiles,
          core_atoms: coreAtoms,
          atom_modes: atomModesPayload(coreAtomModes),
          ignore_bond_order: ignoreBondOrder,
          molecules: selectedList.map((c) => ({
            id: c._id,
            smiles: compoundSmiles(c),
          })),
        })
        .then((preview) => {
          setCorePreview(preview);
          if (!editSmarts && preview.connected && preview.smarts) {
            setCoreSmarts(preview.smarts);
            setCoreAtomModes(parseAtomModes(preview.atom_modes));
          }
          if (preview.connected === false && preview.message) setError(preview.message);
        })
        .catch((err) => setError(String(err)));
    }, 120);
    return () => window.clearTimeout(handle);
  }, [
    alignMode,
    selectedList,
    referenceId,
    coreAtoms,
    coreAtomModes,
    editSmarts,
    ignoreBondOrder,
  ]);

  const referenceSmiles = useMemo(() => {
    const ref = selectedList.find((c) => c._id === referenceId);
    return ref ? compoundSmiles(ref) : "";
  }, [selectedList, referenceId]);

  const selectionKey = useMemo(
    () => selectedList.map((c) => `${c._id}:${compoundSmiles(c)}`).join("|"),
    [selectedList]
  );
  const assayKey = useMemo(() => [...selectedAssays].sort().join(","), [selectedAssays]);

  useEffect(() => {
    if (alignMode !== "same_scaffold" || editSmarts || userCoreRef.current) return;
    if (!selectionKey) return;
    let cancelled = false;
    const handle = window.setTimeout(() => {
      api
        .sarGuessCore({
          reference_id: referenceId || undefined,
          ignore_bond_order: ignoreBondOrder,
          molecules: selectedList.map((c) => ({
            id: c._id,
            smiles: compoundSmiles(c),
          })),
        })
        .then((guess) => {
          if (cancelled || userCoreRef.current || !guess.smarts) return;
          setCoreAtoms(guess.core_atoms);
          setCoreAtomModes(parseAtomModes(guess.atom_modes));
          setCoreSmarts(guess.smarts);
        })
        .catch((err) => {
          if (!cancelled) setError(String(err));
        });
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [alignMode, editSmarts, selectionKey, referenceId, ignoreBondOrder]);

  useEffect(() => {
    if (!selectionKey || selectedList.length > LIVE_ALIGN_MAX) return;
    if (!referenceId) return;
    if (alignMode === "same_scaffold" && !coreSmarts.trim()) return;
    if (skipLiveAlignRef.current) return;
    let cancelled = false;
    const handle = window.setTimeout(() => {
      setLiveAligning(true);
      api
        .sarRunAlignment({
          project_id: db,
          series_id: coll,
          compound_ids: selectedList.map((c) => c._id),
          assay_ids: [...selectedAssays],
          reference_id: referenceId,
          mode: "same_scaffold",
          core_smarts: coreSmarts.trim() || undefined,
          ignore_bond_order: ignoreBondOrder,
          scaffold_element_mode: scaffoldElementMode,
          poses: Object.entries(poseByIdRef.current)
            .filter(([, block]) => Boolean(block?.trim()))
            .map(([id, molblock]) => ({ id, molblock })),
        })
        .then((result) => {
          if (cancelled) return;
          adoptAlignment(result);
          setSavedProject(null);
        })
        .catch((err) => {
          if (!cancelled) {
            adoptAlignment(null);
            setError(String(err));
          }
        })
        .finally(() => {
          if (!cancelled) setLiveAligning(false);
        });
    }, 450);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [db, coll, selectionKey, referenceId, coreSmarts, alignMode, assayKey, ignoreBondOrder, scaffoldElementMode]);

  useLayoutEffect(() => {
    const viewport = figureRef.current;
    const page = pageRef.current;
    if (!viewport || !page || selectedList.length === 0) {
      pageZoomRef.current = 1;
      setPageZoom(1);
      setPageSlot({ width: 0, height: 0 });
      return;
    }

    const fit = () => {
      const nativeW = page.offsetWidth;
      const nativeH = page.offsetHeight;
      if (nativeW < 40 || nativeH < 40) return;
      const next = (viewport.clientWidth - 24) / nativeW;
      const zoom = Number.isFinite(next) && next > 0 ? Math.min(1, next) : 1;
      pageZoomRef.current = zoom;
      setPageZoom((prev) => (Math.abs(prev - zoom) < 1e-4 ? prev : zoom));
      setPageSlot((prev) => {
        const width = nativeW * zoom;
        const height = nativeH * zoom;
        if (Math.abs(prev.width - width) < 0.5 && Math.abs(prev.height - height) < 0.5) return prev;
        return { width, height };
      });
    };

    const ro = new ResizeObserver(() => window.requestAnimationFrame(fit));
    ro.observe(viewport);
    ro.observe(page);
    fit();
    return () => ro.disconnect();
  }, [selectedList.length, poseById, names, figureOrder]);

  useEffect(() => {
    if (selectedIds.size) return;
    setFigureOrder([]);
    setOrderTouched(false);
  }, [selectedIds.size]);

  function toggleSelected(id: string, checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
    if (!checked) {
      if (id === referenceId) {
        const remaining = [...selectedIds].filter((item) => item !== id);
        setReferenceId(remaining[0] ?? "");
        if (!coreSmarts.trim()) {
          setCoreAtoms([]);
          setCoreAtomModes({});
        }
      }
    } else if (!referenceId) {
      setReferenceId(id);
    }
  }

  function applyFigureOrder(fromId: string, toId: string, after: boolean) {
    const ids = selectedListRef.current.map((doc) => doc._id);
    const from = ids.indexOf(fromId);
    const to = ids.indexOf(toId);
    if (from < 0 || to < 0 || fromId === toId) return;
    const next = ids.filter((id) => id !== fromId);
    const insertAt = next.indexOf(toId) + (after ? 1 : 0);
    next.splice(insertAt, 0, fromId);
    setOrderTouched(true);
    setFigureOrder(next);
  }

  function onMolDragStart(event: DragEvent<HTMLElement>, id: string) {
    const target = event.target as HTMLElement;
    if (target.closest("input, button, textarea, a")) {
      event.preventDefault();
      return;
    }
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", id);
    setDraggingId(id);
  }

  function onMolDragOver(event: DragEvent<HTMLElement>, id: string) {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    if (!draggingId || draggingId === id) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const after = event.clientX > rect.left + rect.width / 2;
    setDropHint((prev) => (prev?.id === id && prev.after === after ? prev : { id, after }));
  }

  function onMolDrop(event: DragEvent<HTMLElement>, id: string) {
    event.preventDefault();
    const fromId = event.dataTransfer.getData("text/plain") || draggingId;
    if (!fromId) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const after = event.clientX > rect.left + rect.width / 2;
    applyFigureOrder(fromId, id, after);
    setDraggingId(null);
    setDropHint(null);
  }

  function onMolDragEnd() {
    setDraggingId(null);
    setDropHint(null);
  }

  function toggleAssay(id: string) {
    setSelectedAssays((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleCoreAtom(idx: number, atom: DepictAtom) {
    userCoreRef.current = true;
    setLastCoreAtom(idx);
    setCoreAtoms((prev) => {
      if (prev.includes(idx)) {
        const mode = coreAtomModes[idx] ?? defaultCoreAtomMode(atom.atomic_num, atom.aromatic);
        const nextMode = nextCoreAtomMode(mode);
        if (nextMode) {
          setCoreAtomModes((modes) => ({ ...modes, [idx]: nextMode }));
          setError("");
          return prev;
        }
        setCoreAtomModes((modes) => {
          const copy = { ...modes };
          delete copy[idx];
          return copy;
        });
        setError("");
        const next = prev.filter((i) => i !== idx);
        if (!next.length) setLastCoreAtom(null);
        return next;
      }
      if (prev.length && !atom.neighbors.some((n) => prev.includes(n))) {
        setError("Grow the core by clicking an atom bonded to the current selection.");
        return prev;
      }
      setError("");
      setCoreAtomModes((modes) => ({
        ...modes,
        [idx]: defaultCoreAtomMode(atom.atomic_num, atom.aromatic),
      }));
      return [...prev, idx];
    });
  }

  function setCoreAtomMode(idx: number, mode: CoreAtomMode) {
    if (!coreAtoms.includes(idx)) return;
    userCoreRef.current = true;
    setCoreAtomModes((prev) => ({ ...prev, [idx]: mode }));
    setLastCoreAtom(idx);
  }

  async function generalizeFromAnalog(compoundId: string, atomIdx: number) {
    if (!referenceSmiles || !coreAtoms.length) {
      setError("Select a core on the reference first.");
      return;
    }
    const analog = selectedList.find((c) => c._id === compoundId);
    if (!analog) return;
    userCoreRef.current = true;
    setError("");
    try {
      const body = await api.sarCoreAnalogGeneralize({
        reference_smiles: referenceSmiles,
        core_atoms: coreAtoms,
        atom_modes: atomModesPayload(coreAtomModes),
        analog_smiles: compoundSmiles(analog),
        analog_atom_index: atomIdx,
        ignore_bond_order: ignoreBondOrder,
      });
      if (!body.ok) {
        setError(body.message || "Could not generalize from that atom");
        return;
      }
      setCoreAtoms(body.core_atoms);
      setCoreAtomModes(parseAtomModes(body.atom_modes));
      if (body.mapped_ref_atom != null) setLastCoreAtom(body.mapped_ref_atom);
    } catch (err) {
      setError(String(err));
    }
  }

  async function promoteToReference(id: string) {
    if (id === referenceId) return;
    const doc = selectedList.find((c) => c._id === id);
    if (!doc) return;
    const smiles = compoundSmiles(doc);
    setReferenceId(id);
    if (!coreSmarts.trim() && !coreAtoms.length) return;
    try {
      const preview = await api.sarCorePreview({
        reference_smiles: smiles,
        core_atoms: coreAtoms,
        atom_modes: atomModesPayload(coreAtomModes),
        remap_smarts: coreSmarts.trim() || undefined,
        ignore_bond_order: ignoreBondOrder,
        molecules: selectedList.map((c) => ({
          id: c._id,
          smiles: compoundSmiles(c),
        })),
      });
      setCoreAtoms(preview.core_atoms);
      setCoreAtomModes(parseAtomModes(preview.atom_modes));
      setCorePreview(preview);
      if (!editSmarts && preview.smarts) setCoreSmarts(preview.smarts);
    } catch (err) {
      setError(String(err));
    }
  }

  function clearCore() {
    userCoreRef.current = true;
    setCoreAtoms([]);
    setCoreAtomModes({});
    setLastCoreAtom(null);
    setCorePreview(null);
    if (!editSmarts) setCoreSmarts("");
    setError("");
  }

  function adoptAlignment(result: AlignmentRunResult | null) {
    setAlignResult(result);
    if (result) setMessage("");
    if (!result) {
      setPoseById({});
      return;
    }
    const poses: Record<string, string> = {};
    for (const row of result.layouts) {
      if (row.molblock) poses[row.molecule_id] = row.molblock;
    }
    setPoseById(poses);
  }

  function refreshRecentProjects() {
    api
      .sarListAlignmentProjects(db, coll)
      .then((body) => setRecentProjects(body.projects))
      .catch(() => setRecentProjects([]));
  }

  useEffect(() => {
    refreshRecentProjects();
  }, [db, coll]);

  function applyLoadedProject(record: AlignmentProjectRecord) {
    skipLiveAlignRef.current = true;
    userCoreRef.current = true;
    window.setTimeout(() => {
      skipLiveAlignRef.current = false;
    }, 800);
    const known = new Set(compounds.map((c) => c._id));
    const ids = (record.compound_ids || []).filter((id) => known.has(id));
    if (!ids.length) {
      setError("That alignment has no compounds in this collection.");
      return;
    }
    const missing = (record.compound_ids || []).length - ids.length;
    setSelectedIds(new Set(ids));
    setFigureOrder(ids);
    setOrderTouched(true);
    setSelectedAssays(new Set(record.assay_ids || []));
    setReferenceId(ids.includes(record.reference_id) ? record.reference_id : ids[0]);
    setCoreSmarts(record.core_smarts || "");
    setAlignMode(
      (record.mode as "same_scaffold" | "ring_atom_replacements" | "scaffold_replacement") ||
        "same_scaffold"
    );
    setIgnoreBondOrder(Boolean(record.draft_solution?.details?.ignore_bond_order));
    const sem = String(record.draft_solution?.details?.scaffold_element_mode || "from_smarts");
    setScaffoldElementMode(
      sem === "element_agnostic" || sem === "ignore_elements" ? "element_agnostic" : "from_smarts"
    );
    setEditSmarts(false);
    const draft = record.draft_solution;
    if (draft?.layouts?.length) {
      adoptAlignment(draft);
      const refId = ids.includes(record.reference_id) ? record.reference_id : ids[0];
      const refLayout = draft.layouts.find((row) => row.molecule_id === refId);
      setCoreAtoms(refLayout?.core_atom_indices ?? []);
    } else {
      adoptAlignment(null);
      setCoreAtoms([]);
    }
    setSavedProject(record);
    setError("");
    setMessage(
      `Loaded ${record.id.slice(0, 8)}… (v${record.version})${
        missing > 0 ? ` — ${missing} compound(s) missing` : ""
      }`
    );
  }

  async function loadAlignmentProject(projectId?: string) {
    const id = (projectId || window.prompt("Alignment project id") || "").trim();
    if (!id) return;
    setLoading(true);
    setError("");
    try {
      const record = await api.sarGetAlignmentProject(id);
      applyLoadedProject(record);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  async function persistName(id: string) {
    const nextName = (names[id] ?? "").trim() || "Untitled";
    try {
      const saved = await api.updateCompound(db, coll, id, { Name: nextName });
      setCompounds((prev) => prev.map((c) => (c._id === id ? saved : c)));
      setNames((prev) => ({ ...prev, [id]: compoundName(saved) }));
    } catch (err) {
      setError(String(err));
    }
  }

  async function runAlignment() {
    if (!selectedIds.size) return;
    if (!referenceId) {
      setError("Promote a compound to reference.");
      return;
    }
    if (alignMode === "same_scaffold" && !coreSmarts.trim()) {
      setError("Select a shared core on the reference structure (or enter SMARTS).");
      return;
    }
    setLoading(true);
    setError("");
    setAlignProgress({ phase: "ingest", done: 0, total: selectedIds.size });
    try {
      const result = await api.sarRunAlignmentProgress(
        {
          project_id: db,
          series_id: coll,
          compound_ids: selectedList.map((doc) => doc._id),
          assay_ids: [...selectedAssays],
          reference_id: referenceId,
          mode: "same_scaffold",
          core_smarts: coreSmarts.trim() || "c1ccccc1",
          ignore_bond_order: ignoreBondOrder,
          scaffold_element_mode: scaffoldElementMode,
          poses: Object.entries(poseByIdRef.current)
            .filter(([, block]) => Boolean(block?.trim()))
            .map(([id, molblock]) => ({ id, molblock })),
        },
        setAlignProgress
      );
      adoptAlignment(result);
      setSavedProject(null);
    } catch (err) {
      adoptAlignment(null);
      setError(String(err));
    } finally {
      setLoading(false);
      setAlignProgress(null);
    }
  }

  async function saveAlignmentProject() {
    if (!snapshot || !alignResult) return;
    setLoading(true);
    setError("");
    try {
      const record = await api.sarCreateAlignmentProject({
        project_id: db,
        series_id: coll,
        compound_ids: selectedList.map((doc) => doc._id),
        assay_ids: [...selectedAssays],
        reference_id: referenceId,
        mode: "same_scaffold",
        core_smarts: coreSmarts.trim() || "c1ccccc1",
        snapshot_revision: alignResult.snapshot_revision || snapshot.source.revision,
        draft_solution: alignResult,
      });
      setSavedProject(record);
      setMessage(`Saved alignment project ${record.id.slice(0, 8)}… (v${record.version})`);
      refreshRecentProjects();
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  async function approveAlignmentProject() {
    if (!savedProject || !alignResult) return;
    setLoading(true);
    setError("");
    try {
      const record = await api.sarApproveAlignmentProject(savedProject.id, {
        expected_version: savedProject.version,
        snapshot_revision: savedProject.snapshot_revision,
      });
      setSavedProject(record);
      setMessage(`Approved v${record.version}`);
      refreshRecentProjects();
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  async function downloadMolPage() {
    if (!selectedList.length) return;
    setMolExporting(true);
    setError("");
    try {
      const { blob, filename } = await api.exportMolPage({
        molecules: selectedList.map((doc) => ({
          id: doc._id,
          name: names[doc._id] || compoundName(doc),
          smiles: compoundSmiles(doc),
          molblock: poseByIdRef.current[doc._id] || "",
        })),
        columns: previewColumnCount(pageContentRef.current),
        filename: `${coll}.cdxml`,
        format: "cdxml",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      setMessage(`Downloaded ${filename}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "ChemDraw export failed");
    } finally {
      setMolExporting(false);
    }
  }

  const onRotDown = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (!rotateOn) return;
      event.currentTarget.setPointerCapture(event.pointerId);
      rotateDrag.current = { x: event.clientX, deg: rotationDegRef.current };
    },
    [rotateOn]
  );

  const onRotMove = useCallback((event: PointerEvent<HTMLDivElement>) => {
    if (!rotateDrag.current) return;
    const next = rotateDrag.current.deg + (event.clientX - rotateDrag.current.x) * 0.45;
    rotationDegRef.current = next;
    setRotationDeg(next);
  }, []);

  const onRotUp = useCallback(() => {
    const dragging = rotateDrag.current;
    rotateDrag.current = null;
    if (!dragging) return;
    const deg = rotationDegRef.current;
    if (Math.abs(deg) < 0.5) {
      rotationDegRef.current = 0;
      setRotationDeg(0);
      return;
    }
    const molecules = selectedListRef.current.map((c) => ({
      id: c._id,
      smiles: compoundSmiles(c),
      molblock: poseByIdRef.current[c._id] || "",
    }));
    api
      .sarRotatePoses({ degrees: deg, molecules })
      .then((body) => {
        const next: Record<string, string> = { ...poseByIdRef.current };
        for (const pose of body.poses) next[pose.id] = pose.molblock;
        poseByIdRef.current = next;
        setPoseById(next);
        rotationDegRef.current = 0;
        setRotationDeg(0);
      })
      .catch((err) => setError(String(err)));
  }, []);

  const alignedIds = new Set(alignResult?.layouts.map((l) => l.molecule_id) ?? []);
  const unmatchedById = useMemo(() => unmatchedReasons(alignResult), [alignResult]);
  const failedAlign = Boolean(alignResult && isFailedAlign(alignResult.status));
  const unmatchedCount = selectedList.filter(
    (doc) => unmatchedById.has(doc._id) || (failedAlign && !alignedIds.has(doc._id))
  ).length;
  const canReorder = !rotateOn && !scaffoldOn;
  const statusKicker = alignKicker(alignResult, unmatchedCount);
  const layoutById = useMemo(() => {
    const map = new Map<string, AlignmentRunResult["layouts"][number]>();
    for (const row of alignResult?.layouts ?? []) map.set(row.molecule_id, row);
    return map;
  }, [alignResult]);
  const measurementsById = useMemo(() => {
    const map = new Map<string, SeriesSnapshot["compounds"][number]["measurements"]>();
    for (const row of snapshot?.compounds ?? []) map.set(row.id, row.measurements);
    return map;
  }, [snapshot]);

  return (
    <div className="export-workbench" role="dialog" aria-label="Export molecules">
      <aside className="export-pane export-pane-left">
        <div className="export-pane-head">
          <strong>Compounds</strong>
          <span className="muted">{selectedIds.size} selected</span>
        </div>
        <input
          className="export-search"
          placeholder="Search name or SMILES"
          value={listQuery}
          onChange={(e) => setListQuery(e.target.value)}
        />
        <div className="export-compound-list">
          {filteredList.map((doc) => {
            const smiles = compoundSmiles(doc);
            const selected = selectedIds.has(doc._id);
            return (
              <button
                key={doc._id}
                type="button"
                className={`export-compound-row${selected ? " is-selected" : ""}`}
                onClick={() => toggleSelected(doc._id, !selected)}
              >
                {smiles ? (
                  <img className="export-list-thumb" alt="" src={api.renderUrl(smiles, 96, 72)} />
                ) : (
                  <span className="muted">No structure</span>
                )}
                <span className="export-compound-name">{names[doc._id] ?? compoundName(doc)}</span>
              </button>
            );
          })}
        </div>
      </aside>

      <main className="export-center">
        <header className="export-center-head">
          <div className="export-head-top">
            <CoreReferencePanel
              referenceName={
                referenceId
                  ? names[referenceId] ??
                    (() => {
                      const doc = selectedList.find((c) => c._id === referenceId);
                      return doc ? compoundName(doc) : referenceId;
                    })()
                  : ""
              }
              referenceSmiles={referenceSmiles}
              molblock={poseById[referenceId] || layoutById.get(referenceId)?.molblock}
              coreAtoms={coreAtoms}
              coreAtomModes={coreAtomModes}
              rotationDeg={rotationDeg}
              scaffoldInteractive={scaffoldOn && !rotateOn}
              onCoreAtomClick={(idx, atom) => toggleCoreAtom(idx, atom)}
            />
            <div className="export-toggles">
            <label className="export-switch">
              <input
                type="checkbox"
                checked={scaffoldOn}
                onChange={(e) => {
                  setScaffoldOn(e.target.checked);
                  if (e.target.checked) setRotateOn(false);
                }}
              />
              <span>Scaffold selection</span>
            </label>
            <button
              type="button"
              className="secondary"
              disabled={!coreSmarts && !coreAtoms.length}
              onClick={() => clearCore()}
            >
              Clear scaffold
            </button>
            <label className="export-switch">
              <input
                type="checkbox"
                checked={rotateOn}
                onChange={(e) => {
                  setRotateOn(e.target.checked);
                  if (e.target.checked) setScaffoldOn(false);
                }}
              />
              <span>Rotate</span>
            </label>
            <label
              className="export-switch"
              title="Matching only: aromatic rings can hit aliphatic rings. Drawings always keep real bond orders."
            >
              <input
                type="checkbox"
                checked={ignoreBondOrder}
                onChange={(e) => setIgnoreBondOrder(e.target.checked)}
              />
              <span>Ignore bond order</span>
            </label>
            <label
              className="export-switch"
              title="As written in SMARTS uses the visible query for matching and alignment. Element agnostic treats every scaffold atom as equivalent."
            >
              <span>Scaffold mapping</span>
              <select
                value={scaffoldElementMode}
                onChange={(e) =>
                  setScaffoldElementMode(e.target.value as "from_smarts" | "element_agnostic")
                }
              >
                <option value="from_smarts">As written in SMARTS</option>
                <option value="element_agnostic">Element agnostic</option>
              </select>
            </label>
            {selectedList.length > LIVE_ALIGN_MAX && !alignProgress && (
              <span className="muted">Live alignment off above {LIVE_ALIGN_MAX}</span>
            )}
            {alignProgress && (
              <span className="muted export-align-kicker">{alignProgressLabel(alignProgress)}</span>
            )}
            {liveAligning && selectedList.length <= LIVE_ALIGN_MAX && (
              <span className="muted">Live aligning…</span>
            )}
            {!liveAligning && !alignProgress && message && (
              <span className="muted export-align-kicker">{message}</span>
            )}
            {!liveAligning && !alignProgress && !message && statusKicker && (
              <span className={`export-align-kicker${statusKicker.fail ? " is-fail" : ""}`}>
                {statusKicker.text}
              </span>
            )}
            </div>
          </div>
          <details className="export-smarts">
            <summary>SMARTS</summary>
            {corePreview?.message && <p className="muted export-smarts-hint">{corePreview.message}</p>}
            {editSmarts ? (
              <textarea
                className="export-smarts-edit"
                value={coreSmarts}
                onChange={(e) => setCoreSmarts(e.target.value)}
              />
            ) : (
              <code>{coreSmarts || "—"}</code>
            )}
            <div className="export-smarts-actions">
              {lastCoreAtom != null && coreAtoms.includes(lastCoreAtom) && (
                <div className="export-atom-mode-bar" role="toolbar" aria-label="Core atom match mode">
                  <span className="muted">Atom {lastCoreAtom}</span>
                  {CORE_MODE_ORDER.map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      className={`export-mode-chip export-mode-${mode}${
                        (coreAtomModes[lastCoreAtom] ?? "exact") === mode ? " is-active" : ""
                      }`}
                      onClick={() => setCoreAtomMode(lastCoreAtom, mode)}
                    >
                      {CORE_MODE_CHIP[mode]}
                    </button>
                  ))}
                </div>
              )}
              <label className="export-check">
                <input
                  type="checkbox"
                  checked={editSmarts}
                  onChange={(e) => {
                    userCoreRef.current = true;
                    setEditSmarts(e.target.checked);
                  }}
                />
                Edit
              </label>
            </div>
          </details>
          {alignProgress && (
            <div className="export-progress" role="status" aria-live="polite">
              <span>{alignProgressLabel(alignProgress)}</span>
              <div
                className={`export-progress-track${alignProgressPct(alignProgress) == null ? " is-busy" : ""}`}
              >
                <div
                  className="export-progress-bar"
                  style={
                    alignProgressPct(alignProgress) == null
                      ? undefined
                      : { width: `${alignProgressPct(alignProgress)}%` }
                  }
                />
              </div>
            </div>
          )}
        </header>

        {error && <p className="export-banner export-banner-error">{error}</p>}

        <div
          ref={figureRef}
          className={`export-figure${rotateOn ? " is-rotating" : ""}${canReorder ? " is-reordering" : ""}`}
        >
          {selectedList.length === 0 && (
            <p className="export-empty">Select compounds in the list to include them in the figure.</p>
          )}
          {selectedList.length > 0 && (
            <div
              className="export-page-slot"
              style={
                pageSlot.width > 0
                  ? { width: pageSlot.width, height: pageSlot.height }
                  : undefined
              }
            >
              <div
                ref={pageRef}
                className="export-page"
                style={{
                  width: `calc(${CHEMDRAW_PAGE.drawWidthPt}pt + ${2 * CHEMDRAW_PAGE.marginPt}pt)`,
                  minHeight: `calc(${CHEMDRAW_PAGE.drawHeightPt}pt + ${2 * CHEMDRAW_PAGE.marginPt}pt)`,
                  padding: `${CHEMDRAW_PAGE.marginPt}pt`,
                  transform: `scale(${pageZoom})`,
                }}
              >
                <div ref={pageContentRef} className="export-page-content">
          {selectedList.map((doc) => {
            const smiles = compoundSmiles(doc);
            const isReference = doc._id === referenceId;
            const measurements = measurementsById.get(doc._id) ?? [];
            const unmatchedReason =
              unmatchedById.get(doc._id) ??
              (failedAlign && !alignedIds.has(doc._id) ? globalAlignIssue(alignResult) : "");
            return (
              <article
                key={doc._id}
                draggable={canReorder}
                className={`export-mol${doc._id === referenceId ? " is-reference" : ""}${
                  alignedIds.has(doc._id) ? " is-aligned" : ""
                }${unmatchedReason ? " is-unmatched" : ""}${
                  canReorder ? " is-reorderable" : ""
                }${draggingId === doc._id ? " is-dragging" : ""}${
                  dropHint?.id === doc._id ? (dropHint.after ? " is-drop-after" : " is-drop-before") : ""
                }`}
                onDragStart={canReorder ? (event) => onMolDragStart(event, doc._id) : undefined}
                onDragOver={canReorder ? (event) => onMolDragOver(event, doc._id) : undefined}
                onDrop={canReorder ? (event) => onMolDrop(event, doc._id) : undefined}
                onDragEnd={canReorder ? onMolDragEnd : undefined}
              >
                {smiles ? (
                  <ClickableMol
                    smiles={smiles}
                    molblock={poseById[doc._id] || layoutById.get(doc._id)?.molblock}
                    scale={1}
                    unit="pt"
                    rotation={rotationDeg}
                    interactive={scaffoldOn && !rotateOn}
                    selected={isReference ? coreAtoms : []}
                    highlight={matchById.get(doc._id) ?? []}
                    atomModes={isReference ? coreAtomModes : undefined}
                    title={
                      rotateOn
                        ? "Drag sideways to rotate"
                        : scaffoldOn
                          ? isReference
                            ? "Reference: click atoms to add or cycle match mode"
                            : "Click an atom to generalize the matching reference position (e.g. O on S)"
                          : names[doc._id]
                            ? `${names[doc._id]} — drag to rearrange`
                            : "Drag to rearrange"
                    }
                    onAtomClick={(idx, atom) => {
                      if (!scaffoldOn || rotateOn) return;
                      if (isReference) toggleCoreAtom(idx, atom);
                      else void generalizeFromAnalog(doc._id, idx);
                    }}
                    onRotatePointerDown={rotateOn ? onRotDown : undefined}
                    onRotatePointerMove={rotateOn ? onRotMove : undefined}
                    onRotatePointerUp={rotateOn ? onRotUp : undefined}
                  />
                ) : (
                  <p className="muted">No structure</p>
                )}
                {unmatchedReason && (
                  <p className="export-mol-issue" role="status">
                    {unmatchedReason}
                  </p>
                )}
                <input
                  className="export-name-input"
                  draggable={false}
                  value={names[doc._id] ?? ""}
                  onChange={(e) => setNames((prev) => ({ ...prev, [doc._id]: e.target.value }))}
                  onBlur={() => persistName(doc._id)}
                  aria-label="Compound name"
                />
                <div className="export-mol-actions">
                  {doc._id === referenceId ? (
                    <span className="export-ref-label">Reference</span>
                  ) : (
                    <button type="button" className="export-text-btn" onClick={() => void promoteToReference(doc._id)}>
                      Promote to reference
                    </button>
                  )}
                  <button
                    type="button"
                    className="export-text-btn"
                    onClick={() => toggleSelected(doc._id, false)}
                  >
                    Remove
                  </button>
                </div>
                {measurements.length > 0 && (
                  <ul className="export-measurements">
                    {measurements.map((m) => (
                      <li key={m.assay_id}>
                        {m.assay_id} {m.qualifier === "not_determined" ? "—" : m.display_value}
                        {m.unit ? ` ${m.unit}` : ""}
                      </li>
                    ))}
                  </ul>
                )}
              </article>
            );
          })}
                </div>
              </div>
            </div>
          )}
        </div>
      </main>

      <aside className="export-pane export-pane-right">
        <div className="export-actions">
          {selectedList.length > LIVE_ALIGN_MAX && (
            <button type="button" disabled={loading || liveAligning || !selectedIds.size} onClick={() => runAlignment()}>
              {loading || liveAligning
                ? alignProgress
                  ? alignProgress.total
                    ? `${alignProgress.done}/${alignProgress.total}`
                    : "Aligning…"
                  : "Aligning…"
                : "Align"}
            </button>
          )}
          <button
            type="button"
            className="secondary"
            disabled={loading}
            onClick={() => loadAlignmentProject()}
          >
            Load
          </button>
          <button
            type="button"
            className="secondary"
            disabled={!alignResult || loading}
            onClick={() => saveAlignmentProject()}
          >
            Save
          </button>
          <button
            type="button"
            className="secondary"
            disabled={!savedProject || loading}
            onClick={() => approveAlignmentProject()}
          >
            Approve
          </button>
          <button
            type="button"
            className="secondary"
            disabled={!selectedIds.size || molExporting}
            title="ChemDraw CDXML, laid out like this figure, with names"
            onClick={() => downloadMolPage()}
          >
            {molExporting ? "Exporting…" : "Download ChemDraw"}
          </button>
          <button type="button" className="secondary" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="export-pane-head">
          <strong>Assay labels</strong>
        </div>
        <div className="export-assay-list">
          {assayFields.map((field) => (
            <label key={field.id} className="export-check">
              <input
                type="checkbox"
                checked={selectedAssays.has(field.id)}
                onChange={() => toggleAssay(field.id)}
              />
              <span>{field.name}</span>
            </label>
          ))}
          {!assayFields.length && <p className="muted">No assay fields in the schema.</p>}
        </div>
        <div className="export-recent">
          <div className="export-pane-head">
            <strong>Recent projects</strong>
            <span className="muted">{recentProjects.length}</span>
          </div>
          <div className="export-recent-list">
            {recentProjects.map((row) => (
              <button
                key={row.id}
                type="button"
                className={`export-recent-item${savedProject?.id === row.id ? " is-active" : ""}`}
                onClick={() => loadAlignmentProject(row.id)}
                title={row.id}
              >
                <span className="export-recent-id">{row.id.slice(0, 8)}…</span>
                <span className="export-recent-meta">
                  {row.compound_count} cmpd · {MODE_LABEL[row.mode] || row.mode}
                  {row.approved ? " · approved" : ""}
                </span>
                <span className="muted">{formatWhen(row.updated_at) || row.owner}</span>
              </button>
            ))}
            {!recentProjects.length && <p className="muted">No saved alignments yet.</p>}
          </div>
        </div>
      </aside>
    </div>
  );
}
