import { describe, expect, it } from "vitest";
import { parseAppLocation, pathForPage } from "./routes";

describe("parseAppLocation", () => {
  it("maps admin path", () => {
    expect(parseAppLocation("/admin", "").page).toBe("admin");
    expect(pathForPage("admin")).toBe("/admin");
  });

  it("maps compound browse default", () => {
    expect(parseAppLocation("/compounds", "").page).toBe("browse");
  });

  it("parses alignment on search", () => {
    const { page, alignIds } = parseAppLocation("/search/align", "ids=a,b");
    expect(page).toBe("search");
    expect(alignIds).toEqual(["a", "b"]);
  });
});
