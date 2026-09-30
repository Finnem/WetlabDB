import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { AuditEvent, Compound, TrashCompound } from "../types";

type Tab = "audit" | "trash";

export default function Admin() {
  const [tab, setTab] = useState<Tab>("audit");
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [databases, setDatabases] = useState<string[]>([]);
  const [db, setDb] = useState("");
  const [collections, setCollections] = useState<string[]>([]);
  const [coll, setColl] = useState("");
  const [trash, setTrash] = useState<TrashCompound[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const loadAudit = useCallback(async () => {
    const body = await api.auditEvents(200);
    setEvents(body.events);
  }, []);

  const loadTrash = useCallback(async () => {
    if (!db || !coll) {
      setTrash([]);
      return;
    }
    const body = await api.deletedCompounds(db, coll);
    setTrash(body.compounds);
  }, [db, coll]);

  useEffect(() => {
    if (tab !== "audit") return;
    loadAudit().catch((err) => setError(String(err)));
  }, [tab, loadAudit]);

  useEffect(() => {
    api
      .databases()
      .then((body) => {
        setDatabases(body.databases);
        if (!db && body.databases.length) setDb(body.databases[0]);
      })
      .catch((err) => setError(String(err)));
  }, [db]);

  useEffect(() => {
    if (!db) {
      setCollections([]);
      return;
    }
    api
      .collections(db)
      .then((body) => {
        setCollections(body.collections);
        if (!coll || !body.collections.includes(coll)) setColl(body.collections[0] ?? "");
      })
      .catch((err) => setError(String(err)));
  }, [db, coll]);

  useEffect(() => {
    if (tab !== "trash") return;
    loadTrash().catch((err) => setError(String(err)));
  }, [tab, loadTrash]);

  async function restore(compound: Compound) {
    if (!db || !coll) return;
    setError("");
    setMessage("");
    try {
      await api.restoreCompound(db, coll, compound._id);
      setMessage(`Restored ${compound.Name || compound._id}`);
      await loadTrash();
      await loadAudit();
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <div className="panel">
      <h2>Admin</h2>
      <p className="muted">Audit trail and soft-deleted compounds (restore).</p>
      {error && <p className="error">{error}</p>}
      {message && <p className="success">{message}</p>}

      <div className="tab-row" style={{ marginBottom: "1rem" }}>
        <button type="button" className={tab === "audit" ? "" : "secondary"} onClick={() => setTab("audit")}>
          Audit log
        </button>
        <button type="button" className={tab === "trash" ? "" : "secondary"} onClick={() => setTab("trash")}>
          Trash / restore
        </button>
      </div>

      {tab === "audit" && (
        <>
          <button type="button" className="secondary" onClick={() => loadAudit().catch((e) => setError(String(e)))}>
            Refresh
          </button>
          <table className="data-table" style={{ marginTop: "1rem" }}>
            <thead>
              <tr>
                <th>Time</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Target</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev, index) => (
                <tr key={`${ev.at}-${ev.action}-${index}`}>
                  <td>{ev.at}</td>
                  <td>{ev.actor ?? "—"}</td>
                  <td>{ev.action}</td>
                  <td>{ev.target}</td>
                </tr>
              ))}
              {!events.length && (
                <tr>
                  <td colSpan={4} className="muted">
                    No events yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}

      {tab === "trash" && (
        <>
          <label>
            Database{" "}
            <select value={db} onChange={(e) => setDb(e.target.value)}>
              {databases.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>{" "}
          <label>
            Collection{" "}
            <select value={coll} onChange={(e) => setColl(e.target.value)}>
              {collections.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="secondary" style={{ marginLeft: "0.5rem" }} onClick={() => loadTrash().catch((e) => setError(String(e)))}>
            Refresh
          </button>
          <table className="data-table" style={{ marginTop: "1rem" }}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Deleted at</th>
                <th>By</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {trash.map((row) => (
                <tr key={row._id}>
                  <td>{row.Name || row._id}</td>
                  <td>{row.deleted_at ?? "—"}</td>
                  <td>{row.deleted_by ?? "—"}</td>
                  <td>
                    <button type="button" onClick={() => restore(row)}>
                      Restore
                    </button>
                  </td>
                </tr>
              ))}
              {!trash.length && (
                <tr>
                  <td colSpan={4} className="muted">
                    Trash is empty for this collection.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
