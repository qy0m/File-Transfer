export {};

type FolderWindow = Window & {
  showDirectoryPicker?: (options: {
    id: string;
    mode: "readwrite";
    startIn: "downloads";
  }) => Promise<FileSystemDirectoryHandle>;
};

type DownloadFile = {
  id: string;
  size: number;
  parts: string[];
};

const browser = window as FolderWindow;
const picker = browser.showDirectoryPicker?.bind(browser);
const idPattern = /^[A-Za-z0-9_-]{32}$/;

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parts(path: string): string[] {
  const result = path.split("/");

  if (
    !path ||
    new TextEncoder().encode(path).length > 1024 ||
    /[\\\x00-\x1f\x7f]/.test(path) ||
    /^[A-Za-z]:/.test(path) ||
    result.some(part => part === "" || part === "." || part === "..")
  ) {
    throw new Error("Invalid folder path.");
  }

  return result;
}

function errorName(error: unknown): string {
  return object(error) && typeof error.name === "string"
    ? error.name
    : "";
}

async function newFolder(
  parent: FileSystemDirectoryHandle,
  name: string
): Promise<FileSystemDirectoryHandle> {
  for (let attempt = 1; attempt <= 1000; attempt++) {
    const candidate = attempt === 1
      ? name
      : `${name} (${attempt})`;

    try {
      await parent.getDirectoryHandle(candidate);
    } catch (error) {
      if (errorName(error) === "NotFoundError") {
        return parent.getDirectoryHandle(candidate, { create: true });
      }

      if (errorName(error) !== "TypeMismatchError") throw error;
    }
  }

  throw new Error("Choose a different destination folder.");
}

function readFiles(
  data: unknown,
  transferId: string
): DownloadFile[] {
  if (
    !object(data) ||
    data.id !== transferId ||
    data.state !== "ready" ||
    !Array.isArray(data.files) ||
    data.files.length < 1 ||
    data.files.length > 25
  ) {
    throw new Error("Invalid transfer response.");
  }

  const seenIds = new Set<string>();
  const seenPaths = new Set<string>();

  const files = data.files.map((item: unknown): DownloadFile => {
    if (
      !object(item) ||
      typeof item.id !== "string" ||
      !idPattern.test(item.id) ||
      typeof item.name !== "string" ||
      typeof item.relative_path !== "string" ||
      typeof item.size_bytes !== "number" ||
      !Number.isSafeInteger(item.size_bytes) ||
      item.size_bytes < 0 ||
      item.size_bytes > 5_000_000_000
    ) {
      throw new Error("Invalid file response.");
    }

    const path = parts(item.relative_path);

    if (
      path[path.length - 1] !== item.name ||
      seenIds.has(item.id) ||
      seenPaths.has(item.relative_path)
    ) {
      throw new Error("Invalid file response.");
    }

    seenIds.add(item.id);
    seenPaths.add(item.relative_path);

    return {
      id: item.id,
      size: item.size_bytes,
      parts: path
    };
  });

  if (
    files.reduce((total, file) => total + file.size, 0) >
    5_000_000_000
  ) {
    throw new Error("Invalid transfer size.");
  }

  return files;
}

for (const button of Array.from(
  document.querySelectorAll<HTMLButtonElement>("[data-download-folder]")
)) {
  const group = button.closest("[data-folder-actions]");

  const status =
    group?.querySelector<HTMLElement>("[data-folder-status]");

  if (!status) continue;

  if (!picker || !window.isSecureContext) {
    button.disabled = true;

    status.textContent =
      "Direct folder saving is unavailable in this browser. " +
      "Use the ZIP option, or open this page in desktop Chrome or Edge.";

    continue;
  }

  const normalLabel =
    button.textContent?.trim() || "Standard download";

  let active: AbortController | null = null;

  button.addEventListener("click", async () => {
    if (active) {
      active.abort();
      return;
    }

    const controller = new AbortController();
    active = controller;

    let started = false;

    button.textContent = "Cancel";
    status.classList.remove("text-danger");

    try {
      const transferId = button.dataset.transferId ?? "";
      const downloadAll = button.dataset.downloadAll === "true";

      const folder = downloadAll
        ? []
        : parts(button.dataset.folder ?? "");

      if (!idPattern.test(transferId)) {
        throw new Error("Invalid transfer.");
      }

      status.textContent =
        "Choose where to save a new copy of this folder.";

      const destination = await picker({
        id: "transfer-serv-folder",
        mode: "readwrite",
        startIn: "downloads"
      });

      controller.signal.throwIfAborted();

      status.textContent = "Checking files…";

      const metadata = await fetch(`/api/transfers/${transferId}`, {
        cache: "no-store",
        signal: controller.signal
      });

      if (!metadata.ok) {
        throw new Error(
          `Transfer unavailable (${metadata.status}).`
        );
      }

      const availableFiles = readFiles(
        await metadata.json(),
        transferId
      );

      const files = downloadAll
        ? availableFiles
        : availableFiles.filter(file =>
            file.parts.length > folder.length &&
            folder.every(
                (part, index) => file.parts[index] === part
            )
        );

    if (!files.length) {
        throw new Error("Folder not found.");
    }

    let folderName = folder[folder.length - 1];
    let prefixLength = folder.length;

      if (downloadAll) {
        const firstRoot = files[0].parts[0];

        const sharedRoot = files.every(file =>
            file.parts.length > 1 &&
            file.parts[0] === firstRoot
        );

        folderName = sharedRoot
            ? firstRoot
            : `Transfer-${transferId.slice(0, 8)}`;

        prefixLength = sharedRoot ? 1 : 0;
      }

      controller.signal.throwIfAborted();

      const output = await newFolder(
        destination,
        folderName
      );

      started = true;

      for (const [index, file] of files.entries()) {
        controller.signal.throwIfAborted();

        const relative = file.parts.slice(prefixLength);
        let directory = output;

        for (const part of relative.slice(0, -1)) {
          directory = await directory.getDirectoryHandle(
            part,
            { create: true }
          );
        }

        const name = relative[relative.length - 1];

        try {
          await directory.getFileHandle(name);
          throw new Error("A destination filename already exists.");
        } catch (error) {
          if (errorName(error) !== "NotFoundError") throw error;
        }

        status.textContent =
          `Saving ${index + 1} of ${files.length}: ${relative.join("/")}`;

        const query = new URLSearchParams({
          transfer: transferId,
          file: file.id
        });

        const response = await fetch(`/download.php?${query}`, {
          cache: "no-store",
          signal: controller.signal
        });

        if (!response.ok || !response.body) {
          throw new Error(
            `File download failed (${response.status}).`
          );
        }

        const handle = await directory.getFileHandle(
          name,
          { create: true }
        );

        const writable = await handle.createWritable();
        let received = 0;

        const checked = new TransformStream<Uint8Array, Uint8Array>({
          transform(chunk, stream) {
            received += chunk.byteLength;

            if (received > file.size) {
              throw new Error("File size does not match.");
            }

            stream.enqueue(chunk);
          },

          flush() {
            if (received !== file.size) {
              throw new Error("File size does not match.");
            }
          }
        });

        await response.body
          .pipeThrough(checked)
          .pipeTo(writable, {
            signal: controller.signal
          });
      }

      status.textContent =
        `Saved ${files.length} file(s) in "${output.name}".`;

    } catch (error) {
      const message = errorName(error) === "AbortError"
        ? "Download cancelled."
        : error instanceof Error
          ? error.message
          : "Could not save the folder.";

      status.textContent = message + (
        started
          ? " A partial copy may remain in the destination."
          : ""
      );

      status.classList.add("text-danger");

    } finally {
      active = null;
      button.textContent = normalLabel;
    }
  });
}