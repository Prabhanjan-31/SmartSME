/**
 * The request wrapper, which is where the frontend and the API agree on shape.
 *
 * This file exists because a bug lived here undetected: `request()` set
 * `Content-Type: application/json` whenever a body was present, including when
 * that body was a `FormData`. The browser then never set its own
 * `multipart/form-data; boundary=...`, and the boundary is generated per
 * request, so nothing else can supply it. FastAPI found no `file` field and
 * answered 422 "Field required". Image upload never worked from the UI.
 *
 * The backend suite could not have caught it: every test there posts multipart
 * directly, which skips this function entirely. A contract only one side is
 * tested against is not a tested contract.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, isSessionExpiry, isUnauthorized, onDataChanged } from "./api";

type Captured = { url: string; init: RequestInit };

function captureFetch(response: unknown = {}, status = 200): () => Captured {
  const calls: Captured[] = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return Promise.resolve(
      new Response(JSON.stringify(response), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });
  return () => calls[calls.length - 1];
}

function headerOf(init: RequestInit, name: string): string | undefined {
  const headers = (init.headers ?? {}) as Record<string, string>;
  const key = Object.keys(headers).find((k) => k.toLowerCase() === name.toLowerCase());
  return key ? headers[key] : undefined;
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("content type", () => {
  it("does not set one for a file upload, so the browser can add the boundary", async () => {
    const last = captureFetch({ draft: {} });
    const file = new File([new Uint8Array([1, 2, 3])], "slip.jpg", { type: "image/jpeg" });

    await api.upload("/input/parse-image", file);

    const { init } = last();
    expect(headerOf(init, "content-type")).toBeUndefined();
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBeInstanceOf(File);
  });

  it("sets application/json for a JSON body", async () => {
    const last = captureFetch({ ok: true });

    await api.post("/sales", { partyId: "x" });

    const { init } = last();
    expect(headerOf(init, "content-type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ partyId: "x" }));
  });

  it("sets none for a request with no body at all", async () => {
    const last = captureFetch({ rows: [] });

    await api.get("/products");

    expect(headerOf(last().init, "content-type")).toBeUndefined();
  });
});

describe("errors", () => {
  it("reads FastAPI's single-string detail", async () => {
    captureFetch({ detail: "That image is too large. Try a smaller photo." }, 413);

    await expect(api.get("/anything")).rejects.toThrow(/too large/);
  });

  it("reads FastAPI's validation list, which arrives as objects not strings", async () => {
    captureFetch({ detail: [{ loc: ["body", "file"], msg: "Field required" }] }, 422);

    await expect(api.get("/anything")).rejects.toThrow(/Field required/);
  });

  it("falls back to the status when the body is not JSON", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(new Response("<html>502</html>", { status: 502 })),
    );

    await expect(api.get("/anything")).rejects.toThrow(/502/);
  });
});

describe("requests carry the session", () => {
  it("always sends cookies, because auth is a cookie", async () => {
    const last = captureFetch({ rows: [] });

    await api.get("/products");

    expect(last().init.credentials).toBe("include");
  });

  it("prefixes /api once", async () => {
    const last = captureFetch({ rows: [] });

    await api.get("/products");

    expect(last().url.startsWith("/api/products")).toBe(true);
    expect(last().url).not.toContain("/api/api");
  });
});

describe("401 handling", () => {
  // A 401 means two opposite things depending on which request got it, and the
  // wrong reading is what hid "wrong password" from the login page: a rejected
  // credential was treated as an expired session, so the app reloaded the very
  // page that was about to show the error.
  it("treats a 401 on sign-in as an answer, not an expiry", async () => {
    captureFetch({ detail: "Incorrect email or password." }, 401);

    await expect(api.post("/auth/sign-in", { email: "a", password: "b" })).rejects.toSatisfy(
      (e: unknown) => isUnauthorized(e) && !isSessionExpiry(e),
    );
  });

  it("treats a 401 anywhere else as the session running out", async () => {
    captureFetch({ detail: "Not signed in." }, 401);

    await expect(api.get("/dashboard")).rejects.toSatisfy(
      (e: unknown) => isUnauthorized(e) && isSessionExpiry(e),
    );
  });

  it("carries the failed path on the error, which is what makes that possible", async () => {
    captureFetch({ detail: "nope" }, 401);

    await api.post("/auth/sign-in", {}).catch((e: ApiError) => {
      expect(e.path).toBe("/auth/sign-in");
      expect(e.status).toBe(401);
    });
  });
});

describe("telling the shell that something changed", () => {
  // The bell's unread count lives in the shell, which is never remounted. It
  // used to refetch only when the route changed, so "Mark read" left the red
  // number in place until you left the Notifications page.
  function listen(): { heard: () => number; stop: () => void } {
    let count = 0;
    const stop = onDataChanged(() => {
      count += 1;
    });
    return { heard: () => count, stop };
  }

  it("speaks up after a write that worked", async () => {
    captureFetch({ ok: true });
    const { heard, stop } = listen();

    await api.post("/notifications/abc/read");
    expect(heard()).toBe(1);
    await api.del("/notifications/abc");
    expect(heard()).toBe(2);
    await api.patch("/sales/abc", { date: "2026-11-10" });
    expect(heard()).toBe(3);

    stop();
  });

  it("stays quiet for a read, or every refetch would trigger the next", async () => {
    captureFetch({ unread: 3 });
    const { heard, stop } = listen();

    await api.get("/notifications/unread-count");

    expect(heard()).toBe(0);
    stop();
  });

  it("stays quiet when the write was refused", async () => {
    captureFetch({ detail: "A payment cannot be dated in the future." }, 400);
    const { heard, stop } = listen();

    await expect(api.post("/sales/abc/payments", { amount: 10 })).rejects.toThrow(/future/);

    expect(heard()).toBe(0);
    stop();
  });

  it("stays quiet for signing in and out, which change who is asking", async () => {
    captureFetch({ ok: true });
    const { heard, stop } = listen();

    await api.post("/auth/sign-out");
    await api.post("/auth/sign-in", { email: "a", password: "b" });

    expect(heard()).toBe(0);
    stop();
  });

  it("stops telling a listener that has unsubscribed", async () => {
    captureFetch({ ok: true });
    const { heard, stop } = listen();

    await api.post("/notifications/read-all");
    stop();
    await api.post("/notifications/read-all");

    expect(heard()).toBe(1);
  });
});
