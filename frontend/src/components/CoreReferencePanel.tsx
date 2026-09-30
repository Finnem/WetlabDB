import ClickableMol, { CORE_REF_MOL_SCALE } from "./ClickableMol";
import type { CoreAtomMode, DepictAtom } from "../types";

export default function CoreReferencePanel({
  referenceName,
  referenceSmiles,
  molblock,
  coreAtoms,
  coreAtomModes,
  rotationDeg,
  scaffoldInteractive,
  onCoreAtomClick,
}: {
  referenceName: string;
  referenceSmiles: string;
  molblock?: string | null;
  coreAtoms: number[];
  coreAtomModes: Record<number, CoreAtomMode>;
  rotationDeg: number;
  scaffoldInteractive: boolean;
  onCoreAtomClick: (idx: number, atom: DepictAtom) => void;
}) {
  const hasCore = coreAtoms.length > 0;
  return (
    <div className="export-core-ref-panel">
      <div className="export-core-ref-head">
        <span className="export-kicker">Reference</span>
        {referenceName ? <span className="export-core-ref-name">{referenceName}</span> : null}
        {hasCore ? (
          <span className="muted export-core-ref-hint">Core labels show SMARTS match rules</span>
        ) : null}
      </div>
      {referenceSmiles ? (
        <div className="export-core-ref-mol-wrap">
          <ClickableMol
            className="export-core-ref-mol"
            smiles={referenceSmiles}
            molblock={molblock}
            scale={CORE_REF_MOL_SCALE}
            unit="pt"
            rotation={rotationDeg}
            atomModes={coreAtomModes}
            selected={coreAtoms}
            queryLabels={hasCore}
            queryLabelDim={hasCore}
            interactive={scaffoldInteractive}
            title="Reference — click core atoms to set match mode"
            onAtomClick={onCoreAtomClick}
          />
        </div>
      ) : (
        <p className="export-core-empty">Promote a compound to reference.</p>
      )}
    </div>
  );
}
