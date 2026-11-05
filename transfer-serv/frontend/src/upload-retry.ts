/* Retry explicit busy responses using the same encrypted chunk bytes. */
export async function fetchChunkWithRetry(
  send: () => Promise<Response>,
  onWait: (seconds: number) => void
): Promise<Response> {
  const started = performance.now();

  for (let attempt = 0; ; attempt++) {
    const response = await send();

    if (
      (response.status !== 429 && response.status !== 503) ||
      attempt >= 7
    ) return response;

    const header = response.headers.get("Retry-After");
    let required = 0;

    if (header) {
      if (/^\d+$/.test(header)) {
        required = Number(header) * 1000;
      } else {
        const until = Date.parse(header);
        if (Number.isFinite(until)) {
          required = Math.max(0, until - Date.now());
        }
      }
    }

    const backoff = Math.min(10000, 1000 * 2 ** attempt);
    const delay = Math.max(
      required,
      backoff * (0.5 + Math.random())
    );

    if (performance.now() - started + delay > 60000) {
      return response;
    }

    await response.body?.cancel().catch(() => {});
    onWait(Math.ceil(delay / 1000));
    await new Promise<void>(resolve => setTimeout(resolve, delay));
  }
}