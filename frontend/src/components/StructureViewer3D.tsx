import { useEffect, useRef, useState } from "react";
import $3Dmol from "3dmol";
import { api } from "../api";

export default function StructureViewer3D({
  smiles,
  width = 200,
  height = 200,
}: {
  smiles: string;
  width?: number;
  height?: number;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    setFailed(false);
    host.innerHTML = "";
    const viewer = $3Dmol.createViewer(host, { backgroundColor: "white" });
    let cancelled = false;

    (async () => {
      try {
        const response = await fetch(api.mol3dUrl(smiles), { credentials: "include" });
        if (cancelled) return;
        if (!response.ok) {
          setFailed(true);
          return;
        }
        const molblock = await response.text();
        if (cancelled) return;
        viewer.addModel(molblock, "mol");
        viewer.setStyle({}, { stick: { radius: 0.12 }, sphere: { scale: 0.22 } });
        viewer.zoomTo();
        viewer.resize(width, height);
        viewer.render();
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [smiles, width, height]);

  return (
    <div
      className="structure-viewer-3d"
      style={{ width, height }}
      title="Drag to rotate · scroll to zoom"
    >
      <div className="structure-viewer-3d-canvas" ref={hostRef} />
      {failed ? <p className="muted structure-viewer-3d-msg">3D unavailable</p> : null}
    </div>
  );
}
