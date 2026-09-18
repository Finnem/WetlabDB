import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import CompoundForm from "../components/CompoundForm";
import StructurePreview from "../components/StructurePreview";
import type { Compound, CompoundSchema, User } from "../types";

const COLS_KEY = "wetlabdb.visible_columns";

function csvHeaders(text: string): string[] {
  const line = (text.split(/\r?\n/).find((row) => row.trim()) || "").replace(/^\uFEFF/, "");
  const headers: string[] = [];
  let current = "";
  let quoted = false;
  for (const ch of line) {
    if (ch === '"') {
      quoted = !quoted;
    } else if (ch === "," && !quoted) {
      headers.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  if (current.length || headers.length) headers.push(current.trim());
  return headers.filter(Boolean);
}

export default function Browser({
  user,
  db,
  coll,
  onDb,
  onColl,
}: {
  user: User;
  db: string;
  coll: string;
  onDb: (name: string) => void;
  onColl: (name: string) => void;
}) {
  const [schema, setSchema] = useState<CompoundSchema | null>(null);
  const [databases, setDatabases] = useState<string[]>([]);
  const [collections, setCollections] = useState<string[]>([]);
  const [compounds, setCompounds] = useState<Compound[]>([]);
  const [selected, setSelected] = useState<Compound | null>(null);
  const [creating, setCreating] = useState(false);
  const [q, setQ] = useState("");
  const [column, setColumn] = useState("All");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [visible, setVisible] = useState<string[]>(() => {
    try {
      const stored = localStorage.getItem(COLS_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });
  const [showColumns, setShowColumns] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);

  async function loadCatalog() {
    const dbs = (await api.databases()).databases;
    setDatabases(dbs);
    const nextDb = dbs.includes(db) ? db : dbs[0] || "";
    if (nextDb !== db) onDb(nextDb);
    if (!nextDb) {
      setCollections([]);
      return;
    }
    const colls = (await api.collections(nextDb)).collections;
    setCollections(colls);
    const nextColl = colls.includes(coll) ? coll : colls[0] || "";
    if (nextColl !== coll) onColl(nextColl);
  }

  async function loadCompounds(nextDb = db, nextColl = coll) {
    if (!nextDb || !nextColl) {
      setCompounds([]);
      return;
    }
    const body = await api.compounds(nextDb, nextColl, q, column);
    setCompounds(body.compounds);
  }

  useEffect(() => {
    api.schema().then((s) => {
      setSchema(s);
      setVisible((prev) => (prev.length ? prev : s.visible_columns));
    });
    loadCatalog().catch((err) => setError(String(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadCompounds().catch((err) => setError(String(err)));
    setSelected(null);
    setCreating(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [db, coll]);

  useEffect(() => {
    localStorage.setItem(COLS_KEY, JSON.stringify(visible));
  }, [visible]);

  const allColumns = useMemo(() => {
    const keys = new Set(visible);
    for (const doc of compounds) {
      for (const key of Object.keys(doc)) {
        if (key !== "_id") keys.add(key);
      }
    }
    if (schema) Object.keys(schema.fields).forEach((k) => keys.add(k));
    return Array.from(keys);
  }, [compounds, schema, visible]);

  async function save(data: Record<string, unknown>, unset: string[]) {
    if (!db || !coll) return;
    if (creating || !selected) {
      const doc = await api.addCompound(db, coll, data);
      setCreating(false);
      setSelected(doc);
    } else {
      const doc = await api.updateCompound(db, coll, selected._id, data, unset);
      setSelected(doc);
    }
    await loadCompounds();
    setMessage("Saved");
  }

  return (
    <div className="layout">
      <section className="panel">
        <div className="toolbar">
          <label>
            Database
            <select value={db} onChange={(e) => onDb(e.target.value)}>
              {databases.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          {user.admin && (
            <>
              <button
                className="secondary"
                onClick={async () => {
                  const name = prompt("New database name?");
                  const collection = prompt("First collection name?", "Compounds");
                  if (!name || !collection) return;
                  await api.createDatabase(name, collection);
                  onDb(name);
                  onColl(collection);
                  await loadCatalog();
                }}
              >
                + DB
              </button>
              <button
                className="danger"
                onClick={async () => {
                  if (!db || !confirm(`Delete database ${db}?`)) return;
                  await api.dropDatabase(db);
                  onDb("");
                  await loadCatalog();
                }}
              >
                Delete DB
              </button>
            </>
          )}
          <label>
            Collection
            <select value={coll} onChange={(e) => onColl(e.target.value)}>
              {collections.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          {user.admin && (
            <>
              <button
                className="secondary"
                onClick={async () => {
                  const name = prompt("New collection name?");
                  if (!name || !db) return;
                  await api.createCollection(db, name);
                  onColl(name);
                  await loadCatalog();
                }}
              >
                + coll
              </button>
              <button
                className="danger"
                onClick={async () => {
                  if (!db || !coll || !confirm(`Delete collection ${coll}?`)) return;
                  await api.dropCollection(db, coll);
                  onColl("");
                  await loadCatalog();
                }}
              >
                Delete coll
              </button>
            </>
          )}
        </div>
        <div className="toolbar">
          <input placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
          <select value={column} onChange={(e) => setColumn(e.target.value)}>
            <option>All</option>
            {visible.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
          <button className="secondary" onClick={() => loadCompounds()}>
            Filter
          </button>
          <button className="secondary" onClick={() => setShowColumns((v) => !v)}>
            Columns
          </button>
          <button
            onClick={() => {
              setCreating(true);
              setSelected(null);
            }}
          >
            Add
          </button>
          <a href={api.exportCsvUrl(db, coll, visible.length ? visible : ["Name", "SMILES"], q, column)}>
            <button type="button" className="secondary">
              Download CSV
            </button>
          </a>
          <input
            type="file"
            accept=".csv"
            onChange={(e) => setImportFile(e.target.files?.[0] || null)}
          />
          <button
            className="secondary"
            disabled={!importFile}
            onClick={async () => {
              if (!importFile || !schema) return;
              const head = await importFile.slice(0, 65536).text();
              const headers = csvHeaders(head);
              const defaultId =
                schema.csv_identifiers.find((col) => headers.includes(col)) ||
                headers[0] ||
                "Name";
              const identifier = prompt(
                `Identifier column (${schema.csv_identifiers.join(", ")})`,
                defaultId
              );
              if (!identifier) return;
              const defaultData = headers.filter((col) => col !== identifier).join(",");
              const dataCols =
                prompt("Data columns, comma-separated", defaultData) || defaultData;
              const summary = await api.importCsv(
                db,
                coll,
                importFile,
                identifier,
                dataCols.split(",").map((s) => s.trim()).filter(Boolean)
              );
              setMessage(`Imported: created ${summary.created}, updated ${summary.updated}`);
              await loadCompounds();
            }}
          >
            Import CSV
          </button>
        </div>
        {showColumns && (
          <div className="row" style={{ marginBottom: "0.5rem" }}>
            {allColumns.map((c) => (
              <label key={c}>
                <input
                  type="checkbox"
                  checked={visible.includes(c)}
                  onChange={(e) =>
                    setVisible((prev) =>
                      e.target.checked ? [...prev, c] : prev.filter((x) => x !== c)
                    )
                  }
                />
                {c}
              </label>
            ))}
          </div>
        )}
        {error && <p className="error">{error}</p>}
        {message && <p className="ok">{message}</p>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Structure</th>
                {visible.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {compounds.map((doc) => (
                <tr
                  key={doc._id}
                  className={selected?._id === doc._id ? "selected" : ""}
                  onClick={() => {
                    setSelected(doc);
                    setCreating(false);
                  }}
                >
                  <td>
                    {doc.SMILES ? (
                      <img
                        className="thumb"
                        alt=""
                        src={api.renderUrl(String(doc.SMILES))}
                      />
                    ) : null}
                  </td>
                  {visible.map((c) => (
                    <td key={c}>{String(doc[c] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        {!schema && <p className="muted">Loading form…</p>}
        {schema && (creating || selected) && (
          <>
            <div className="toolbar">
              <strong>{creating ? "New compound" : selected?.Name || "Edit"}</strong>
              {selected && !creating && (
                <button
                  className="danger"
                  onClick={async () => {
                    if (!selected || !confirm("Delete this compound?")) return;
                    await api.deleteCompound(db, coll, selected._id);
                    setSelected(null);
                    await loadCompounds();
                  }}
                >
                  Delete
                </button>
              )}
            </div>
            {!creating && selected?.SMILES ? (
              <StructurePreview smiles={String(selected.SMILES)} width={280} height={200} />
            ) : null}
            <CompoundForm
              key={creating ? "new" : selected?._id ?? "edit"}
              schema={schema}
              initial={creating ? schema.defaults : selected || schema.defaults}
              onSubmit={save}
              onCancel={() => {
                setCreating(false);
              }}
            />
          </>
        )}
        {!creating && !selected && <p className="muted">Select a compound or click Add.</p>}
      </section>
    </div>
  );
}
