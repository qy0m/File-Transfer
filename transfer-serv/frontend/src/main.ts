import { collectDroppedFiles } from "./file-drop.js";

const MAX_FILES = 25;
const MAX_BYTES = 5_000_000_000;
const CHUNK_BYTES = 8 * 1024 * 1024;
const ID_PATTERN = /^[A-Za-z0-9_-]{32}$/;

type UploadFile = {
  id: string;
  name: string;
  size_bytes: number;
  received_bytes: number;
  state: "pending" | "ready";
};

type UploadSession = {
  id: string;
  token: string;
  files: UploadFile[];
};

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function isObject(
  value: unknown
): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function formatBytes(bytes: number): string {
  if (bytes < 1000) {
    return `${bytes} B`;
  }

  if (bytes < 1_000_000) {
    return `${(bytes / 1000).toFixed(1)} KB`;
  }

  if (bytes < 1_000_000_000) {
    return `${(bytes / 1_000_000).toFixed(1)} MB`;
  }

  return `${(bytes / 1_000_000_000).toFixed(2)} GB`;
}

function errorDetail(
  body: unknown,
  status: number
): string {
  if (isObject(body)) {
    if (typeof body.detail === "string") {
      return body.detail;
    }

    if (
      isObject(body.detail) &&
      typeof body.detail.error === "string"
    ) {
      return body.detail.error;
    }
  }

  return `Request failed (${status}).`;
}

async function api(
  path: string,
  options: RequestInit = {},
  timeoutMs = 30_000
): Promise<unknown> {
  const headers = new Headers(options.headers);
  headers.set("X-Requested-With", "transfer-serv");

  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
    cache: "no-store",
    signal: AbortSignal.timeout(timeoutMs)
  });


  const body: unknown = await response.json();

  if (!response.ok) {
    throw new ApiError(
      response.status,
      errorDetail(body, response.status)
    );
  }

  return body;
}

const droppedPaths = new WeakMap<File, string>();

function uploadPath(file: File): string {
  return droppedPaths.get(file) ||
    file.webkitRelativePath ||
    file.name;
}

async function createSession(
  files: File[]
): Promise<UploadSession> {
  const body = await api("/transfers", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      files: files.map(file => ({
        name: file.name,
        relative_path: uploadPath(file),
        size_bytes: file.size
      }))
    })
  });

  if (
    !isObject(body) ||
    typeof body.id !== "string" ||
    !ID_PATTERN.test(body.id) ||
    typeof body.upload_token !== "string" ||
    !/^[A-Za-z0-9_-]{43}$/.test(body.upload_token) ||
    !Array.isArray(body.files) ||
    body.files.length !== files.length
  ) {
    throw new Error("Invalid transfer response.");
  }

  const returned: unknown[] = body.files;

  const records = returned.map(
    (value, index): UploadFile => {
      if (
        !isObject(value) ||
        typeof value.id !== "string" ||
        !ID_PATTERN.test(value.id) ||
        value.name !== files[index].name ||
        value.relative_path !== uploadPath(files[index]) ||
        value.size_bytes !== files[index].size
      ) {
        throw new Error("Invalid file response.");
      }

      return {
        id: value.id,
        name: files[index].name,
        size_bytes: files[index].size,
        received_bytes: 0,
        state: "pending"
      };
    }
  );

  if (
    new Set(records.map(file => file.id)).size !== files.length
  ) {
    throw new Error("Duplicate file IDs in transfer response.");
  }

  return {
    id: body.id,
    token: body.upload_token,
    files: records
  };
}

async function synchronize(
  session: UploadSession
): Promise<string> {
  const body = await api(
    `/transfers/${session.id}/upload-status`,
    {
      headers: {
        "X-Upload-Token": session.token
      }
    }
  );

  if (
    !isObject(body) ||
    body.id !== session.id ||
    (body.state !== "pending" && body.state !== "ready") ||
    !Array.isArray(body.files) ||
    body.files.length !== session.files.length
  ) {
    throw new Error("Invalid upload status.");
  }

  const rows: unknown[] = body.files;

  const updates = session.files.map(file => {
    const matches = rows.filter(
      row => isObject(row) && row.id === file.id
    );

    const row = matches[0];

    if (
      matches.length !== 1 ||
      !isObject(row) ||
      row.name !== file.name ||
      row.size_bytes !== file.size_bytes ||
      typeof row.received_bytes !== "number" ||
      !Number.isSafeInteger(row.received_bytes) ||
      row.received_bytes < 0 ||
      row.received_bytes > file.size_bytes ||
      (row.state !== "pending" && row.state !== "ready") ||
      (
        row.state === "ready" &&
        row.received_bytes !== file.size_bytes
      )
    ) {
      throw new Error("Invalid file upload status.");
    }

    return {
      received: row.received_bytes,
      state: row.state as "pending" | "ready"
    };
  });

  updates.forEach((update, index) => {
    session.files[index].received_bytes = update.received;
    session.files[index].state = update.state;
  });

  return body.state;
}

function isComplete(file: UploadFile): boolean {
  return file.state === "ready";
}

function element<T extends HTMLElement>(id: string): T {
  const result = document.getElementById(id);

  if (!result) {
    throw new Error(`Missing page element: ${id}`);
  }

  return result as T;
}

function initializeUploader(): void {
  const input = element<HTMLInputElement>("files");
  const dropZone = element<HTMLElement>("drop-zone");
  const overlay = element<HTMLElement>("drop-overlay");

  const review =
    element<HTMLDialogElement>("drop-confirmation");
  const reviewSummary =
    element<HTMLElement>("drop-summary");
  const reviewList =
    element<HTMLUListElement>("drop-file-list");
  const reviewCancel =
    element<HTMLButtonElement>("drop-cancel");
  const reviewUpload =
    element<HTMLButtonElement>("drop-upload");
  const pickerButton =
    element<HTMLButtonElement>("upload-picker");
  const filesButton =
    element<HTMLButtonElement>("browse-files");
  filesButton.addEventListener("click", () => {
    if (!filesButton.disabled) input.click();
  });
  const folderInput = element<HTMLInputElement>("folder-files");
  const folderButton = element<HTMLButtonElement>("browse-folder");
  const supportsFolders = "webkitdirectory" in folderInput;
  folderButton.disabled = !supportsFolders;
  if (!supportsFolders) {
    folderButton.title =
      "Folder selection is unavailable in this browser.";
  }
  folderButton.addEventListener("click", () => {
    if (!folderButton.disabled) folderInput.click();
  });
  const selection = element<HTMLElement>("selection-status");
  const list = element<HTMLUListElement>("file-list");
  const button = element<HTMLButtonElement>("upload-button");
  const progress = element<HTMLProgressElement>("upload-progress");
  const details = element<HTMLElement>("progress-details");
  const status = element<HTMLElement>("upload-status");
  const shareResult = element<HTMLElement>("share-result");
  const shareLink = element<HTMLInputElement>("share-link");
  const openLink = element<HTMLAnchorElement>("open-transfer");
  const copyButton = element<HTMLButtonElement>("copy-link");
  const copyStatus = element<HTMLElement>("copy-status");

  let selected: File[] = [];
  let session: UploadSession | null = null;
  let busy = false;
  let readingDrop = false;
  let done = false;

  function validSelection(): boolean {
    return selected.length > 0 &&
      selected.length <= MAX_FILES &&
      selected.reduce(
        (total, file) => total + file.size, 0
      ) <= MAX_BYTES;
  }

  function updateButton(): void {
    const locked = busy || readingDrop;

    button.disabled = locked || done || !validSelection();
    pickerButton.disabled = locked;
    filesButton.disabled = locked;
    input.disabled = locked;
    folderInput.disabled = locked;
    folderButton.disabled = locked || !supportsFolders;
    dropZone.setAttribute("aria-disabled", String(locked));

    dropZone.setAttribute(
      "aria-busy",
      String(readingDrop)
    );

    button.textContent = busy
      ? "Uploading..."
      : done
        ? "Upload complete"
        : session
          ? "Resume upload"
          : "Upload files";
  }

  function message(
    text: string,
    failed = false
  ): void {
    status.textContent = text;
    status.classList.toggle("text-danger", failed);
    status.classList.toggle("text-secondary", !failed);
  }

  function render(): void {
    const total = selected.reduce(
      (bytes, file) => bytes + file.size, 0
    );

    const confirmed = session?.files.reduce(
      (bytes, file) => bytes + file.received_bytes, 0
    ) ?? 0;

    const sent = Math.min(total, confirmed);

    const percent = done
      ? 100
      : total
        ? sent / total * 100
        : 0;

    progress.value = percent;

    details.textContent =
      `${Math.floor(percent)}% · ${formatBytes(sent)} of ${formatBytes(total)}`;

    list.replaceChildren();

    selected.slice(0, MAX_FILES).forEach((file, index) => {
      const item = document.createElement("li");
      const record = session?.files[index];

      item.className = "list-group-item px-0 small";

      const state = record
        ? record.state === "ready"
          ? " · Complete"
          : ` · ${formatBytes(record.received_bytes)} confirmed`
        : "";

      item.textContent =
        `${uploadPath(file)} · ${formatBytes(file.size)}${state}`;

      list.append(item);
    });
  }


  function setSelection(files: File[]): void {
    selected = files;
    session = null;
    done = false;

    shareResult.hidden = true;
    shareLink.value = "";
    openLink.removeAttribute("href");
    copyStatus.textContent = "";

    const total = selected.reduce(
      (bytes, file) => bytes + file.size,
      0
    );

    let text = selected.length
      ? `${selected.length} file(s) selected · ${formatBytes(total)}`
      : "No files selected.";

    if (selected.length > MAX_FILES) {
      text = "Choose no more than 25 files.";
    } else if (total > MAX_BYTES) {
      text = "The combined size must be 5 GB or less.";
    }

    selection.textContent = text;

    selection.classList.toggle(
      "text-danger",
      selected.length > 0 && !validSelection()
    );

    message("");
    render();
    updateButton();
  }

  function chooseFiles(source: HTMLInputElement): void {
    if (busy || readingDrop || !source.files?.length) return;

    const files = Array.from(source.files);

    if (source === folderInput) input.value = "";
    folderInput.value = "";

    setSelection(files);
  }

  input.addEventListener(
    "change",
    () => chooseFiles(input)
  );

  folderInput.addEventListener(
    "change",
    () => chooseFiles(folderInput)
  );

  function confirmDrop(files: File[]): Promise<boolean> {
    const total = files.reduce(
      (bytes, file) => bytes + file.size,
      0
    );

    reviewSummary.textContent =
      `${files.length} file(s) · ${formatBytes(total)}`;

    reviewList.replaceChildren();

    for (const file of files) {
      const item = document.createElement("li");

      item.textContent =
        `${uploadPath(file)} · ${formatBytes(file.size)}`;

      reviewList.append(item);
    }

    return new Promise(resolve => {
      let approved = false;

      const cancel = () => {
        review.close();
      };

      const accept = () => {
        approved = true;
        review.close();
      };

      const finish = () => {
        reviewCancel.removeEventListener("click", cancel);
        reviewUpload.removeEventListener("click", accept);
        resolve(approved);
      };

      reviewCancel.addEventListener("click", cancel);
      reviewUpload.addEventListener("click", accept);

      review.addEventListener(
        "close",
        finish,
        { once: true }
      );

      review.showModal();
    });
  }

  function fileDrag(event: DragEvent): boolean {
    return Array.from(
      event.dataTransfer?.types ?? []
    ).includes("Files");
  }

  let dragDepth = 0;

  function resetDrag(): void {
    dragDepth = 0;
    overlay.hidden = true;
  }

  document.addEventListener("dragenter", event => {
    if (!fileDrag(event)) return;

    event.preventDefault();
    dragDepth++;

    if (!busy && !readingDrop) {
      overlay.hidden = false;
    }
  });

  document.addEventListener("dragleave", () => {
    dragDepth = Math.max(0, dragDepth - 1);

    if (!dragDepth) {
      overlay.hidden = true;
    }
  });

  document.addEventListener("dragover", event => {
    if (!fileDrag(event)) return;

    event.preventDefault();

    const inside =
      event.target instanceof Node &&
      dropZone.contains(event.target);

    if (event.dataTransfer) {
      event.dataTransfer.dropEffect =
        inside && !busy && !readingDrop
          ? "copy"
          : "none";
    }
  });

  document.addEventListener("drop", async event => {
    if (!fileDrag(event)) return;

    event.preventDefault();
    resetDrag();

    if (
      busy ||
      readingDrop ||
      !event.dataTransfer ||
      !(event.target instanceof Node) ||
      !dropZone.contains(event.target)
    ) {
      return;
    }

    readingDrop = true;
    updateButton();
    message("Reading dropped files and folders.");

    let startUpload = false;

    try {
      const dropped = await collectDroppedFiles(
        event.dataTransfer
      );

      for (const item of dropped) {
        droppedPaths.set(item.file, item.path);
      }

      const files = dropped.map(item => item.file);

      if (!files.length || files.length > MAX_FILES) {
        throw new Error("Choose between 1 and 25 files.");
      }

      const total = files.reduce(
        (bytes, file) => bytes + file.size,
        0
      );

      if (total > MAX_BYTES) {
        throw new Error(
          "The combined size must be 5 GB or less."
        );
      }

      message("");

      if (await confirmDrop(files)) {
        input.value = "";
        folderInput.value = "";

        setSelection(files);
        startUpload = true;
      } else {
        message(
          "Drop canceled. Your previous selection is unchanged."
        );
      }
    } catch (error) {
      message(
        error instanceof Error
          ? error.message
          : "Could not read the drop.",
        true
      );
    } finally {
      readingDrop = false;
      updateButton();
    }

    if (startUpload) {
      void upload();
    }
  });

  document.addEventListener("dragend", resetDrag);
  window.addEventListener("blur", resetDrag);

  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      resetDrag();
    }
  });

  async function upload(): Promise<void> {
    if (busy || readingDrop || done || !validSelection()) {
      return;
    }

    busy = true;
    input.disabled = true;
    updateButton();

    try {
      if (!session) {
        message("Creating your transfer…");
        session = await createSession(selected);
      }

      const active = session;

      await synchronize(active);
      render();

      for (let index = 0; index < selected.length; index++) {
        const local = selected[index];
        const record = active.files[index];

        while (!isComplete(record)) {
          const offset = record.received_bytes;

          const data = local.slice(
            offset,
            Math.min(offset + CHUNK_BYTES, local.size)
          );

          message(
            `Uploading ${index + 1} of ${selected.length}: ${uploadPath(local)}`
          );

          const reply = await api(
            `/transfers/${active.id}/files/${record.id}/chunks?offset=${offset}`,
            {
              method: "PUT",
              headers: {
                "X-Upload-Token": active.token,
                "Content-Type": "application/octet-stream"
              },
              body: data
            },
            120_000
          );

          if (
            !isObject(reply) ||
            reply.file_id !== record.id ||
            reply.received_bytes !== offset + data.size ||
            reply.file_state !== (
              offset + data.size === local.size
                ? "ready"
                : "pending"
            )
          ) {
            throw new Error("Invalid chunk confirmation.");
          }

          record.received_bytes = offset + data.size;
          record.state = reply.file_state as "pending" | "ready";

          render();
        }
      }

      const finalState = await synchronize(active);

      if (
        finalState !== "ready" ||
        active.files.some(file => file.state !== "ready")
      ) {
        throw new Error("The transfer is not complete yet.");
      }

      const url = new URL(
        "/transfer.php",
        window.location.origin
      );

      url.searchParams.set("id", active.id);

      shareLink.value = url.href;
      openLink.href = url.href;
      shareResult.hidden = false;

      done = true;
      render();

      message("Upload complete. Share the link below.")

    } catch (error) {
      if (
        error instanceof ApiError &&
        (error.status === 401 || error.status === 410)
      ) {
        session = null;
      }

      render();

      const reason = error instanceof Error
        ? error.message
        : "Upload failed.";

      const recovery = session
        ? " Keep this page open and click Resume upload to retry."
        : " Click Upload files to retry.";

      message(reason + recovery, true);
    } finally {
      busy = false;
      input.disabled = false;
      updateButton();
    }
  }

  button.addEventListener("click", () => {
    void upload();
  });

  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(shareLink.value);
      copyStatus.textContent = "Link copied.";
    } catch {
      shareLink.focus();
      shareLink.select();

      copyStatus.textContent =
        "Link selected. Copy it with Ctrl+C.";
    }
  });

  render();
  updateButton();
}

async function checkHealth(): Promise<void> {
  const status = document.getElementById("service-status");

  if (!status) {
    return;
  }

  try {
    const health = await api("/health");

    if (!isObject(health) || health.ok !== true) {
      throw new Error("Service unavailable");
    }

    status.textContent =
      "Service connected · Gateway, API, and database are ready.";
  } catch {
    status.textContent =
      "Service unavailable. Check the API and gateway terminals.";

    status.classList.add("text-danger");
  }
}

if (document.getElementById("files")) {
  initializeUploader();
}

void checkHealth();
