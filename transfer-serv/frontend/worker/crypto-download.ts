/* Classic service worker for streamed decrypted downloads, including Firefox. */
const scope = self as unknown as ServiceWorkerGlobalScope;

type DownloadEntry = {
  id: string;
  opaque: string;
  path: string;
  size: number;
  key: CryptoKey;
};

type DownloadJob = {
  transfer: string;
  files: DownloadEntry[];
  zip: boolean;
  expires: number;
  port: MessagePort;
};

const downloadJobs = new Map<string, DownloadJob>();
const textEncoder = new TextEncoder();
const BLOCK = 16 * 1024 * 1024 - 16;

scope.addEventListener(
  "install",
  event => event.waitUntil(scope.skipWaiting())
);

scope.addEventListener(
  "activate",
  event => event.waitUntil(scope.clients.claim())
);

scope.addEventListener("message", event => {
  event.waitUntil((async () => {
    if (
      !event.source ||
      !("id" in event.source) ||
      !event.ports[0]
    ) return;

    const client = await scope.clients.get(event.source.id);
    if (!client) return;

    const url = new URL(client.url);

    if (
      url.origin !== scope.location.origin ||
      url.pathname !== "/transfer.php"
    ) return;

    const data = event.data;

    if (
      !data ||
      data.type !== "encrypted-download-v2" ||
      !/^[A-Za-z0-9_-]{32}$/.test(data.transfer) ||
      !/^[A-Za-z0-9_-]{48}$/.test(data.token) ||
      !Array.isArray(data.files) ||
      !data.files.length ||
      data.files.length > 200 ||
      typeof data.zip !== "boolean"
    ) return;

    for (const file of data.files) {
      if (
        !/^[A-Za-z0-9_-]{32}$/.test(file.id) ||
        !/^[A-Za-z0-9_-]{32}\.fv$/.test(file.opaque) ||
        !Number.isSafeInteger(file.size) ||
        file.size < 0 ||
        typeof file.path !== "string" ||
        file.path.length > 1024 ||
        /[\\\x00-\x1f\x7f]/.test(file.path) ||
        file.path.split("/").some(
          (p: string) => p === "" || p === "." || p === ".."
        ) ||
        !(file.key instanceof CryptoKey) ||
        file.key.algorithm.name !== "AES-GCM"
      ) return;
    }

    for (const [token, job] of downloadJobs) {
      if (job.expires < Date.now()) downloadJobs.delete(token);
    }

    if (downloadJobs.size >= 8) {
      event.ports[0].postMessage({
        error: "Too many pending downloads."
      });
      return;
    }

    downloadJobs.set(data.token, {
      ...data,
      expires: Date.now() + 60000,
      port: event.ports[0]
    });

    event.ports[0].postMessage({ ready: true });
  })());
});

async function* decryptFile(
  transfer: string,
  file: DownloadEntry,
  signal?: AbortSignal
): AsyncGenerator<Uint8Array<ArrayBuffer>> {
  const abort = new AbortController();
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;

  try {
    const response = await fetch(
      `/download.php?transfer=${transfer}&file=${file.id}`,
      {
        cache: "no-store",
        redirect: "error",
        signal: signal
          ? AbortSignal.any([signal, abort.signal])
          : abort.signal
      }
    );

    if (!response.ok || !response.body) {
      throw new Error("Encrypted download unavailable.");
    }

    reader = response.body.getReader();

    let pending = new Uint8Array(0);
    let consumed = 0;
    let received = 0;

    const count = Math.max(1, Math.ceil(file.size / BLOCK));

    for (let index = 0; index < count; index++) {
      const plainSize = Math.min(BLOCK, file.size - index * BLOCK);
      const block = new Uint8Array(plainSize + 16);
      let offset = 0;

      while (offset < block.length) {
        if (consumed === pending.length) {
          const next = await reader.read();

          if (next.done) {
            throw new Error("Encrypted file is incomplete.");
          }

          pending = new Uint8Array(next.value);
          consumed = 0;
        }

        const length = Math.min(
          block.length - offset,
          pending.length - consumed
        );

        block.set(
          pending.subarray(consumed, consumed + length),
          offset
        );

        offset += length;
        consumed += length;
      }

      const iv = new Uint8Array(12);
      new DataView(iv.buffer).setBigUint64(4, BigInt(index));

      const decrypted = new Uint8Array(
        await crypto.subtle.decrypt(
          {
            name: "AES-GCM",
            iv,
            tagLength: 128,
            additionalData: textEncoder.encode(
              `filevoya:v2:${file.opaque}:${file.size}:${index}`
            )
          },
          file.key,
          block
        )
      );

      received += decrypted.length;

      if (index === count - 1) {
        if (
          consumed !== pending.length ||
          !(await reader.read()).done ||
          received !== file.size
        ) {
          throw new Error("Encrypted file size does not match.");
        }
      }

      if (decrypted.length) yield decrypted;
    }
  } finally {
    abort.abort();
    await reader?.cancel().catch(() => {});
  }
}

const crcTable = Uint32Array.from({ length: 256 }, (_, n) => {
  for (let bit = 0; bit < 8; bit++) {
    n = (n >>> 1) ^ ((n & 1) ? 0xedb88320 : 0);
  }
  return n >>> 0;
});

function crcUpdate(crc: number, data: Uint8Array): number {
  for (const byte of data) {
    crc = (crc >>> 8) ^ crcTable[(crc ^ byte) & 255];
  }
  return crc >>> 0;
}

function buffer(length: number): [Uint8Array<ArrayBuffer>, DataView] {
  const bytes = new Uint8Array(length);
  return [bytes, new DataView(bytes.buffer)];
}

/* Stored ZIP64: bounded memory, UTF-8 names, CRC32, 64-bit sizes and offsets. */
async function* zipFiles(
  job: DownloadJob,
  signal?: AbortSignal
): AsyncGenerator<Uint8Array<ArrayBuffer>> {
  const central: Uint8Array<ArrayBuffer>[] = [];
  let position = 0n;

  for (const file of job.files) {
    const name = textEncoder.encode(file.path);
    const size = BigInt(file.size);
    const start = position;
    const [header, h] = buffer(30 + name.length + 20);

    h.setUint32(0, 0x04034b50, true);
    h.setUint16(4, 45, true);
    h.setUint16(6, 0x808, true);
    h.setUint16(12, 33, true);
    h.setUint32(18, 0xffffffff, true);
    h.setUint32(22, 0xffffffff, true);
    h.setUint16(26, name.length, true);
    h.setUint16(28, 20, true);
    header.set(name, 30);

    const extra = 30 + name.length;
    h.setUint16(extra, 1, true);
    h.setUint16(extra + 2, 16, true);
    h.setBigUint64(extra + 4, size, true);
    h.setBigUint64(extra + 12, size, true);

    position += BigInt(header.length);
    yield header;

    let crc = 0xffffffff;

    for await (const chunk of decryptFile(job.transfer, file, signal)) {
      crc = crcUpdate(crc, chunk);
      position += BigInt(chunk.length);
      yield chunk;
    }

    crc = (crc ^ 0xffffffff) >>> 0;

    const [descriptor, d] = buffer(24);
    d.setUint32(0, 0x08074b50, true);
    d.setUint32(4, crc, true);
    d.setBigUint64(8, size, true);
    d.setBigUint64(16, size, true);

    position += 24n;
    yield descriptor;

    const [entry, c] = buffer(46 + name.length + 28);
    c.setUint32(0, 0x02014b50, true);
    c.setUint16(4, 45, true);
    c.setUint16(6, 45, true);
    c.setUint16(8, 0x808, true);
    c.setUint16(14, 33, true);
    c.setUint32(16, crc, true);
    c.setUint32(20, 0xffffffff, true);
    c.setUint32(24, 0xffffffff, true);
    c.setUint16(28, name.length, true);
    c.setUint16(30, 28, true);
    c.setUint32(42, 0xffffffff, true);
    entry.set(name, 46);

    const e = 46 + name.length;
    c.setUint16(e, 1, true);
    c.setUint16(e + 2, 24, true);
    c.setBigUint64(e + 4, size, true);
    c.setBigUint64(e + 12, size, true);
    c.setBigUint64(e + 20, start, true);

    central.push(entry);
  }

  const directoryStart = position;

  for (const entry of central) {
    position += BigInt(entry.length);
    yield entry;
  }

  const [end, z] = buffer(98);
  z.setUint32(0, 0x06064b50, true);
  z.setBigUint64(4, 44n, true);
  z.setUint16(12, 45, true);
  z.setUint16(14, 45, true);
  z.setBigUint64(24, BigInt(job.files.length), true);
  z.setBigUint64(32, BigInt(job.files.length), true);
  z.setBigUint64(40, position - directoryStart, true);
  z.setBigUint64(48, directoryStart, true);
  z.setUint32(56, 0x07064b50, true);
  z.setBigUint64(64, position, true);
  z.setUint32(72, 1, true);
  z.setUint32(76, 0x06054b50, true);
  z.setUint16(84, 0xffff, true);
  z.setUint16(86, 0xffff, true);
  z.setUint32(88, 0xffffffff, true);
  z.setUint32(92, 0xffffffff, true);

  yield end;
}

scope.addEventListener("fetch", event => {
  const url = new URL(event.request.url);

  if (
    url.origin !== scope.location.origin ||
    !url.pathname.startsWith("/e2ee-download/")
  ) return;

  const token = url.pathname.slice("/e2ee-download/".length);
  const job = downloadJobs.get(token);
  downloadJobs.delete(token);

  if (
    event.request.method !== "GET" ||
    !job ||
    job.expires < Date.now()
  ) {
    event.respondWith(new Response(
      "Download expired. Start again from the share page.",
      { status: 410 }
    ));
    return;
  }

  let finish!: () => void;

  event.waitUntil(new Promise<void>(resolve => {
    finish = resolve;
  }));

  const abort = new AbortController();

  const generator = job.zip
    ? zipFiles(job, abort.signal)
    : decryptFile(job.transfer, job.files[0], abort.signal);

  const stream = new ReadableStream<Uint8Array<ArrayBuffer>>({
    async pull(controller) {
      try {
        const next = await generator.next();

        if (next.done) {
          controller.close();
          job.port.postMessage({ complete: true });
          job.port.close();
          finish();
        } else {
          controller.enqueue(next.value);
        }
      } catch {
        controller.error(new Error(
          "File authentication or download failed."
        ));

        job.port.postMessage({
          error: "Download failed verification or was interrupted. Discard any partial download and retry."
        });

        job.port.close();
        finish();
      }
    },

    async cancel() {
      abort.abort();
      await generator.return(undefined);
      job.port.postMessage({ error: "Download cancelled." });
      job.port.close();
      finish();
    }
  }, { highWaterMark: 0 });

  const name = job.zip
    ? "Filevoya-files.zip"
    : job.files[0].path.split("/").at(-1)!;

  const headers = new Headers({
    "Content-Type": job.zip
      ? "application/zip"
      : "application/octet-stream",

    "Content-Disposition":
      "attachment; filename*=UTF-8''" +
      encodeURIComponent(name).replace(
        /['()*]/g,
        c => "%" + c.charCodeAt(0).toString(16)
      ),

    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox"
  });

  // Zero Content-Length could skip empty-file authentication.
  if (!job.zip && job.files[0].size > 0) {
    headers.set("Content-Length", String(job.files[0].size));
  }

  event.respondWith(new Response(stream, { headers }));
});