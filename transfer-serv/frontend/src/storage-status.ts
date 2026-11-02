export {};

const panel = document.getElementById("storage-panel");

let busy = false;
let queued = false;

function element<T extends HTMLElement>(id: string): T {
    const node = document.getElementById(id);

    if (!node) {
        throw new Error(`Missing storage element: ${id}`);
    }

    return node as T;
}

function size(value: number): string {
  if (value < 1000) return `${value} B`;

  if (value < 1_000_000) {
    return `${(value / 1000).toFixed(1)} KB`;
  }

  if (value < 1_000_000_000) {
    return `${(value / 1_000_000).toFixed(1)} MB`;
  }

  return `${(value / 1_000_000_000).toFixed(2)} GB`;
}

async function refreshStorage(): Promise<void> {
    if (!panel) return;

    if (busy) {
        queued = true;
        return;
    }

    busy = true;

    try {
        let guest = false;
        
        let response = await fetch("/api/account/storage", {
          credentials: "same-origin",
          cache: "no-store",
          headers: { Accept: "application/json" },
          signal: AbortSignal.timeout(15_000)
        });

        if (
          response.status === 401 &&
          document.getElementById("storage-page")
        ) {
          guest = true;

          response = await fetch("/api/guest/storage", {
            credentials: "same-origin",
            cache: "no-store",
            headers: { Accept: "application/json" },
            signal: AbortSignal.timeout(15_000)
          });
        }

        if (response.status === 401) {
            panel.hidden = true;
            return;
        }

        if (!response.ok) {
            throw new Error("Storage request failed.");
        }

        const result: unknown = await response.json();

        if (typeof result !== "object" || result === null) {
            throw new Error("Invalid storage response.");
        }

        const data = result as Record<string, unknown>;

        if (guest) {
          data.account_reserved_bytes = data.reserved_bytes;
        }

        const exempt =
          !guest && data.quota_exempt === true;

        if (
          exempt
            ? data.budget_bytes !== null
            : (
              typeof data.budget_bytes !== "number" ||
              !Number.isSafeInteger(data.budget_bytes) ||
              data.budget_bytes <= 0
            )
        ) {
          throw new Error("Invalid storage response.");
        }

        const keys = [
            "reserved_bytes",
            "available_bytes",
            "account_reserved_bytes"
        ];

        for (const key of keys) {
            if (
                typeof data[key] !== "number" ||
                !Number.isSafeInteger(data[key]) ||
                data[key] < 0
            ) {
                throw new Error("Invalid storage response.");
            }
        }

        const budget = data.budget_bytes as number;
        const reserved = data.reserved_bytes as number;
        const available = data.available_bytes as number;
    const account = data.account_reserved_bytes as number;

    if (!exempt && available > budget) {
      throw new Error("Invalid storage response.");
    }

    element("storage-available").textContent = size(available);
    element("storage-account").textContent = size(account);
    element("storage-budget").textContent =
      exempt ? "No account quota" : size(budget);

    element("storage-allowance").textContent = exempt
      ? "Administrator · free disk space and pending reservations still apply."
      : "Your upload storage allowance is 5 GB.";

    element("storage-budget-label").textContent = exempt
      ? `Your storage used or reserved: ${size(reserved)}`
      : `Your storage used: ${size(reserved)} of ${size(budget)}`;

    const progress =
      element<HTMLProgressElement>("storage-progress");

    progress.hidden = false;

    progress.value = exempt
      ? 0
      : Math.min(100, reserved / budget * 100);

    let note = exempt
      ? "Storage remaining is disk capacity after the safety reserve and pending uploads."
      : "Pending uploads reserve their full declared size.";
      

    if (data.reason === "transfer_limit") {
      note =
        "The service has reached its transfer limit. " +
        "Try again after transfers are removed.";
    } else if (data.reason === "budget") {
      note =
        "Your 5 GB storage allowance is full. " +
        "Delete uploads to restore space.";
    } else if (data.reason === "disk_space") {
      note =
        "Available capacity is also limited by free disk space " +
        "and pending uploads.";
    } else if (data.reason === "unavailable") {
      note = "Upload storage is temporarily unavailable.";
    }

    element("storage-note").textContent = note;
    element("storage-note").classList.remove("text-danger");

    const context = document.getElementById("storage-context");

    if (context) {
      context.textContent = guest
        ? "Guest storage · 5 GB for this browser."
        : "Account storage · 5 GB across your uploads.";
    }

    panel.hidden = false;

  } catch {
    panel.hidden = false;

    for (const id of [
      "storage-available",
      "storage-account",
      "storage-budget"
    ]) {
      element(id).textContent = "—";
    }

    element("storage-budget-label").textContent = "";
    element("storage-progress").hidden = true;

    element("storage-note").textContent =
      "Storage information is unavailable. Click Refresh to retry.";

    element("storage-note").classList.add("text-danger");

  } finally {
    busy = false;

    if (queued) {
      queued = false;
      void refreshStorage();
    }
  }
}

if (panel) {
  document.getElementById("dashboard-refresh")?.addEventListener(
    "click",
    () => void refreshStorage()
  );

  window.addEventListener(
    "storage-changed",
    () => void refreshStorage()
  );

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) void refreshStorage();
  });

  window.setInterval(() => {
    if (!document.hidden) void refreshStorage();
  }, 60_000);

  void refreshStorage();
}