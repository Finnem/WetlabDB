export type AppPage = "browse" | "search" | "users";

export function pathForPage(page: AppPage): string {
  if (page === "search") return "/search";
  if (page === "users") return "/users";
  return "/compounds";
}

export function alignPath(page: AppPage, ids: string[]): string {
  const base = pathForPage(page);
  const params = new URLSearchParams();
  if (ids.length) params.set("ids", ids.join(","));
  const q = params.toString();
  return q ? `${base}/align?${q}` : `${base}/align`;
}

export function parseAppLocation(pathname: string, search: string): {
  page: AppPage;
  alignIds: string[] | null;
} {
  const path = pathname.replace(/\/+$/, "") || "/";
  const params = new URLSearchParams(search);

  const alignSuffix = "/align";
  if (path.endsWith(alignSuffix)) {
    const raw = params.get("ids") ?? "";
    const alignIds = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const base = path.slice(0, -alignSuffix.length) || "/";
    let page: AppPage = "browse";
    if (base === "/search") page = "search";
    else if (base === "/users") page = "users";
    return { page, alignIds: alignIds.length ? alignIds : [] };
  }

  if (path === "/align") {
    const raw = params.get("ids") ?? "";
    const alignIds = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    return { page: "browse", alignIds: alignIds.length ? alignIds : [] };
  }

  let page: AppPage = "browse";
  if (path === "/search") page = "search";
  else if (path === "/users") page = "users";
  else if (path === "/" || path === "/compounds") page = "browse";

  return { page, alignIds: null };
}

export function readAppLocation(): { page: AppPage; alignIds: string[] | null } {
  return parseAppLocation(window.location.pathname, window.location.search);
}

export function navigateTo(path: string, replace = false): void {
  if (replace) {
    window.history.replaceState(null, "", path);
  } else {
    window.history.pushState(null, "", path);
  }
}
