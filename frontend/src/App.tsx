import { useEffect, useState } from "react";
import { api } from "./api";
import Browser from "./pages/Browser";
import Login from "./pages/Login";
import Search from "./pages/Search";
import Users from "./pages/Users";
import type { User } from "./types";

type Page = "browse" | "search" | "users";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [page, setPage] = useState<Page>("browse");
  const [db, setDb] = useState(localStorage.getItem("wetlabdb.db") || "");
  const [coll, setColl] = useState(localStorage.getItem("wetlabdb.coll") || "");

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    if (db) localStorage.setItem("wetlabdb.db", db);
    if (coll) localStorage.setItem("wetlabdb.coll", coll);
  }, [db, coll]);

  if (!ready) return <p className="muted" style={{ padding: "2rem" }}>Loading…</p>;
  if (!user) return <Login onLogin={setUser} />;

  return (
    <div className="shell">
      <header className="topbar">
        <h1>WetlabDB</h1>
        <nav>
          <button className={page === "browse" ? "active" : ""} onClick={() => setPage("browse")}>
            Compounds
          </button>
          <button className={page === "search" ? "active" : ""} onClick={() => setPage("search")}>
            Molecular search
          </button>
          {user.admin && (
            <button className={page === "users" ? "active" : ""} onClick={() => setPage("users")}>
              Users
            </button>
          )}
        </nav>
        <span className="spacer" />
        <span className="who">
          {user.username}
          {user.admin ? " (admin)" : ""}
        </span>
        <button
          className="secondary"
          onClick={async () => {
            await api.logout();
            setUser(null);
          }}
        >
          Log out
        </button>
      </header>
      {page === "browse" && (
        <Browser user={user} db={db} coll={coll} onDb={setDb} onColl={setColl} />
      )}
      {page === "search" && <Search db={db} coll={coll} />}
      {page === "users" && user.admin && <Users />}
    </div>
  );
}
