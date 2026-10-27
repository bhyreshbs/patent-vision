import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, getToken, setToken, toApiError } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("token storage", () => {
  it("stores and clears the token", () => {
    expect(getToken()).toBeNull();
    setToken("abc");
    expect(getToken()).toBe("abc");
    setToken(null);
    expect(getToken()).toBeNull();
  });
});

describe("toApiError", () => {
  it("reads the structured backend error", async () => {
    const res = new Response(
      JSON.stringify({ error: { code: "corrupt_image", message: "Bad file.", next_action: "Upload another." } }),
      { status: 422 },
    );
    const err = await toApiError(res);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe("Bad file.");
    expect(err.code).toBe("corrupt_image");
    expect(err.nextAction).toBe("Upload another.");
    expect(err.status).toBe(422);
  });
  it("includes the first validation detail", async () => {
    const res = new Response(
      JSON.stringify({ error: { code: "validation_error", message: "Request validation failed.", details: [{ field: "name", message: "too short" }] } }),
      { status: 422 },
    );
    expect((await toApiError(res)).message).toContain("name: too short");
  });
  it("falls back for non-JSON bodies", async () => {
    const err = await toApiError(new Response("oops", { status: 500 }));
    expect(err.message).toBe("Request failed (500).");
  });
});

describe("api client", () => {
  it("sends the bearer token and JSON body", async () => {
    setToken("tok");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: 1, name: "P" }), { status: 201 }),
    );
    await api.createProject("P", "d");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/projects$/);
    const headers = new Headers((init as RequestInit).headers);
    expect(headers.get("Authorization")).toBe("Bearer tok");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect((init as RequestInit).body).toBe(JSON.stringify({ name: "P", description: "d" }));
  });
  it("does not force a JSON content type on uploads", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 201 }));
    await api.uploadImage(1, new File(["x"], "a.png", { type: "image/png" }), "Front");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.body).toBeInstanceOf(FormData);
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
  });
  it("throws ApiError with the server message and handles 204", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: { code: "not_found", message: "Project not found." } }), { status: 404 }),
    );
    await expect(api.getProject(5)).rejects.toMatchObject({ status: 404, message: "Project not found." });
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(api.deleteProject(5)).resolves.toBeUndefined();
  });
  it("reports network failures clearly", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("failed"));
    await expect(api.me()).rejects.toMatchObject({ code: "network", status: 0 });
  });
});
