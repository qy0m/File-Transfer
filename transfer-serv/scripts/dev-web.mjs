import { spawn } from "node:child_process";
import {
  createServer,
  request as proxyRequest
} from "node:http";
import { fileURLToPath } from "node:url";

const publicDirectory = fileURLToPath(
  new URL("../frontend/public/", import.meta.url)
);

let stopping = false;

const php = spawn("php", [
  "-S", "127.0.0.1:8001",
  "-t", publicDirectory
], {
  stdio: "inherit",
  env: {
    ...process.env,
    TRANSFER_API_URL:
      process.env.TRANSFER_API_URL ??
      "http://127.0.0.1:8000",
    UPLOAD_PATH:
      process.env.UPLOAD_PATH ??
      fileURLToPath(
        new URL("../var/uploads/", import.meta.url)
      )
  }
});

const server = createServer({
  requestTimeout: 60_000,
  headersTimeout: 15_000
}, (request, response) => {
  const path = request.url ?? "/";
  const api = path.startsWith("/api/");

  const upstream = proxyRequest({
    hostname: "127.0.0.1",
    port: api ? 3000 : 8001,
    method: request.method,
    path,
    headers: {
      ...request.headers,
      host: api
        ? "127.0.0.1:3000"
        : "127.0.0.1:8001"
    }
  }, incoming => {
    response.writeHead(
      incoming.statusCode ?? 502,
      incoming.headers
    );

    incoming.on("error", () => response.destroy());
    incoming.pipe(response);
  });

  upstream.setTimeout(90_000, () => {
    upstream.destroy(new Error("Upstream timed out"));
  });

  upstream.on("error", () => {
    if (response.headersSent) {
      response.destroy();
      return;
    }

    response.writeHead(502, {
      "Content-Type": "application/json",
      "Cache-Control": "no-store"
    });

    response.end(JSON.stringify({
      detail: api
        ? "Gateway unavailable. Start it on port 3000."
        : "PHP server unavailable."
    }));
  });

  request.on("error", () => upstream.destroy());
  request.on("aborted", () => upstream.destroy());

  response.on("close", () => {
    if (!response.writableEnded) {
      upstream.destroy();
    }
  });

  request.pipe(upstream);
});

function stop(code = 0) {
  if (stopping) {
    return;
  }

  stopping = true;

  server.close();
  server.closeAllConnections();
  php.kill("SIGTERM");
  process.exitCode = code;
}

php.on("error", error => {
  console.error("Could not start PHP:", error.message);
  stop(1);
});

php.on("exit", code => {
  if (!stopping) {
    console.error("PHP stopped. Check the message above.");
    stop(code || 1);
  }
});

server.on("error", error => {
  console.error("Development server failed:", error.message);
  stop(1);
});

server.listen(8080, "127.0.0.1", () => {
  console.log("Open http://127.0.0.1:8080");
});

process.on("SIGINT", () => stop());
process.on("SIGTERM", () => stop());