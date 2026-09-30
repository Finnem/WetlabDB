import { useEffect, useMemo, useState, type PointerEvent } from "react";
import { api } from "../api";
import { atomModesPayload } from "../coreScaffold";
import type { CoreAtomMode, DepictAtom, DepictResult } from "../types";

function inlineSvg(svg: string): string {
  return svg.replace(/<\?xml[^>]*>/, "").trim();
}

export const ACS_DISPLAY_SCALE = 3;

export const CORE_REF_MOL_SCALE = 2.15;

export default function ClickableMol({
  smiles,
  scale = ACS_DISPLAY_SCALE,
  unit = "px",
  rotation = 0,
  selected = [],
  highlight = [],
  atomModes,
  interactive = false,
  fragmentAtoms,
  molblock,
  queryLabels = false,
  queryLabelDim = false,
  className = "",
  title,
  onAtomClick,
  onRotatePointerDown,
  onRotatePointerMove,
  onRotatePointerUp,
}: {
  smiles: string;
  scale?: number;
  unit?: "px" | "pt";
  rotation?: number;
  selected?: number[];
  highlight?: number[];
  atomModes?: Record<number, CoreAtomMode>;
  interactive?: boolean;
  fragmentAtoms?: number[];
  molblock?: string | null;
  /** Floating labels for core query text (e.g. S, O/S/Se, any). */
  queryLabels?: boolean;
  /** Dim structure drawing when query labels are shown (header mirror). */
  queryLabelDim?: boolean;
  className?: string;
  title?: string;
  onAtomClick?: (idx: number, atom: DepictAtom) => void;
  onRotatePointerDown?: (event: PointerEvent<HTMLDivElement>) => void;
  onRotatePointerMove?: (event: PointerEvent<HTMLDivElement>) => void;
  onRotatePointerUp?: (event: PointerEvent<HTMLDivElement>) => void;
}) {
  const [drawn, setDrawn] = useState<DepictResult | null>(null);
  const [error, setError] = useState("");
  const selectedSet = useMemo(() => new Set(selected), [selected.join(",")]);
  const highlightSet = useMemo(() => new Set(highlight), [highlight.join(",")]);
  const fragmentKey = (fragmentAtoms ?? []).join(",");
  const modesKey = useMemo(() => JSON.stringify(atomModes ?? {}), [atomModes]);
  const annotateModes = Boolean(atomModes && Object.keys(atomModes).length);

  useEffect(() => {
    if (!smiles) {
      setDrawn(null);
      return;
    }
    let cancelled = false;
    api
      .sarDepict({
        smiles,
        fragment_atoms: fragmentAtoms,
        molblock: molblock || undefined,
        core_atom_modes: annotateModes ? atomModesPayload(atomModes!) : undefined,
        query_labels: annotateModes || queryLabels,
      })
      .then((body) => {
        if (!cancelled) {
          setDrawn(body);
          setError("");
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setDrawn(null);
          setError(String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [smiles, fragmentKey, molblock, modesKey, queryLabels, annotateModes]);

  const svg = useMemo(() => (drawn ? inlineSvg(drawn.svg) : ""), [drawn]);

  const refIndex = (depictIdx: number) =>
    fragmentAtoms && depictIdx < fragmentAtoms.length ? fragmentAtoms[depictIdx] : depictIdx;

  const boxWidth = drawn ? drawn.width * scale : 72 * scale;
  const boxHeight = drawn ? drawn.height * scale : 56 * scale;
  const sizeStyle =
    unit === "pt"
      ? { width: `${boxWidth}pt`, height: `${boxHeight}pt`, maxWidth: "100%" }
      : { width: boxWidth, height: boxHeight };

  if (!smiles) {
    return <p className="muted sar-no-structure">Empty SMILES</p>;
  }
  if (error) {
    return <p className="muted sar-no-structure">{error}</p>;
  }
  if (!drawn) {
    return (
      <div className={`sar-mol-clickable sar-mol-loading ${className}`.trim()} style={sizeStyle}>
        <span className="muted">Drawing…</span>
      </div>
    );
  }

  const dimSvg = queryLabelDim && queryLabels;

  return (
    <div
      className={
        `sar-mol-clickable${interactive ? " sar-mol-interactive" : ""}${
          queryLabels ? " sar-mol-query-labels" : ""
        }${dimSvg ? " sar-mol-query-dim" : ""} ${className}`.trim()
      }
      style={{
        ...sizeStyle,
        transform: rotation ? `rotate(${rotation}deg)` : undefined,
      }}
      title={title}
      onPointerDown={onRotatePointerDown}
      onPointerMove={onRotatePointerMove}
      onPointerUp={onRotatePointerUp}
      onPointerCancel={onRotatePointerUp}
    >
      <div className="sar-mol-svg" dangerouslySetInnerHTML={{ __html: svg }} />
      {drawn.atoms.map((atom) => {
        const refIdx = refIndex(atom.idx);
        const isSelected = selectedSet.has(refIdx);
        const isMatched = highlightSet.has(atom.idx);
        const mode = isSelected ? atomModes?.[refIdx] ?? "exact" : null;
        const modeClass = mode ? ` sar-atom-mode-${mode}` : "";
        const queryText = atom.query_label?.trim() || "";
        const showFloatingLabel = queryLabels && queryText && !(interactive && isSelected);
        const badgeText = isSelected && mode ? queryText || atom.symbol : "";
        return (
          <span key={atom.idx}>
            {showFloatingLabel ? (
              <span
                className="sar-query-label"
                style={{
                  left: `${(atom.x / drawn.width) * 100}%`,
                  top: `${(atom.y / drawn.height) * 100}%`,
                }}
              >
                {queryText}
              </span>
            ) : null}
            {interactive ? (
              <button
                type="button"
                className={
                  "sar-atom-hit" +
                  modeClass +
                  (isSelected ? " sar-atom-selected" : "") +
                  (isMatched && !isSelected ? " sar-atom-matched" : "")
                }
                style={{
                  left: `${(atom.x / drawn.width) * 100}%`,
                  top: `${(atom.y / drawn.height) * 100}%`,
                }}
                aria-label={`Atom ${atom.idx} ${atom.symbol}${badgeText ? ` · ${badgeText}` : ""}`}
                title={
                  isSelected && badgeText
                    ? `${atom.symbol} ${refIdx} · matches as ${badgeText}`
                    : isMatched
                      ? `${atom.symbol} ${atom.idx} · matched`
                      : `${atom.symbol} ${atom.idx}`
                }
                onClick={() => onAtomClick?.(atom.idx, atom)}
              >
                {badgeText ? <span className="sar-atom-mode-badge">{badgeText}</span> : null}
              </button>
            ) : null}
          </span>
        );
      })}
    </div>
  );
}
