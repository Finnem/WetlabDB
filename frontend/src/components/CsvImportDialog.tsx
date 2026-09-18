import { useMemo, useState } from "react";

export type CollisionMode = "append" | "overwrite";

export default function CsvImportDialog({
  headers,
  defaultIdentifier,
  onCancel,
  onImport,
}: {
  headers: string[];
  defaultIdentifier: string;
  onCancel: () => void;
  onImport: (opts: {
    identifier: string;
    dataCols: string[];
    onCollision: CollisionMode;
  }) => void;
}) {
  const [identifier, setIdentifier] = useState(defaultIdentifier);
  const [selected, setSelected] = useState<string[]>(() =>
    headers.filter((col) => col !== defaultIdentifier)
  );
  const [onCollision, setOnCollision] = useState<CollisionMode>("append");

  const dataChoices = useMemo(
    () => headers.filter((col) => col !== identifier),
    [headers, identifier]
  );

  function toggleColumn(column: string, checked: boolean) {
    setSelected((prev) => {
      const next = prev.filter((col) => col !== column && col !== identifier);
      if (checked) next.push(column);
      return next;
    });
  }

  return (
    <div className="modal-backdrop">
      <div className="modal dialog">
        <header>
          <strong>Import CSV</strong>
        </header>
        <div className="dialog-body">
          <label>
            Identifier column
            <select
              value={identifier}
              onChange={(e) => {
                const next = e.target.value;
                const previous = identifier;
                setIdentifier(next);
                setSelected((prev) => {
                  const nextSelected = prev.filter((col) => col !== next);
                  if (previous !== next && headers.includes(previous) && !nextSelected.includes(previous)) {
                    nextSelected.push(previous);
                  }
                  return nextSelected;
                });
              }}
            >
              {headers.map((col) => (
                <option key={col}>{col}</option>
              ))}
            </select>
          </label>
          <fieldset>
            <legend>Data columns</legend>
            {dataChoices.map((col) => (
              <label key={col}>
                <input
                  type="checkbox"
                  checked={selected.includes(col)}
                  onChange={(e) => toggleColumn(col, e.target.checked)}
                />
                {col}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend>On ID collision</legend>
            <label>
              <input
                type="radio"
                name="on-collision"
                checked={onCollision === "append"}
                onChange={() => setOnCollision("append")}
              />
              Append (keep existing values; write differences as alternative fields)
            </label>
            <label>
              <input
                type="radio"
                name="on-collision"
                checked={onCollision === "overwrite"}
                onChange={() => setOnCollision("overwrite")}
              />
              Overwrite matching records
            </label>
            <p className="muted">
              Append stores a colliding Name as <code>alternative Name</code>, and
              other colliding columns as <code>alternative …</code>.
            </p>
          </fieldset>
        </div>
        <footer>
          <button type="button" className="secondary" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            onClick={() =>
              onImport({
                identifier,
                dataCols: selected.filter((col) => col !== identifier),
                onCollision,
              })
            }
          >
            Import
          </button>
        </footer>
      </div>
    </div>
  );
}
