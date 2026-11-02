import {
  decryptManifest,
  decode64,
  importKey,
  wireSize,
  type SecretFile
} from "./encryption.js";

type FileRecord = SecretFile & { id: string };

let registration: Promise<ServiceWorkerRegistration> | undefined;

export function prepareEncryptedDownloads(): Promise<ServiceWorkerRegistration> {
  if (!isSecureContext || !crypto.subtle || !("serviceWorker" in navigator)) {
    return Promise.reject(new Error(
      "Encrypted transfers require HTTPS, Web Crypto, and service workers. Enable them in your browser."
    ));
  }

  return registration ??= (async () => {
    await navigator.serviceWorker.register("/e2ee-worker.js", {
      scope: "/",
      updateViaCache: "none"
    });

    let timer: ReturnType<typeof setTimeout> | undefined;

    try {
      const ready = await Promise.race([
        navigator.serviceWorker.ready,
        new Promise<never>((_, reject) => {
          timer = setTimeout(() => reject(new Error(
            "Encrypted download support could not start. Check your browser permissions and refresh."
          )), 15000);
        })
      ]);

      if (!ready.active) {
        throw new Error(
          "Download support is unavailable. Refresh and retry."
        );
      }

      // The current page need not be controlled.
      // Downloads use a fresh navigation handled by the active worker.
      return ready;
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
  })().catch(error => {
    registration = undefined;
    throw error;
  });
}

async function initialize(panel: HTMLElement): Promise<void> {
  const status = document.getElementById("encrypted-status")!;
  const list = document.getElementById("encrypted-files")!;
  const all = document.getElementById(
    "encrypted-download-all"
  ) as HTMLButtonElement;
  const form = document.getElementById(
    "encrypted-key-form"
  ) as HTMLFormElement;
  const input = document.getElementById(
    "encrypted-key"
  ) as HTMLInputElement;

  const transfer = panel.dataset.transferId!;
  let files: FileRecord[] = [];
  let downloading = false;

  async function download(
    selected: FileRecord[],
    zip: boolean
  ): Promise<void> {
    if (downloading) return;

    downloading = true;
    status.textContent = "Preparing encrypted download…";

    try {
      const worker = (await prepareEncryptedDownloads()).active;

      if (!worker) {
        throw new Error(
          "Download support is unavailable. Refresh and retry."
        );
      }

      const entries = await Promise.all(selected.map(async file => ({
        ...file,
        key: await importKey(decode64(file.key), ["decrypt"])
      })));

      const token = Array.from(
        crypto.getRandomValues(new Uint8Array(24)),
        n => n.toString(16).padStart(2, "0")
      ).join("");

      const channel = new MessageChannel();
      let frame: HTMLIFrameElement | undefined;

      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => {
          channel.port1.close();
          reject(new Error("Download preparation timed out."));
        }, 10000);

        channel.port1.onmessage = event => {
          const data = event.data;

          if (data.ready) {
            clearTimeout(timer);
            resolve();
          }

          if (data.complete || data.error) {
            clearTimeout(timer);
            downloading = false;

            status.textContent = data.error ??
              "Decryption and verification finished. Check your browser downloads for the saved file.";

            channel.port1.close();
            frame?.remove();

            if (data.error) reject(new Error(data.error));
          }
        };

        worker.postMessage({
          type: "encrypted-download",
          transfer,
          files: entries,
          token,
          zip
        }, [channel.port2]);
      });

      // A navigation reaches the worker; a download attribute can bypass it.
      frame = document.createElement("iframe");
      frame.hidden = true;
      frame.src = "/e2ee-download/" + token;
      document.body.append(frame);

      status.textContent =
        "Decrypting and saving through your browser. Keep this page open; use your browser downloads to cancel.";
    } catch (error) {
      downloading = false;
      status.textContent = error instanceof Error
        ? error.message
        : "Could not start download.";
    }
  }

  async function unlock(key: string): Promise<void> {
    status.textContent = "Decrypting file names…";
    list.replaceChildren();
    all.disabled = true;

    try {
      if (decode64(key).length !== 32) {
        throw new Error("Invalid key.");
      }

      const response = await fetch(`/api/transfers/${transfer}`, {
        cache: "no-store",
        redirect: "error"
      });

      if (!response.ok) {
        throw new Error("Transfer unavailable or expired.");
      }

      const metadata = await response.json();

      if (
        metadata.id !== transfer ||
        metadata.encryption?.version !== 1 ||
        typeof metadata.encryption.manifest !== "string" ||
        !Array.isArray(metadata.files)
      ) {
        throw new Error("Invalid encrypted transfer.");
      }

      const secrets = await decryptManifest(
        metadata.encryption.manifest,
        key
      );

      if (metadata.files.length !== secrets.length) {
        throw new Error("File list does not match.");
      }

      const ids = new Set<string>();

      files = secrets.map(file => {
        const matching = metadata.files.filter(
          (row: { name?: string }) => row.name === file.opaque
        );
        const row = matching[0];

        if (
          matching.length !== 1 ||
          row.relative_path !== file.opaque ||
          row.size_bytes !== wireSize(file.size) ||
          typeof row.id !== "string" ||
          !/^[A-Za-z0-9_-]{32}$/.test(row.id) ||
          ids.has(row.id)
        ) {
          throw new Error("Encrypted file list does not match.");
        }

        ids.add(row.id);
        return { ...file, id: row.id };
      });

      for (const file of files) {
        const row = document.createElement("li");
        row.className =
          "list-group-item d-flex flex-wrap justify-content-between align-items-center gap-3";

        const name = document.createElement("span");
        name.className = "shared-file-name";
        name.textContent =
          `${file.path} · ${file.size.toLocaleString()} bytes`;

        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-outline-primary btn-sm";
        button.textContent = "Download";
        button.addEventListener(
          "click", () => void download([file], false)
        );

        row.append(name, button);
        list.append(row);
      }

      await prepareEncryptedDownloads();

      all.disabled = false;
      form.hidden = true;
      input.value = "";

      status.textContent =
        "End-to-end encrypted. File contents and names are decrypted in your browser. Keep the full share link safe.";
    } catch {
      files = [];
      list.replaceChildren();
      form.hidden = false;

      status.textContent =
        "Could not unlock this transfer. Check the full link or key, expiry, and browser support. Altered encrypted data cannot be decrypted.";
    }
  }

  all.addEventListener("click", () => void download(files, true));

  form.addEventListener("submit", event => {
    event.preventDefault();
    let key = input.value.trim();

    try {
      if (key.includes("#")) {
        key = new URLSearchParams(
          new URL(key).hash.slice(1)
        ).get("key") ?? "";
      }
    } catch {}

    void unlock(key);
  });

  const key = new URLSearchParams(location.hash.slice(1)).get("key");

  if (key) {
    await unlock(key);
  } else {
    status.textContent =
      "The decryption key is missing. Open the complete share link, including #key=…, or enter the key below. Filevoya cannot recover it.";
  }
}

const panel = document.getElementById("encrypted-transfer");
if (panel) void initialize(panel);