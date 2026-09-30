import type { Compound, SarAssayField, SarMeasurement } from "./types";

function csvCell(value: string): string {
  if (/[",\n\r]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

export function downloadAlignmentCsv(
  docs: Compound[],
  names: Record<string, string>,
  assayFields: SarAssayField[],
  selectedAssayIds: Set<string>,
  measurementsById: Map<string, SarMeasurement[]>
): void {
  const assays = assayFields.filter((f) => selectedAssayIds.has(f.id));
  const headers = ["Name", "SMILES", ...assays.map((a) => a.name)];
  const lines = [headers.join(",")];
  for (const doc of docs) {
    const meas = measurementsById.get(doc._id) ?? [];
    const byAssay = new Map(meas.map((m) => [m.assay_id, m]));
    const row = [
      String(names[doc._id] ?? doc.Name ?? ""),
      String(doc.SMILES ?? ""),
      ...assays.map((a) => {
        const m = byAssay.get(a.id);
        if (!m || m.qualifier === "not_determined") return "";
        const text = m.display_value || "";
        return m.unit ? `${text} ${m.unit}`.trim() : text;
      }),
    ];
    lines.push(row.map(csvCell).join(","));
  }
  const blob = new Blob([`${lines.join("\n")}\n`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "alignment_export.csv";
  a.click();
  URL.revokeObjectURL(url);
}
