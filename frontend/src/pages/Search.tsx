import { useEffect, useState } from "react";
import { api } from "../api";
import KetcherEditor, { looksLikeQuery } from "../components/KetcherEditor";
import StructurePreview from "../components/StructurePreview";
import type { SearchMetrics, SimilarityHit, SubstructureHit } from "../types";

export default function Search({ db, coll }: { db: string; coll: string }) {
  const [metrics, setMetrics] = useState<SearchMetrics | null>(null);
  const [query, setQuery] = useState("");
  const [metric, setMetric] = useState("Tanimoto");
  const [cutoff, setCutoff] = useState(0.7);
  const [hits, setHits] = useState<(SimilarityHit | SubstructureHit)[]>([]);
  const [mode, setMode] = useState<"similarity" | "substructure">("similarity");
  const [error, setError] = useState("");
  const [drawing, setDrawing] = useState(false);

  useEffect(() => {
    api.metrics().then((m) => {
      setMetrics(m);
      setMetric(m.default);
      setCutoff(m.cutoffs[m.default] ?? 0.7);
    });
  }, []);

  useEffect(() => {
    if (metrics?.cutoffs[metric] != null) setCutoff(metrics.cutoffs[metric]);
  }, [metric, metrics]);

  async function runSimilarity(sortAll: boolean) {
    if (!db || !coll) return;
    setError("");
    setMode("similarity");
    try {
      const body = await api.similarity(db, coll, {
        query,
        cutoff,
        metric,
        sort_all: sortAll,
      });
      setHits(body.hits);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    }
  }

  async function runSubstructure() {
    if (!db || !coll) return;
    setError("");
    setMode("substructure");
    try {
      setHits((await api.substructure(db, coll, query)).hits);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    }
  }

  return (
    <div className="search-page">
      <div className="panel">
        <div className="toolbar">
          <input
            style={{ minWidth: "22rem" }}
            placeholder="SMILES or SMARTS"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button className="secondary" onClick={() => setDrawing(true)}>
            Draw
          </button>
          {metrics && (
            <select value={metric} onChange={(e) => setMetric(e.target.value)}>
              {metrics.metrics.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          )}
          <label>
            Cutoff {cutoff.toFixed(2)}
            <input
              type="range"
              min={-1}
              max={1}
              step={0.01}
              value={cutoff}
              onChange={(e) => setCutoff(Number(e.target.value))}
            />
          </label>
          <button onClick={() => runSimilarity(false)}>Similarity</button>
          <button className="secondary" onClick={() => runSimilarity(true)}>
            Sort all
          </button>
          <button className="secondary" onClick={runSubstructure}>
            Substructure
          </button>
          <a href={api.exportSimilarityCsvUrl(db, coll, query, cutoff, metric, false)}>
            <button type="button" className="secondary">
              Download results
            </button>
          </a>
        </div>
        {metrics?.descriptions[metric] && (
          <p className="muted">{metrics.descriptions[metric]}</p>
        )}
        {error && <p className="error">{error}</p>}
        {query && <StructurePreview smiles={query} width={280} height={200} />}
      </div>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Structure</th>
              <th>Name</th>
              <th>SMILES</th>
              <th>CAS Nr</th>
              <th>Storage Location</th>
              {mode === "similarity" && <th>Similarity</th>}
            </tr>
          </thead>
          <tbody>
            {hits.map((hit) => {
              const doc = hit.document;
              const highlight = "match_atoms" in hit ? hit.match_atoms : undefined;
              const sim = "similarity" in hit ? hit.similarity : undefined;
              return (
                <tr key={doc._id}>
                  <td>
                    {doc.SMILES && (
                      <img
                        className="thumb"
                        alt=""
                        src={api.renderUrl(String(doc.SMILES), 160, 120, highlight)}
                      />
                    )}
                  </td>
                  <td>{String(doc.Name ?? "")}</td>
                  <td>{String(doc.SMILES ?? "")}</td>
                  <td>{String(doc["CAS Nr"] ?? "")}</td>
                  <td>{String(doc["Storage Location"] ?? "")}</td>
                  {mode === "similarity" && (
                    <td>{sim != null ? sim.toFixed(3) : ""}</td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {drawing && (
        <KetcherEditor
          initial={query}
          onApply={(smiles, molfile) => {
            setDrawing(false);
            if (looksLikeQuery(smiles)) {
              setQuery(smiles);
              return;
            }
            fetch("/api/chem/from-molfile", {
              method: "POST",
              credentials: "include",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ molfile }),
            })
              .then(async (r) => (r.ok ? r.json() : { smiles }))
              .then((body) => setQuery(body.smiles || smiles))
              .catch(() => setQuery(smiles));
          }}
          onClose={() => setDrawing(false)}
        />
      )}
    </div>
  );
}
