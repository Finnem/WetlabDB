import { Component, lazy, Suspense, useEffect, useRef, useState, type ErrorInfo, type ReactNode } from "react";

type KetcherHandle = {
  getSmiles: () => Promise<string> | string;
  getMolfile: () => Promise<string> | string;
  getSmarts?: () => Promise<string> | string;
  setMolecule?: (mol: string) => Promise<void> | void;
  editor?: { tool: (name: string, opts?: unknown) => unknown };
};

const QUERY_ATOMS: { label: string; pseudo: string; title: string }[] = [
  { label: "A", pseudo: "A", title: "Any heavy atom (not H)" },
  { label: "X", pseudo: "X", title: "Any halogen (F, Cl, Br, I)" },
  { label: "*", pseudo: "AH", title: "Any atom, including H" },
];

export function looksLikeQuery(text: string): boolean {
  return /\[[^\]]*,[^\]]*\]/.test(text) || text.includes("*") || /\[[^\]]*![^\]]*\]/.test(text);
}

class EditorErrorBoundary extends Component<{ children: ReactNode }, { message: string }> {
  state = { message: "" };

  static getDerivedStateFromError(error: Error) {
    return { message: error.message || "Editor failed to load" };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Ketcher failed", error, info.componentStack);
  }

  render() {
    if (this.state.message) {
      return <p className="error" style={{ padding: "1rem" }}>{this.state.message}</p>;
    }
    return this.props.children;
  }
}

const LazyEditor = lazy(async () => {
  const [{ Editor }, { StandaloneStructServiceProvider }] = await Promise.all([
    import("ketcher-react"),
    import("ketcher-standalone"),
  ]);
  await import("ketcher-react/dist/index.css");
  const provider = new StandaloneStructServiceProvider();

  function Inner({
    initial,
    onReady,
  }: {
    initial: string;
    onReady: (k: KetcherHandle) => void;
  }) {
    return (
      <div className="ketcher-host">
        <Editor
          staticResourcesUrl="./"
          structServiceProvider={provider}
          errorHandler={(msg: string) => console.error(msg)}
          onInit={(ketcher: KetcherHandle) => {
            onReady(ketcher);
            if (initial) ketcher.setMolecule?.(initial);
          }}
        />
      </div>
    );
  }

  return { default: Inner };
});

export default function KetcherEditor({
  initial = "",
  onApply,
  onClose,
}: {
  initial?: string;
  onApply: (smiles: string, molfile: string) => void;
  onClose: () => void;
}) {
  const ketcherRef = useRef<KetcherHandle | null>(null);
  const [error, setError] = useState("");
  const [activeQuery, setActiveQuery] = useState("");

  useEffect(() => {
    setError("");
  }, [initial]);

  function selectQuery(pseudo: string) {
    const ketcher = ketcherRef.current;
    if (!ketcher?.editor?.tool) {
      setError("Editor is still loading");
      return;
    }
    ketcher.editor.tool("atom", { type: "gen", label: pseudo, pseudo });
    setActiveQuery(pseudo);
    setError("");
  }

  async function apply() {
    const ketcher = ketcherRef.current;
    if (!ketcher) {
      setError("Editor is still loading");
      return;
    }
    try {
      const [smiles, molfile, smarts] = await Promise.all([
        Promise.resolve(ketcher.getSmiles()),
        Promise.resolve(ketcher.getMolfile()),
        ketcher.getSmarts ? Promise.resolve(ketcher.getSmarts()) : Promise.resolve(""),
      ]);
      const smartsText = String(smarts || "");
      const smilesText = String(smiles || "");
      const queryText = looksLikeQuery(smartsText) ? smartsText : smilesText || smartsText;
      onApply(queryText, String(molfile || ""));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read structure");
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal">
        <header>
          <strong>Draw molecule</strong>
          <span className="muted">Query atoms for substructure search:</span>
          {QUERY_ATOMS.map((atom) => (
            <button
              key={atom.pseudo}
              type="button"
              className={activeQuery === atom.pseudo ? "" : "secondary"}
              title={atom.title}
              onClick={() => selectQuery(atom.pseudo)}
            >
              {atom.label}
            </button>
          ))}
        </header>
        <EditorErrorBoundary>
          <Suspense fallback={<p className="muted" style={{ padding: "1rem" }}>Loading editor…</p>}>
            <LazyEditor initial={initial} onReady={(k) => (ketcherRef.current = k)} />
          </Suspense>
        </EditorErrorBoundary>
        <footer>
          {error && <span className="error">{error}</span>}
          <button type="button" className="secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="button" onClick={apply}>
            Apply
          </button>
        </footer>
      </div>
    </div>
  );
}
