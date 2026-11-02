const reportForm = document.getElementById(
  "abuse-form"
) as HTMLFormElement | null;

function reportTransferId(value: string): string {
  value = value.trim();

  if (
    value.length === 32 &&
    /^[A-Za-z0-9_-]{32}$/.test(value)
  ) return value;

  const url = new URL(value);

  if (
    url.protocol !== "https:" ||
    ![location.origin, "https://www.filevoya.site"].includes(url.origin) ||
    url.pathname !== "/transfer.php" ||
    url.searchParams.getAll("id").length !== 1
  ) {
    throw new Error("Enter a Filevoya share link or its transfer ID.");
  }

  const id = url.searchParams.get("id") ?? "";

  if (
    id.length !== 32 ||
    !/^[A-Za-z0-9_-]{32}$/.test(id)
  ) {
    throw new Error("Enter a valid transfer ID.");
  }

  return id;
}

if (reportForm) {
  const input = document.getElementById(
    "abuse-transfer"
  ) as HTMLInputElement;
  const category = document.getElementById(
    "abuse-category"
  ) as HTMLSelectElement;
  const button = document.getElementById(
    "abuse-submit"
  ) as HTMLButtonElement;
  const status = document.getElementById("abuse-status")!;

  let busy = false;

  reportForm.addEventListener("submit", event => {
    event.preventDefault();
    if (busy) return;

    void (async () => {
      busy = true;
      button.disabled = true;

      try {
        const id = reportTransferId(input.value);
        input.value = id;
        status.textContent = "Submitting report…";

        const response = await fetch("/api/abuse/reports", {
          method: "POST",
          credentials: "same-origin",
          cache: "no-store",
          redirect: "error",
          signal: AbortSignal.timeout(15000),
          headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "transfer-serv"
          },
          body: JSON.stringify({
            transfer_id: id,
            category: category.value
          })
        });

        if (!response.ok) {
          throw new Error(
            response.status === 429
              ? "Too many reports. Please try again later."
              : response.status === 404
                ? "That transfer is unavailable or has expired."
                : "Could not submit the report. Please try again later."
          );
        }

        reportForm.reset();
        status.textContent =
          "Report received for review. Reports do not automatically remove files.";
      } catch (error) {
        status.textContent = error instanceof Error
          ? error.message
          : "Could not submit report.";
      } finally {
        busy = false;
        button.disabled = false;
      }
    })();
  });
}