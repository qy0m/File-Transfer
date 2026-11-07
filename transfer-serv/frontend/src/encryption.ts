/* Filevoya E2EE v2: independent AES-256-GCM file keys: authenticated framing. */
export const PLAIN_CHUNK = 16 * 1024 * 1024 - 16;
export const WIRE_CHUNK = PLAIN_CHUNK + 16;
const encoder = new TextEncoder();

export type SecretFile = {
    opaque: string;
    path: string;
    size: number;
    key: string;
};

export type EncryptionPlan = {
    key: string;
    encryption: { version: 2; manifest: string };
    files: SecretFile[];
    keys: CryptoKey[];
};

export function encode64(bytes: Uint8Array): string {
    let text = "";
    for (const byte of bytes) text += String.fromCharCode(byte);
    return btoa(text)
        .replaceAll("+", "-")
        .replaceAll("/", "_")
        .replace(/=+$/, "");
}

export function decode64(text: string): Uint8Array<ArrayBuffer> {
    if (!/^[A-Za-z0-9_-]+$/.test(text) || text.length % 4 === 1) {
        throw new Error("Invalid encryption data.");
    }

    const raw = atob(text.replaceAll("-", "+").replaceAll("_", "/"));
    const bytes = Uint8Array.from(raw, ch => ch.charCodeAt(0));

    if (encode64(bytes) !== text) {
        throw new Error("Invalid encryption data.");
    }

    return bytes;
}

export function importKey(
    raw: Uint8Array<ArrayBuffer>,
    usages: KeyUsage[]
): Promise<CryptoKey> {
    if (raw.length !== 32) throw new Error("Invalid encryption key.");

    return crypto.subtle.importKey(
        "raw", raw, "AES-GCM", false, usages
    );
}

export function wireSize(size: number): number {
    const result =
        size + Math.max(1, Math.ceil(size / PLAIN_CHUNK)) * 16;

    if (
        !Number.isSafeInteger(size) ||
        size < 0 ||
        !Number.isSafeInteger(result)
    ) {
        throw new Error("File exceeds the supported size.");
    }

    return result;
}

export function chunkParameters(
    file: SecretFile,
    index: number
): AesGcmParams {
    if (!Number.isSafeInteger(index) || index < 0) {
        throw new Error("Invalid chunk.");
    }

    const iv = new Uint8Array(12);
    new DataView(iv.buffer).setBigUint64(4, BigInt(index));

    return {
        name: "AES-GCM",
        iv,
        tagLength: 128,
        additionalData: encoder.encode(
            `filevoya:v2:${file.opaque}:${file.size}:${index}`
        )
    };
}

export async function createEncryptionPlan(
    files: File[],
    paths: string[]
): Promise<EncryptionPlan> {
    if (!isSecureContext || !crypto.subtle) {
        throw new Error(
            "Encrypted uploads require HTTPS and browser encryption support."
        );
    }

    if (
        files.length !== paths.length ||
        !files.length ||
        files.length > 200 ||
        paths.some(
            (path, index) =>
                !validPath(path) ||
                path.split("/").at(-1) !== files[index].name
        ) ||
        new Set(paths).size !== paths.length
    ) {
        throw new Error("Invalid or duplicate file paths.");
    }

    const pathSet = new Set(paths);

    for (const path of paths) {
        const segments = path.split("/");

        for (let end = 1; end < segments.length; end++) {
            if (pathSet.has(segments.slice(0, end).join("/"))) {
                throw new Error("A file cannot also be a folder.");
            }
        }
    }

    const secrets: SecretFile[] = files.map((file, index) => ({
        opaque:
            encode64(crypto.getRandomValues(new Uint8Array(24))) + ".fv",
        path: paths[index],
        size: file.size,
        key: encode64(crypto.getRandomValues(new Uint8Array(32)))
    }));

    const rawKey = crypto.getRandomValues(new Uint8Array(32));
    const key = await importKey(rawKey, ["encrypt"]);
    const iv = crypto.getRandomValues(new Uint8Array(12));

    const encrypted = new Uint8Array(
        await crypto.subtle.encrypt(
            {
                name: "AES-GCM",
                iv,
                tagLength: 128,
                additionalData: encoder.encode("filevoya:manifest:v2")
            },
            key,
            encoder.encode(JSON.stringify({ version: 2, files: secrets }))
        )
    );
    
    const packed = new Uint8Array(iv.length + encrypted.length);
    packed.set(iv);
    packed.set(encrypted, iv.length);

    return {
        key: encode64(rawKey),
        encryption: { version: 2, manifest: encode64(packed) },
        files: secrets,
        keys: await Promise.all(
            secrets.map(file =>
                importKey(decode64(file.key), ["encrypt"])
            )
        )
    };
}

export async function encryptedChunk(
    plan: EncryptionPlan,
    index: number,
    file: File,
    wireOffset: number
): Promise<Uint8Array<ArrayBuffer>> {
    if (wireOffset % WIRE_CHUNK !== 0) {
        throw new Error(
            "Invalid encrypted upload offset. Start a new transfer."
        );
    }

    const chunkIndex = wireOffset / WIRE_CHUNK;
    const start = chunkIndex * PLAIN_CHUNK;

    const data = await file
        .slice(start, Math.min(start + PLAIN_CHUNK, file.size))
        .arrayBuffer();

    return new Uint8Array(
        await crypto.subtle.encrypt(
            chunkParameters(plan.files[index], chunkIndex),
            plan.keys[index],
            data
        )
    );
}

export function validPath(path: unknown): path is string {
    return (
        typeof path === "string" &&
        encoder.encode(path).length <= 1024 &&
        !/[\\\x00-\x1f\x7f]/.test(path) &&
        !/^[A-Za-z]:/.test(path) &&
        path.split("/").every(
            part =>
                part !== "" &&
                part !== "." &&
                part !== ".." &&
                part.length <= 255
        )
    );
}

export async function decryptManifest(
    packed: string,
    key: string
): Promise<SecretFile[]> {
    const raw = decode64(packed);

    const data = await crypto.subtle.decrypt(
        {
            name: "AES-GCM",
            iv: raw.slice(0, 12),
            tagLength: 128,
            additionalData: encoder.encode("filevoya:manifest:v2")
        },
        await importKey(decode64(key), ["decrypt"]),
        raw.slice(12)
    );

    const result = JSON.parse(
        new TextDecoder("utf-8", { fatal: true }).decode(data)
    );

    if (
        !result ||
        result.version !== 2 ||
        !Array.isArray(result.files) ||
        result.files.length < 1 ||
        result.files.length > 200
    ) {
        throw new Error("Invalid manifest.");
    }

    const names = new Set<string>();
    const paths = new Set<string>();

    for (const file of result.files) {
        if (
            !file ||
            typeof file.opaque !== "string" ||
            !/^[A-Za-z0-9_-]{32}\.fv$/.test(file.opaque) ||
            names.has(file.opaque) ||
            !validPath(file.path) ||
            paths.has(file.path) ||
            typeof file.key !== "string" ||
            decode64(file.key).length !== 32
        ) {
            throw new Error("Invalid encrypted file metadata.");
        }

        wireSize(file.size);
        names.add(file.opaque);
        paths.add(file.path);
    }

    for (const path of paths) {
        const segments = path.split("/");

        for (let i = 1; i < segments.length; i++) {
            if (paths.has(segments.slice(0, i).join("/"))) {
                throw new Error("Conflicting folder paths.");
            }
        }
    }

    return result.files as SecretFile[];
}