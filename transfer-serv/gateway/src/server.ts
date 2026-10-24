import {
  createServer,
  type IncomingMessage,
  type ServerResponse
} from "node:http";

const apiUrl = (
  process.env.API_URL ?? "http://api:8000"
).replace(/\/+$/, "");

const port = Number(process.env.PORT ?? "3000");
const host = process.env.HOST ?? "0.0.0.0";

const MAX_METADATA_BYTES = 64 * 1024;
const MAX_CHUNK_BYTES = 8 * 1024 * 1024;
const ID = "[A-Za-z0-9_-]{32}";

const transferRoute = new RegExp(
  `^/transfers/(${ID})$`
);

const statusRoute = new RegExp(
  `^/transfers/(${ID})/upload-status$`
);

const chunkRoute = new RegExp(
  `^/transfers/(${ID})/files/(${ID})/chunks$`
);

class GatewayError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function sendJson(
  response: ServerResponse,
  status: number,
  body: unknown
): void {
  if (response.destroyed || response.writableEnded) {
    return;
  }

  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff"
  });

  response.end(JSON.stringify(body));
}

function requireMethod(
  request: IncomingMessage,
  response: ServerResponse,
  method: string
): void {
  if (request.method !== method) {
    response.setHeader("Allow", method);

    throw new GatewayError(405, "Method not allowed.");
  }
}

async function readBody(
  request: IncomingMessage,
  limit: number
): Promise<Buffer> {
  const length = request.headers["content-length"];

  if (length !== undefined && Number(length) > limit) {
    throw new GatewayError(413, "Request body is too large.");
  }

  const chunks: Buffer[] = [];
  let total = 0;

  for await (const part of request.iterator({
    destroyOnReturn: false
  })) {
    const chunk = Buffer.isBuffer(part)
      ? part
      : Buffer.from(part);

    total += chunk.length;

    if (total > limit) {
      throw new GatewayError(413, "Request body is too large.");
    }

    chunks.push(chunk);
  }

  return Buffer.concat(chunks, total);
}

function requireContentType(
  request: IncomingMessage,
  expected: string
): void {
  const type = (
    request.headers["content-type"] ?? ""
  ).split(";")[0].trim().toLowerCase();

  if (type !== expected) {
    throw new GatewayError(415, `Use ${expected}.`);
  }

  const encoding = request.headers["content-encoding"];

  if (encoding && encoding !== "identity") {
    throw new GatewayError(
      415, "Compressed bodies are unsupported."
    );
  }
}

async function forward(
  request: IncomingMessage,
  response: ServerResponse,
  path: string,
  body?: Buffer,
  contentType?: string
): Promise<void> {
  const headers: Record<string, string> = {
    Accept: "application/json"
  };

  for (const name of [
    "cookie",
    "origin",
    "x-requested-with",
    "x-transfer-client-ip"
  ]) {
    const value = request.headers[name];

    if (value !== undefined) {
      const limit = name === "cookie" ? 8192 : 512;

      if (typeof value !== "string" || value.length > limit) {
        throw new GatewayError(
          400,
          "Invalid account header."
        );
      }

      headers[name] = value;
    }
  }

  const token = request.headers["x-upload-token"];

  if (token !== undefined) {
    if (typeof token !== "string" || token.length > 128) {
      throw new GatewayError(
        400, "Invalid upload token header."
      );
    }

    headers["X-Upload-Token"] = token;
  }

  if (contentType) {
    headers["Content-Type"] = contentType;
  }

  try {
    const upstream = await fetch(`${apiUrl}${path}`, {
      method: request.method,
      headers,
      body: body === undefined
        ? undefined
        : new Uint8Array(body),
      signal: AbortSignal.timeout(30_000),
      redirect: "error"
    });

    const result: unknown = await upstream.json();

    const cookies = upstream.headers.getSetCookie();

    if (cookies.length > 0) {
      response.setHeader("Set-Cookie", cookies);
    }

    const retryAfter = upstream.headers.get("retry-after");

    if (retryAfter && /^\d{1,6}$/.test(retryAfter)) {
      response.setHeader("Retry-After", retryAfter);
    }

    sendJson(response, upstream.status, result);
  } catch (error) {
    if (
      error instanceof Error &&
      error.name === "TimeoutError"
    ) {
      throw new GatewayError(
        504, "Backend request timed out."
      );
    }

    throw new GatewayError(502, "Backend unavailable.");
  }
}

async function health(
  response: ServerResponse
): Promise<void> {
  try {
    const upstream = await fetch(`${apiUrl}/health`, {
      signal: AbortSignal.timeout(5000),
      redirect: "error"
    });

    const body: unknown = await upstream.json();

    if (
      !upstream.ok ||
      typeof body !== "object" ||
      body === null ||
      !("ok" in body) ||
      body.ok !== true
    ) {
      throw new Error("Unhealthy API");
    }

    sendJson(response, 200, {
      ok: true,
      gateway: "node-typescript",
      api: "fastapi",
      database: "sqlite3"
    });
  } catch {
    throw new GatewayError(503, "Backend unavailable.");
  }
}

async function handle(
  request: IncomingMessage,
  response: ServerResponse
): Promise<void> {
  try {
    const url = new URL(
      request.url ?? "/",
      "http://gateway.local"
    );

    const path = url.pathname.startsWith("/api/")
      ? url.pathname.slice(4)
      : url.pathname;

    if (path === "/health") {
      requireMethod(request, response, "GET");
      await health(response);
      return;
    }

    const accountMethods: Record<string, string> = {
      "/auth/register": "POST",
      "/auth/login": "POST",
      "/auth/logout": "POST",
      "/auth/me": "GET",
      "/account/password": "POST",
      "/account/storage": "GET",
      "/guest/storage": "GET"
    };

    const accountMethod = accountMethods[path];

    if (accountMethod) {
      requireMethod(request, response, accountMethod);

      if (accountMethod === "POST") {
        requireContentType(request, "application/json");

        const body = await readBody(request, 8 * 1024);

        await forward(
          request,
          response,
          path,
          body,
          "application/json"
        );
      } else {
        await forward(request, response, path);
      }

      return;
    }

    if (
      new RegExp(`^/account/transfers/(${ID})$`).test(path)
    ) {
      requireMethod(request, response, "DELETE");

      await forward(request, response, path);
      return;
    }

    if (path === "/account/transfers") {
      requireMethod(request, response, "GET");

      const pages = url.searchParams.getAll("page");

      if (
        pages.length > 1 ||
        (
          pages.length === 1 &&
          !/^[1-9]\d{0,6}$/.test(pages[0])
        )
      ) {
        throw new GatewayError(
          400,
          "Invalid dashboard page."
        );
      }

      const page = pages[0] ?? "1";

      await forward(
        request,
        response,
        `${path}?page=${page}`
      );

      return;
    }

    if (path === "/transfers") {
      requireMethod(request, response, "POST");
      requireContentType(request, "application/json");

      const body = await readBody(
        request, MAX_METADATA_BYTES
      );

      await forward(
        request,
        response,
        path,
        body,
        "application/json"
      );

      return;
    }

    if (transferRoute.test(path)) {
      requireMethod(request, response, "GET");
      await forward(request, response, path);
      return;
    }

    if (statusRoute.test(path)) {
      requireMethod(request, response, "GET");
      await forward(request, response, path);
      return;
    }

    if (chunkRoute.test(path)) {
      requireMethod(request, response, "PUT");
      requireContentType(
        request, "application/octet-stream"
      );

      const offsets = url.searchParams.getAll("offset");

      if (
        offsets.length !== 1 ||
        !/^\d+$/.test(offsets[0]) ||
        !Number.isSafeInteger(Number(offsets[0]))
      ) {
        throw new GatewayError(
          400, "Provide one nonnegative integer offset."
        );
      }

      const receiveStarted = performance.now();

      const body = await readBody(
        request, MAX_CHUNK_BYTES
      );

      const receiveFinished = performance.now();
      const offset = Number(offsets[0]);

      await forward(
        request,
        response,
        `${path}?offset=${offset}`,
        body,
        "application/octet-stream"
      );

      const forwardFinished = performance.now();

      console.info(JSON.stringify({
        event: "upload_timing_gateway",
        bytes: body.length,
        receive_ms: Math.round(
          receiveFinished - receiveStarted
        ),
        api_roundtrip_ms: Math.round(
          forwardFinished - receiveFinished
        ),
        total_ms: Math.round(
          forwardFinished - receiveStarted
        )
      }));

      return;
    }

    throw new GatewayError(404, "Not found.");
  } catch (error) {
    if (error instanceof GatewayError) {
      sendJson(response, error.status, {
        detail: error.message
      });
    } else {
      sendJson(response, 500, {
        detail: "Gateway request failed."
      });
    }
  } finally {
    if (!request.destroyed && !request.readableEnded) {
      request.resume();
    }
  }
}

const server = createServer({
  requestTimeout: 150_000,
  headersTimeout: 15_000,
  maxHeaderSize: 16 * 1024
}, (request, response) => {
  void handle(request, response);
});

server.listen(port, host, () => {
  console.log(
    `Gateway listening on http://${host}:${port}`
  );
});

for (const signal of ["SIGTERM", "SIGINT"] as const) {
  process.on(signal, () => {
    server.close(() => {
      process.exit(0);
    });

    server.closeIdleConnections();

    setTimeout(() => {
      server.closeAllConnections();
      process.exit(0);
    }, 10_000).unref();
  });
}
