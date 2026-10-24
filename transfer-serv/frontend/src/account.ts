export {};

type User = {
  id: string;
  username: string;
};

type SharedFile = {
  id: string;
  name: string;
  size_bytes: number;
  state: "pending" | "ready";
  received_bytes: number;
};

type Transfer = {
  id: string;
  expires_at: number;
  state: "pending" | "ready";
  files: SharedFile[];
};

type Dashboard = {
  transfers: Transfer[];
  page: number;
  total: number;
  has_more: boolean;
};

const ID = /^[A-Za-z0-9_-]{32}$/;

let user: User | null = null;
let page = 1;
let loading = false;
let deleting = false;

class AccountError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function element<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);

  if (!node) {
    throw new Error(`Missing account element: ${id}`);
  }

  return node as T;
}

function bytes(value: number): string {
  if (value < 1000) return `${value} B`;
  if (value < 1_000_000) return `${(value / 1000).toFixed(1)} KB`;
  if (value < 1_000_000_000) {
    return `${(value / 1_000_000).toFixed(1)} MB`;
  }

  return `${(value / 1_000_000_000).toFixed(2)} GB`;
}

async function request(
  path: string,
  body?: unknown,
  method: "GET" | "POST" | "DELETE" =
    body === undefined ? "GET" : "POST"
): Promise<unknown> {
  const response = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "transfer-serv"
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(30_000)
  });

  const result: unknown = await response.json();

  if (!response.ok) {
    let message = `Request failed (${response.status}).`;

    if (object(result) && typeof result.detail === "string") {
      message = result.detail;
    } else if (
      object(result) &&
      Array.isArray(result.detail) &&
      object(result.detail[0]) &&
      typeof result.detail[0].msg === "string"
    ) {
      message = result.detail[0].msg;
    }

    throw new AccountError(response.status, message);
  }

  return result;
}

function showSession(value: User | null): void {
  user = value;

  element("account-guest").hidden = value !== null;
  element("account-member").hidden = value === null;
  element("account-name").textContent = value?.username ?? "";
  element("account-status").hidden = true;
}

function validDashboard(value: unknown): value is Dashboard {
  return object(value) &&
    Number.isSafeInteger(value.page) &&
    Number.isSafeInteger(value.total) &&
    typeof value.has_more === "boolean" &&
    Array.isArray(value.transfers) &&
    value.transfers.every(transfer =>
      object(transfer) &&
      typeof transfer.id === "string" &&
      ID.test(transfer.id) &&
      typeof transfer.expires_at === "number" &&
      Number.isSafeInteger(transfer.expires_at) &&
      (
        transfer.state === "pending" ||
        transfer.state === "ready"
      ) &&
      Array.isArray(transfer.files) &&
      transfer.files.every(file =>
        object(file) &&
        typeof file.id === "string" &&
        ID.test(file.id) &&
        typeof file.name === "string" &&
        typeof file.size_bytes === "number" &&
        Number.isSafeInteger(file.size_bytes) &&
        file.size_bytes >= 0 &&
        typeof file.received_bytes === "number" &&
        Number.isSafeInteger(file.received_bytes) &&
        file.received_bytes >= 0 &&
        file.received_bytes <= file.size_bytes &&
        (file.state === "pending" || file.state === "ready")
      )
    );
}

function link(text: string, href: string): HTMLAnchorElement {
  const node = document.createElement("a");

  node.textContent = text;
  node.href = href;
  node.className = "btn btn-outline-primary btn-sm";

  return node;
}

function renderDashboard(data: Dashboard): void {
  const list = element("dashboard-list");
  list.replaceChildren();

  element("dashboard-empty").hidden = data.total !== 0;

  element("dashboard-summary").textContent =
    `Page ${data.page} · ${data.total} current transfer(s)`;

  element<HTMLButtonElement>("dashboard-prev").disabled =
    data.page <= 1;

  element<HTMLButtonElement>("dashboard-next").disabled =
    !data.has_more;

  for (const transfer of data.transfers) {
    const card = document.createElement("section");
    card.className = "card mb-3";

    const body = document.createElement("div");
    body.className = "card-body";

    const heading = document.createElement("h2");
    heading.className = "h5";
    heading.textContent = `${transfer.files.length} file(s)`;

    const information = document.createElement("p");
    information.className = "small text-secondary";

    information.textContent =
      `${transfer.state === "ready" ? "Ready to share" : "Upload incomplete"} · Expires ` +
      new Date(transfer.expires_at * 1000).toLocaleString();

    const files = document.createElement("ul");
    files.className = "list-group list-group-flush";

    for (const file of transfer.files) {
      const row = document.createElement("li");
      row.className =
        "list-group-item d-flex flex-wrap gap-3 align-items-center";

      const description = document.createElement("div");
      description.className = "flex-grow-1 shared-file-name";

      const name = document.createElement("strong");
      name.textContent = file.name;

      const size = document.createElement("div");
      size.className = "small text-secondary";

      size.textContent = file.state === "ready"
        ? bytes(file.size_bytes)
        : `${bytes(file.received_bytes)} of ${bytes(file.size_bytes)} uploaded`;

      description.append(name, size);
      row.append(description);

      if (
        transfer.state === "ready" &&
        file.state === "ready"
      ) {
        const query = new URLSearchParams({
          transfer: transfer.id,
          file: file.id
        });

        const download = link(
          "Download",
          `/download.php?${query}`
        );

        download.setAttribute(
          "aria-label",
          `Download ${file.name}`
        );

        row.append(download);
      }

      files.append(row);
    }

    body.append(heading, information, files);

    if (transfer.state === "ready") {
      const actions = document.createElement("div");
      actions.className = "d-flex flex-wrap gap-2 mt-3";

      const path = `/transfer.php?id=${transfer.id}`;

      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "btn btn-primary btn-sm";
      copy.textContent = "Copy share link";

      const copyStatus = document.createElement("p");
      copyStatus.className = "small mt-2 mb-0";
      copyStatus.setAttribute("role", "status");

      copy.addEventListener("click", async () => {
        const url = new URL(
          path,
          window.location.origin
        ).href;

        try {
          await navigator.clipboard.writeText(url);
          copyStatus.textContent = "Link copied.";
        } catch {
          const field = document.createElement("input");
          field.type = "text";
          field.readOnly = true;
          field.className = "form-control";
          field.value = url;
          field.setAttribute("aria-label", "Share link to copy");

          copyStatus.replaceChildren(field);
          field.focus();
          field.select();
        }
      });

      actions.append(
        link("Open share page", path),
        copy
      );

      body.append(actions, copyStatus);
    }

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className =
      "btn btn-outline-primary btn-sm mt-3";
    remove.textContent = "Delete transfer";

    const deleteStatus = document.createElement("p");
    deleteStatus.className =
      "small text-danger mt-2 mb-0";
    deleteStatus.setAttribute("role", "status");

    remove.addEventListener("click", async () => {
      if (loading || deleting) return;

      if (!window.confirm(
        `Delete this transfer and all ${transfer.files.length} file(s)?\n\n` +
        "The share link will stop working and any active upload will stop. " +
        "This cannot be undone."
      )) {
        return;
      }

      deleting = true;
      remove.disabled = true;
      deleteStatus.textContent = "";

      try {
        const result = await request(
          `/account/transfers/${transfer.id}`,
          undefined,
          "DELETE"
        );

        if (
          !object(result) ||
          result.ok !== true ||
          typeof result.storage_deleted !== "boolean"
        ) {
          throw new Error("Invalid deletion response.");
        }

        card.remove();

        window.dispatchEvent(new Event("storage-changed"));
        deleting = false;

        await loadDashboard(page);

        const status = element("dashboard-status");

        const message = result.storage_deleted
          ? "Transfer and files deleted."
          : "Transfer disabled. File deletion is queued.";

        status.textContent =
          status.classList.contains("text-danger")
            ? message + " " + status.textContent
            : message;
      } catch (error) {
        if (
          error instanceof AccountError &&
          error.status === 401
        ) {
          showSession(null);
          window.location.replace("/login.php");
          return;
        }

        deleteStatus.textContent = error instanceof Error
          ? error.message
          : "Could not delete the transfer.";

      } finally {
        deleting = false;
        remove.disabled = false;
      }
    });

    body.append(remove, deleteStatus);

    card.append(body);
    list.append(card);
  }
}

async function loadDashboard(target: number): Promise<void> {
  if (loading || deleting) return;
  loading = true;

  const status = element("dashboard-status");

  const controls = [
    "dashboard-prev",
    "dashboard-next",
    "dashboard-refresh"
  ];

  controls.forEach(id => {
    element<HTMLButtonElement>(id).disabled = true;
  });

  status.textContent = "Loading your files…";
  status.classList.remove("text-danger");

  try {
    let result = await request(
      `/account/transfers?page=${target}`
    );

    if (!validDashboard(result)) {
      throw new Error("Invalid dashboard response.");
    }

    if (
      result.transfers.length === 0 &&
      result.total > 0 &&
      target > 1
    ) {
      result = await request("/account/transfers?page=1");

      if (!validDashboard(result)) {
        throw new Error("Invalid dashboard response.");
      }
    }

    page = result.page;
    renderDashboard(result);
    status.textContent = "";
  } catch (error) {
    if (
      error instanceof AccountError &&
      error.status === 401
    ) {
      element("dashboard-list").replaceChildren();
      showSession(null);
      window.location.replace("/login.php");
      return;
    }

    status.textContent = error instanceof Error
      ? error.message
      : "Could not load files.";

    status.classList.add("text-danger");

    element<HTMLButtonElement>("dashboard-prev").disabled =
      page <= 1;

    element<HTMLButtonElement>("dashboard-next").disabled =
      true;
  } finally {
    loading = false;

    element<HTMLButtonElement>("dashboard-refresh").disabled =
      false;
  }
}

const form = document.getElementById(
  "account-form"
) as HTMLFormElement | null;

const dashboard = document.getElementById("dashboard-list");

const settings = document.getElementById(
  "settings-form"
) as HTMLFormElement | null;

async function loadSession(): Promise<void> {
  try {
    let current: User | null = null;

    try {
      const result = await request("/auth/me");

      if (
        !object(result) ||
        !object(result.user) ||
        typeof result.user.id !== "string" ||
        !ID.test(result.user.id) ||
        typeof result.user.username !== "string"
      ) {
        throw new Error("Invalid account response.");
      }

      current = {
        id: result.user.id,
        username: result.user.username
      };
    } catch (error) {
      if (
        !(error instanceof AccountError && error.status === 401)
      ) {
        throw error;
      }
    }

    showSession(current);

    if (dashboard || settings) {
      if (!current) {
        window.location.replace("/login.php");
        return;
      }

      if (settings) {
        element<HTMLInputElement>("settings-username").value =
          current.username;

        element<HTMLButtonElement>("settings-submit").disabled =
          false;

        element("settings-status").textContent = "";
      }

      if (dashboard) {
        await loadDashboard(page);
      }

    } else if (form && current) {
      window.location.replace("/dashboard.php");
      return;
    }
  } catch {
    const status = element("account-status");
    status.hidden = false;
    status.textContent = "Account service unavailable.";

    if (settings) {
      element("settings-status").textContent =
        "Could not load your account. Refresh this page to retry.";
    }

    if (dashboard) {
      element("dashboard-status").textContent =
        "Could not check your account. Click Refresh to retry.";
    }
  } finally {
    if (form) {
      element<HTMLButtonElement>("account-submit").disabled =
        false;
    }
  }
}

if (form) {
  form.addEventListener("submit", async event => {
    event.preventDefault();

    const status = element("account-form-status");
    const submit = element<HTMLButtonElement>("account-submit");

    if (submit.disabled) return;

    const username =
      element<HTMLInputElement>("account-username");

    const password =
      element<HTMLInputElement>("account-password");

    const confirm = document.getElementById(
      "account-confirm"
    ) as HTMLInputElement | null;

    status.classList.remove("text-danger");

    if (confirm && confirm.value !== password.value) {
      status.textContent = "Passwords do not match.";
      status.classList.add("text-danger");
      return;
    }

    submit.disabled = true;
    status.textContent = "Please wait…";

    try {
      await request(
        form.dataset.mode === "register"
          ? "/auth/register"
          : "/auth/login",
        {
          username: username.value,
          password: password.value
        }
      );

      password.value = "";
      if (confirm) confirm.value = "";

      window.location.assign("/dashboard.php");
    } catch (error) {
      status.textContent = error instanceof Error
        ? error.message
        : "Could not sign in.";

      status.classList.add("text-danger");
    } finally {
      submit.disabled = false;
    }
  });
}

element<HTMLButtonElement>("account-logout").addEventListener(
  "click",
  async () => {
    const button =
      element<HTMLButtonElement>("account-logout");

    button.disabled = true;

    try {
      await request("/auth/logout", {});
      showSession(null);
      window.location.assign("/login.php");
    } catch (error) {
      const status = element("account-status");
      status.hidden = false;

      status.textContent = error instanceof Error
        ? error.message
        : "Could not sign out.";
    } finally {
      button.disabled = false;
    }
  }
);

if (dashboard) {
  element("dashboard-prev").addEventListener(
    "click",
    () => void loadDashboard(page - 1)
  );

  element("dashboard-next").addEventListener(
    "click",
    () => void loadDashboard(page + 1)
  );

  element("dashboard-refresh").addEventListener(
    "click",
    () => void loadSession()
  );

  window.setInterval(() => {
    if (!document.hidden && user && !loading && !deleting) {
      void loadDashboard(page);
    }
  }, 60_000);
}

window.addEventListener("pageshow", event => {
  if (event.persisted) window.location.reload();
});

if (settings) {
  settings.addEventListener("submit", async event => {
    event.preventDefault();

    const button =
      element<HTMLButtonElement>("settings-submit");
    
    if (button.disabled) return;

    const current = element<HTMLInputElement>(
      "settings-current-password"
    );

    const password = element<HTMLInputElement>(
      "settings-new-password"
    );

    const confirm = element<HTMLInputElement>(
      "settings-confirm-password"
    );

    const status = element<HTMLElement>("settings-status");

    status.classList.remove("text-danger");

    if (password.value !== confirm.value) {
      status.textContent = "New passwords do not match.";
      status.classList.add("text-danger");
      return;
    }

    button.disabled = true;
    status.textContent = "Updating password...";

    try {
      await request("/account/password", {
        current_password: current.value,
        new_password: password.value
      });

      settings.reset();
      showSession(null);

      window.location.assign(
        "/login.php?password_changed=1"
      );

    } catch (error) {
      if (
        error instanceof AccountError &&
        error.status === 401
      ) {
        settings.reset();
        showSession(null);
        window.location.replace("/login.php");
        return;
      }

      status.textContent = error instanceof Error
        ? error.message
        : "Could not update password.";

      status.classList.add("text-danger");

    } finally {
      button.disabled = false;
    }
  });
}

if (
  form &&
  form.dataset.mode === "login" &&
  new URLSearchParams(
    window.location.search
  ).get("password_changed") === "1"
) {
  element("account-form-status").textContent =
    "Password updated. Sign in with your new password.";
}

void loadSession();