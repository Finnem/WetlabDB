import { api } from "../api";

export default function StructurePreview({
  smiles,
  width = 280,
  height = 200,
}: {
  smiles: string;
  width?: number;
  height?: number;
}) {
  return (
    <div className="structure-preview" style={{ width, height }}>
      <img alt="" src={api.renderUrl(smiles, width, height)} />
    </div>
  );
}
