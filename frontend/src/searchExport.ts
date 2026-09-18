import type { SimilarityHit, SubstructureHit } from "./types";

function csvCell(value: string): string {
  if (/[",\n\r]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

/** Build CSV for the hits currently shown in the search table. */
export function searchHitsToCsv(
  hits: (SimilarityHit | SubstructureHit)[],
  mode: "similarity" | "substructure"
): string {
  const headers =
    mode === "similarity"
      ? ["Name", "SMILES", "CAS Nr", "Storage Location", "Similarity"]
      : ["Name", "SMILES", "CAS Nr", "Storage Location"];
  const lines = [headers.join(",")];
  for (const hit of hits) {
    const doc = hit.document;
    const row = [
      String(doc.Name ?? ""),
      String(doc.SMILES ?? ""),
      String(doc["CAS Nr"] ?? ""),
      String(doc["Storage Location"] ?? ""),
    ];
    if (mode === "similarity" && "similarity" in hit) {
      const sim = hit.similarity;
      row.push(sim != null ? sim.toFixed(4) : "");
    }
    lines.push(row.map(csvCell).join(","));
  }
  return `${lines.join("\n")}\n`;
}

export function downloadSearchHitsCsv(
  hits: (SimilarityHit | SubstructureHit)[],
  mode: "similarity" | "substructure"
): void {
  const text = searchHitsToCsv(hits, mode);
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "search_results.csv";
  a.click();
  URL.revokeObjectURL(url);
}
