import { useEffect, useMemo, useState } from "react";
import type { CompoundSchema } from "../types";
import KetcherEditor, { looksLikeQuery } from "./KetcherEditor";

export default function CompoundForm({
  schema,
  initial,
  onSubmit,
  onCancel,
}: {
  schema: CompoundSchema;
  initial: Record<string, unknown>;
  onSubmit: (data: Record<string, unknown>, unset: string[]) => Promise<void>;
  onCancel?: () => void;
}) {
  const [values, setValues] = useState<Record<string, unknown>>({ ...initial });
  const [drawField, setDrawField] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [extraKey, setExtraKey] = useState("");
  const [extraValue, setExtraValue] = useState("");
  const docId = String(initial._id ?? "new");

  useEffect(() => {
    setValues({ ...initial });
    setDrawField(null);
    setError("");
    setExtraKey("");
    setExtraValue("");
    // Identity is the selected document; don't reset on every parent render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId]);

  const fieldNames = useMemo(() => {
    const known = Object.keys(schema.fields);
    const extras = Object.keys(values).filter((k) => k !== "_id" && !known.includes(k));
    return [...known, ...extras];
  }, [schema.fields, values]);

  function setField(key: string, value: unknown) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  async function applyStructure(smiles: string, molfile: string) {
    setDrawField(null);
    if (!drawField) return;
    if (looksLikeQuery(smiles)) {
      setField(drawField, smiles);
      return;
    }
    try {
      const converted = await fetch("/api/chem/from-molfile", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ molfile }),
      });
      if (converted.ok) {
        const body = await converted.json();
        setField(drawField, body.smiles);
        return;
      }
    } catch {
      /* fall through to raw SMILES */
    }
    setField(drawField, smiles);
  }

  async function submit() {
    if (drawField) return;
    setError("");
    const data: Record<string, unknown> = { ...values };
    delete data._id;
    const unset = Object.keys(initial).filter(
      (key) => key !== "_id" && !(key in data)
    );
    try {
      await onSubmit(data, unset);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  return (
    <form
      className="form"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      {fieldNames.map((key) => {
        const spec = schema.fields[key];
        const type = spec?.type || typeof values[key];
        const value = values[key];
        return (
          <div className="form-row" key={key}>
            <label>{key}</label>
            {type === "boolean" ? (
              <input
                type="checkbox"
                checked={Boolean(value)}
                onChange={(e) => setField(key, e.target.checked)}
              />
            ) : type === "float" ? (
              <input
                type="number"
                step="any"
                value={value === undefined || value === null ? "" : String(value)}
                onChange={(e) => setField(key, e.target.value === "" ? 0 : Number(e.target.value))}
              />
            ) : (
              <input
                value={value === undefined || value === null ? "" : String(value)}
                onChange={(e) => setField(key, e.target.value)}
              />
            )}
            {key === "SMILES" && (
              <button type="button" className="secondary" onClick={() => setDrawField(key)}>
                Draw
              </button>
            )}
            {key !== "SMILES" && spec && <span />}
            {!spec && (
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setValues((prev) => {
                    const next = { ...prev };
                    delete next[key];
                    return next;
                  });
                }}
              >
                Remove
              </button>
            )}
          </div>
        );
      })}
      <div className="form-row">
        <input placeholder="extra field" value={extraKey} onChange={(e) => setExtraKey(e.target.value)} />
        <input placeholder="value" value={extraValue} onChange={(e) => setExtraValue(e.target.value)} />
        <button
          type="button"
          className="secondary"
          onClick={() => {
            if (!extraKey.trim()) return;
            setField(extraKey.trim(), extraValue);
            setExtraKey("");
            setExtraValue("");
          }}
        >
          Add field
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button type="submit">Save</button>
        {onCancel && (
          <button type="button" className="secondary" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
      {drawField && (
        <KetcherEditor
          initial={String(values[drawField] || "")}
          onApply={applyStructure}
          onClose={() => setDrawField(null)}
        />
      )}
    </form>
  );
}
