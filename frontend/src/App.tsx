import { useCallback, useEffect, useState, type MouseEvent, type ReactNode } from "react";
import { api } from "./api";
import Browser from "./pages/Browser";
import Login from "./pages/Login";
import Search from "./pages/Search";
import Users from "./pages/Users";
import Alignment from "./pages/Alignment";
import {
  alignPath,
  navigateTo,
  parseAppLocation,
  pathForPage,
  readAppLocation,
  type AppPage,
} from "./routes";
import type { User } from "./types";

function TopNavLink({
  href,
  active,
  onNavigate,
  children,
}: {
  href: string;
  active: boolean;
  onNavigate: () => void;
  children: ReactNode;
}) {
  return (
    <a
      href={href}
      className={active ? "active" : ""}
      onClick={(e: MouseEvent<HTMLAnchorElement>) => {
        if (e.defaultPrevented) return;
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        onNavigate();
      }}
    >
      {children}
    </a>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [page, setPage] = useState<AppPage>(() => readAppLocation().page);
  const [db, setDb] = useState(localStorage.getItem("wetlabdb.db") || "");
  const [coll, setColl] = useState(localStorage.getItem("wetlabdb.coll") || "");
  const [exportIds, setExportIds] = useState<string[] | null>(() => readAppLocation().alignIds);

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

  const applyLocation = useCallback(
    (pathname: string, search: string) => {
      const { page: nextPage, alignIds } = parseAppLocation(pathname, search);
      if (nextPage === "users" && !user?.admin) {
        setPage("browse");
        setExportIds(null);
        navigateTo("/compounds", true);
        return;
      }
      setPage(nextPage);
      setExportIds(alignIds);
    },
    [user]
  );

  useEffect(() => {
    if (!user) return;
    if (window.location.pathname === "/") {
      navigateTo("/compounds", true);
    }
    applyLocation(window.location.pathname, window.location.search);
  }, [user, applyLocation]);

  useEffect(() => {
    if (!user) return;
    const onPopState = () => applyLocation(window.location.pathname, window.location.search);
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [user, applyLocation]);

  const goToPage = useCallback(
    (next: AppPage) => {
      setExportIds(null);
      setPage(next);
      navigateTo(pathForPage(next));
    },
    []
  );

  const openAlignment = useCallback(
    (ids: string[]) => {
      if (!ids.length) return;
      setExportIds(ids);
      navigateTo(alignPath(page, ids));
    },
    [page]
  );

  const closeAlignment = useCallback(() => {
    setExportIds(null);
    navigateTo(pathForPage(page));
  }, [page]);

  if (!ready) return <p className="muted" style={{ padding: "2rem" }}>Loading…</p>;
  if (!user) return <Login onLogin={setUser} />;

  const showAlign = Boolean(exportIds?.length && db && coll);

  return (
    <div className="shell">
      <header className="topbar">
        <h1>
          <a className="topbar-brand" href="/compounds" onClick={(e) => {
            if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
            e.preventDefault();
            goToPage("browse");
          }}>
            WetlabDB
          </a>
        </h1>
        <nav>
          <TopNavLink
            href="/compounds"
            active={page === "browse" && !showAlign}
            onNavigate={() => goToPage("browse")}
          >
            Compounds
          </TopNavLink>
          <TopNavLink href="/search" active={page === "search"} onNavigate={() => goToPage("search")}>
            Molecular search
          </TopNavLink>
          {user.admin && (
            <TopNavLink href="/users" active={page === "users"} onNavigate={() => goToPage("users")}>
              Users
            </TopNavLink>
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
      <div className="shell-body">
        {page === "browse" && (
          <Browser
            user={user}
            db={db}
            coll={coll}
            onDb={setDb}
            onColl={setColl}
            onExportMolecules={openAlignment}
          />
        )}
        {page === "search" && (
          <Search db={db} coll={coll} onExportMolecules={openAlignment} />
        )}
        {page === "users" && user.admin && <Users />}
        {showAlign && exportIds && (
          <Alignment
            db={db}
            coll={coll}
            initialSelectedIds={exportIds}
            onClose={closeAlignment}
          />
        )}
      </div>
    </div>
  );
}
