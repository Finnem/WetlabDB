import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import type { CollectionAccessPolicy } from "../types";

const VISIBILITY_OPTIONS: CollectionAccessPolicy["visibility"][] = [
  "employees_and_students",
  "owner_only",
  "employees",
  "students",
  "custom",
];

const CAP_OPTIONS: CollectionAccessPolicy["student_access"][] = ["none", "viewer", "editor"];

function policyKey(p: CollectionAccessPolicy) {
  return `${p.database}/${p.collection}`;
}

export default function Permissions() {
  const [policies, setPolicies] = useState<CollectionAccessPolicy[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [draft, setDraft] = useState<CollectionAccessPolicy | null>(null);
  const [customUsersText, setCustomUsersText] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    const body = await api.collectionPolicies();
    setPolicies(body.policies);
    if (!selectedKey && body.policies.length) {
      setSelectedKey(policyKey(body.policies[0]));
    }
  }

  useEffect(() => {
    refresh().catch((err) => setError(String(err)));
  }, []);

  useEffect(() => {
    const found = policies.find((p) => policyKey(p) === selectedKey) ?? null;
    setDraft(found ? { ...found, custom_users: [...found.custom_users] } : null);
    setCustomUsersText(found?.custom_users.join(", ") ?? "");
  }, [selectedKey, policies]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setError("");
    setMessage("");
    const custom_users = customUsersText
      .split(/[,;\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      const saved = await api.putCollectionPolicy(draft.database, draft.collection, {
        owner: draft.owner,
        visibility: draft.visibility,
        custom_users,
        student_access: draft.student_access,
        employee_access: draft.employee_access,
      });
      setMessage(`Saved ${saved.database}/${saved.collection}`);
      await refresh();
      setSelectedKey(policyKey(saved));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save policy");
    }
  }

  if (!policies.length) {
    return (
      <div className="search-page">
        <div className="panel">
          <h2>Permissions</h2>
          <p className="muted">No collections you can manage yet.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="search-page">
      <div className="panel">
        <h2>Collection permissions</h2>
        <p className="muted">
          Control who can view or edit each collection. Owner-only collections are visible only to the
          owner and admins.
        </p>
        <label>
          Collection
          <select value={selectedKey} onChange={(e) => setSelectedKey(e.target.value)}>
            {policies.map((p) => (
              <option key={policyKey(p)} value={policyKey(p)}>
                {p.database} / {p.collection}
              </option>
            ))}
          </select>
        </label>
        {draft && (
          <form className="form" onSubmit={submit} style={{ marginTop: "1rem", maxWidth: "32rem" }}>
            <label>
              Owner (username)
              <input
                value={draft.owner ?? ""}
                onChange={(e) =>
                  setDraft({ ...draft, owner: e.target.value.trim() || null })
                }
                placeholder="optional"
              />
            </label>
            <label>
              Visibility
              <select
                value={draft.visibility}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    visibility: e.target.value as CollectionAccessPolicy["visibility"],
                  })
                }
              >
                {VISIBILITY_OPTIONS.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            {draft.visibility === "custom" && (
              <label>
                Allowed users (comma-separated)
                <input
                  value={customUsersText}
                  onChange={(e) => setCustomUsersText(e.target.value)}
                  placeholder="alice, bob"
                />
              </label>
            )}
            <label>
              Student access
              <select
                value={draft.student_access}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    student_access: e.target.value as CollectionAccessPolicy["student_access"],
                  })
                }
              >
                {CAP_OPTIONS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Employee access
              <select
                value={draft.employee_access}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    employee_access: e.target.value as CollectionAccessPolicy["employee_access"],
                  })
                }
              >
                {CAP_OPTIONS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            {error && <p className="error">{error}</p>}
            {message && <p className="ok">{message}</p>}
            <button type="submit">Save policy</button>
          </form>
        )}
      </div>
    </div>
  );
}
