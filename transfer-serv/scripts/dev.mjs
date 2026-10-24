import { spawn } from "node:child_process";
import { access, mkdir } from "node:fs/promises";
import { constants } from "node:fs";
import { createServer } from "node:net";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

const root = fileURLToPath(new URL("../", import.meta.url));
const python = resolve(root, ".venv/bin/python");

const apiUrl = "http://127.0.0.1:8000";
const webUrl = "http://127.0.0.1:8080";

const environment = {
  ...process.env,

  DATABASE_PATH: resolve(
    root,
    process.env.DATABASE_PATH ||
      "var/database/transfers.sqlite3"
  ),

  UPLOAD_PATH: resolve(
    root,
    process.env.UPLOAD_PATH || "var/uploads"
  ),

  API_URL: apiUrl,
  TRANSFER_API_URL: apiUrl,
  APP_ORIGIN: webUrl,
  COOKIE_SECURE: "0",
  HOST: "127.0.0.1",
  PORT: "3000"
};

const groups = new Set();

let stopping = false;
let shutdown;

function signalGroup(pid, signal) {
  try {
    process.kill(-pid, signal);
  } catch (error) {
    if (error.code !== "ESRCH") {
      console.error(error.message);
    }
  }
}

function alive(pid) {
  try {
    process.kill(-pid, 0);
    return true;
  } catch (error) {
    return error.code !== "ESRCH";
  }
}

function stop(code = 0) {
  if (shutdown) return shutdown;

  stopping = true;
  process.exitCode = code;

  console.log("\n[dev] Stopping services…");

  const pending = [...groups];

  shutdown = (async () => {
    for (const pid of pending) {
      signalGroup(pid, "SIGTERM");
    }

    const deadline = Date.now() + 5000;

    while (
      pending.some(alive) &&
      Date.now() < deadline
    ) {
      await delay(100);
    }

    for (const pid of pending.filter(alive)) {
      signalGroup(pid, "SIGKILL");
    }
  })();

  return shutdown;
}

process.on("SIGINT", () => {
  void stop();
});

process.on("SIGTERM", () => {
  void stop();
});

function start(name, command, args, service = false) {
  if (stopping) {
    throw new Error("Startup interrupted.");
  }

  console.log(`[dev] ${name}`);

  const child = spawn(command, args, {
    cwd: root,
    env: environment,
    stdio: "inherit",
    detached: true
  });

  if (child.pid) {
    groups.add(child.pid);
  }

  child.once("close", () => {
    groups.delete(child.pid);
  });

  if (service) {
    child.once("error", error => {
      if (!stopping) {
        console.error(
          `[dev] ${name} could not start: ${error.message}`
        );

        void stop(1);
      }
    });

    child.once("exit", (code, signal) => {
      if (!stopping) {
        console.error(
          `[dev] ${name} stopped (${signal || code}). ` +
          "See its output above."
        );

        void stop(1);
      }
    });
  }

  return child;
}

function run(name, command, args) {
  const child = start(name, command, args);

  return new Promise((accept, reject) => {
    child.once("error", error => {
      reject(new Error(`${name}: ${error.message}`));
    });

    child.once("close", code => {
      if (code === 0) {
        accept();
      } else {
        reject(new Error(
          `${name} failed. See the output above.`
        ));
      }
    });
  });
}

async function requireFile(path, mode, message) {
  try {
    await access(resolve(root, path), mode);
  } catch {
    throw new Error(message);
  }
}

function checkPort(port) {
  return new Promise((accept, reject) => {
    const probe = createServer();

    probe.once("error", error => {
      reject(new Error(
        `Port ${port} is unavailable (${error.code}). ` +
        "Stop the old service and retry."
      ));
    });

    probe.listen(port, "127.0.0.1", () => {
      probe.close(accept);
    });
  });
}

async function ready(name, url, json = true) {
  const deadline = Date.now() + 30000;

  while (!stopping && Date.now() < deadline) {
    try {
      const response = await fetch(url, {
        signal: AbortSignal.timeout(2000),
        redirect: "error"
      });

      if (json) {
        const body = await response.json();

        if (response.ok && body?.ok === true) {
          return;
        }
      } else {
        await response.body?.cancel();

        if (response.ok) {
          return;
        }
      }
    } catch {
      // Services may need a moment to bind their ports.
    }

    await delay(250);
  }

  throw new Error(
    `${name} did not become ready at ${url}. ` +
    "Check its output above."
  );
}

async function main() {
  if (process.platform !== "linux") {
    throw new Error(
      "This development launcher currently supports Linux."
    );
  }

  await requireFile(
    ".venv/bin/python",
    constants.X_OK,
    "Missing .venv/bin/python. Create the virtual " +
    "environment and install api/requirements.txt."
  );

  await requireFile(
    "node_modules/typescript/bin/tsc",
    constants.R_OK,
    "Node dependencies are missing. Run npm install first."
  );

  await requireFile(
    "scripts/dev-web.mjs",
    constants.R_OK,
    "Missing scripts/dev-web.mjs."
  );

  for (const port of [8000, 3000, 8001, 8080]) {
    await checkPort(port);
  }

  await run("Checking PHP", "php", ["--version"]);

  await run("Checking Python dependencies", python, [
    "-c",
    "import uvicorn, fastapi, argon2"
  ]);

  await run("Checking Python syntax", python, [
    "-m",
    "compileall",
    "-q",
    "api/app"
  ]);

  await run("Building frontend and gateway", "npm", [
    "run",
    "build"
  ]);

  await mkdir(environment.UPLOAD_PATH, {
    recursive: true
  });

  console.log(
    `[dev] Database: ${environment.DATABASE_PATH}`
  );

  console.log(
    `[dev] Uploads:  ${environment.UPLOAD_PATH}`
  );

  start("API", python, [
    "-m",
    "uvicorn",
    "app.main:app",
    "--app-dir",
    "api",
    "--host",
    "127.0.0.1",
    "--port",
    "8000"
  ], true);

  await ready("API", `${apiUrl}/health`);

  start(
    "Gateway",
    process.execPath,
    ["gateway/dist/server.js"],
    true
  );

  await ready(
    "Gateway",
    "http://127.0.0.1:3000/api/health"
  );

  start(
    "Website and PHP",
    process.execPath,
    ["scripts/dev-web.mjs"],
    true
  );

  await ready("Website", webUrl, false);

  await ready(
    "Website API proxy",
    `${webUrl}/api/health`
  );

  if (!stopping) {
    console.log(
      `\n[dev] Ready: ${webUrl}\n` +
      "[dev] Press Ctrl+C to stop everything.\n"
    );
  }
}

try {
  await main();
} catch (error) {
  if (!stopping) {
    console.error(`\n[dev] ${error.message}`);
    await stop(1);
  }
}