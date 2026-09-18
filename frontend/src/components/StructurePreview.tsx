import { Suspense, lazy } from "react";
import { api } from "../api";

const StructureViewer3D = lazy(() => import("./StructureViewer3D"));

export default function StructurePreview({
  smiles,
  width = 200,
  height = 200,
}: {
  smiles: string;
  width?: number;
  height?: number;
}) {
  return (
    <div className="structure-previews">
      <div className="structure-preview" style={{ width, height }}>
        <img alt="" src={api.renderUrl(smiles, width, height)} />
      </div>
      <Suspense
        fallback={
          <div className="structure-viewer-3d" style={{ width, height }}>
            <p className="muted structure-viewer-3d-msg">Loading 3D…</p>
          </div>
        }
      >
        <StructureViewer3D smiles={smiles} width={width} height={height} />
      </Suspense>
    </div>
  );
}
