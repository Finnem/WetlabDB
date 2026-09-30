import { useEffect, useRef, useState } from "react";

export type ExportMenuProps = {
  busy?: boolean;
  disabled?: boolean;
  csvDisabled?: boolean;
  structuresDisabled?: boolean;
  chemDrawDisabled?: boolean;
  showFigureLayout?: boolean;
  figureLayoutDisabled?: boolean;
  onCsv: () => void;
  onChemDraw: () => void | Promise<void>;
  onMolZip: () => void | Promise<void>;
  onSdf: () => void | Promise<void>;
  onFigureLayout?: () => void;
};

export default function ExportMenu({
  busy = false,
  disabled = false,
  csvDisabled = false,
  structuresDisabled = false,
  chemDrawDisabled = false,
  showFigureLayout = false,
  figureLayoutDisabled = false,
  onCsv,
  onChemDraw,
  onMolZip,
  onSdf,
  onFigureLayout,
}: ExportMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function run(action: () => void | Promise<void>) {
    setOpen(false);
    await action();
  }

  const menuDisabled = disabled || busy;

  return (
    <div className="export-menu" ref={rootRef}>
      <button
        type="button"
        className="secondary"
        disabled={menuDisabled}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((v) => !v)}
      >
        {busy ? "Exporting…" : "Export"}
      </button>
      {open && (
        <div className="export-menu-panel" role="menu">
          <button
            type="button"
            role="menuitem"
            disabled={csvDisabled}
            onClick={() => run(onCsv)}
          >
            CSV
          </button>
          <button
            type="button"
            role="menuitem"
            disabled={chemDrawDisabled}
            title="ChemDraw CDXML grid from 2D coordinates"
            onClick={() => run(onChemDraw)}
          >
            ChemDraw (CDXML)
          </button>
          <div className="export-menu-label" role="presentation">
            Molecular file formats
          </div>
          <button
            type="button"
            role="menuitem"
            className="export-menu-nested"
            disabled={structuresDisabled}
            onClick={() => run(onMolZip)}
          >
            MOL files (ZIP)
          </button>
          <button
            type="button"
            role="menuitem"
            className="export-menu-nested"
            disabled={structuresDisabled}
            onClick={() => run(onSdf)}
          >
            SDF
          </button>
          {showFigureLayout && onFigureLayout && (
            <>
              <div className="export-menu-divider" role="presentation" />
              <button
                type="button"
                role="menuitem"
                disabled={figureLayoutDisabled}
                title="Open alignment workbench for SAR figure layout and posed export"
                onClick={() => {
                  setOpen(false);
                  onFigureLayout();
                }}
              >
                Align &amp; export figure…
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
