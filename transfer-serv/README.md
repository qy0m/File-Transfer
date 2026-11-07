# Filevoya

Self-hosted file and folder sharing with expiring links, guest uploads,
optional accounts, and browser encryption. The project directory is transfer-serv.

## Stack

PHP 8.4, TypeScript, Bootstrap 5, CSS, Node.js 24, Python 3.12/FastAPI,
SQLite3, NGINX, and Docker Compose. TypeScript uses tsc; no Vite is required.

## Features and encryption

New browser uploads use AES-256-GCM for file contents, names, and folder paths.
The complete share link contains the decryption key. Keep it private: anyone
with it can decrypt the transfer, and the server cannot recover a lost key.
The server still processes encrypted sizes, file counts, ownership, and
connection information. Browser encryption depends on the website code delivered.

Regular accounts and guest browsers have a 5 GB storage allowance, with up to
25 files per regular transfer. Encryption adds overhead. Transfers expire after
24 hours; incomplete uploads expire after 15 minutes without a successful chunk.
Accounts support transfer management and password changes; passwords use Argon2.

## Encryption format 2: 16 MiB chunks

New uploads use **format version 2**, with one encrypted chunk of up to
**16 MiB per request**, including its 16-byte AES-GCM authentication tag.
A full chunk contains `16 * 1024 * 1024 - 16` plaintext bytes. Empty files
and the final partial chunk are authenticated as well.

Individual files are decrypted in the browser. Encrypted ZIP downloads
must be started from the unlocked share page; the browser decrypts the
files and assembles the archive. Transfer pages recognize the presence
of encrypted metadata instead of routing unfamiliar encryption versions
to ordinary server downloads. The browser still validates format 2.

The generic Compose default remains **four concurrent upload requests per
gateway process**. The reference deployment uses `MAX_ACTIVE_UPLOADS=10`
and has passed ten-client upload and ciphertext-download checks through
its HTTPS relay. Capacity and throughput depend on the deployment;
16 MiB chunks increase memory requirements per active request.

### Upgrading an existing version-1 installation

**This is a breaking encrypted-format change. Version-1 encrypted transfers
are not readable by the version-2 browser code and are not converted automatically.**

1. Stop new uploads and save consistent, encrypted backups of the database,
   stored uploads, configuration, and the previously working application.
   Verify that rollback images can be inspected and started before stopping
   the running containers.
2. Let old transfers expire and run cleanup, or deliberately remove them
   through the existing transfer-deletion tools. Before upgrading a
   version-1 database, verify that `transfers`, `files`, and
   `transfer_encryption` are empty and old upload files have been removed.
   **Keep the SQLite database file: it also contains user accounts.**
3. Update the API, gateway, PHP pages, browser modules, and service worker
   together. Startup upgrades the empty encryption table to version 2
   while retaining accounts and account-session records. It refuses the
   version-1 upgrade if old transfer records remain.
4. Allow bodies of at least **16 MiB** at every reverse proxy; for NGINX,
   use `client_max_body_size 16m;` or a larger proxy limit. The API and
   gateway enforce their own 16 MiB chunk limit. Preserve private host
   bindings, storage mounts, and trusted-proxy settings.
5. Hard-refresh the browser after deployment. Check sign-in, then upload a
   file larger than 32 MiB and verify the actual contents of both its
   individual download and its browser-generated ZIP download.

Older cached upload pages send version-1 metadata and are rejected by
the updated API. Open the refreshed site and start a new upload.

## Required filenames before setup

This upload includes three filenames with a leading `!` as a workaround for uploading hidden files.
Before installing, building, or running the project, restore their standard names inside `transfer-serv/`:

| Uploaded file | Required action |
| --- | --- |
| `!.env.example` | Rename to `.env.example`. |
| `!.gitignore` | Replace the older `.gitignore` with this file's contents, then remove `!.gitignore`. |
| `!.dockerignore` | Replace the older `.dockerignore` with this file's contents, then remove `!.dockerignore`. |

Keep the `!.env.example` line **inside** `.gitignore`: it is a Git
exception rule allowing the safe example file to be tracked.
Never publish your real `.env` or private keys.

## Local Docker setup on Linux

Install Docker Engine and the Compose plugin. In the project directory:

    cp .env.example .env
    mkdir -p var/database var/uploads
    sudo chown -R 10001:10001 var/database var/uploads
    sudo chmod 750 var/database var/uploads
    docker compose config --quiet
    docker compose up -d --build
    docker compose ps
    curl --fail http://127.0.0.1:8080/api/health

Use sudo for Docker commands if your installation requires it.
Open http://127.0.0.1:8080 on the same machine. The example COOKIE_SECURE=0
setting is for local HTTP only. Use HTTPS, COOKIE_SECURE=1, and your exact
public APP_ORIGIN for a public deployment.

DATA_ROOT selects the host storage directory. Create database and uploads below
it and give UID 10001 write access. Mount encrypted storage before starting.
DOCKER_SUBNET must be an unused private subnet; Compose uses the same value
for the API trusted proxy network. Limits are documented in .env.example.

The supplied NGINX configuration serves HTTP and routes PHP and API requests.
It does not provision HTTPS, WireGuard, disk encryption, or a public relay.
Behind another reverse proxy, configure NGINX real-IP handling for only trusted
proxy addresses and their authoritative client-IP header. Until then, limits
identify the immediate proxy peer. Never trust arbitrary forwarding headers.

## Development and checks

For native Linux development, install the runtimes listed above, then run:

    npm ci
    python3 -m venv .venv
    .venv/bin/python -m pip install -r api/requirements.txt
    mkdir -p var/native/database var/native/uploads
    env DATABASE_PATH=var/native/database/transfers.sqlite3 UPLOAD_PATH=var/native/uploads npm run dev

The native launcher supplies its own environment; it does not load Compose .env.
Run npm run check, npm run build, Python syntax checks, and PHP linting.
Then test an encrypted browser upload, a full share link in a second browser,
individual and folder downloads, and account-owned deletion.

After installing the API requirements and running `npm ci` and
`npm run build`, run the encrypted storage checks on Linux from
the `transfer-serv/` directory:

    .venv/bin/python scripts/test-storage-limits.py

The test requires Node.js 24 or newer. It generates encrypted requests
using the built frontend encryption module and starts private API
processes with temporary databases and upload directories.

It checks storage reservations, transfer counts, owner deletion,
shared-IP limits across cookies and accounts, and daily allocations
retained after deletion. It does not target your running deployment.

## Upload concurrency

`MAX_ACTIVE_UPLOADS` controls concurrent upload-chunk requests per
gateway process. Compose defaults to four. Increase this value only
after measuring memory use, storage performance, and throughput on
your deployment. Reverse-proxy limits are configured separately.

The uploader retries chunk requests receiving HTTP 429 or 503 up to
seven times, using randomized delays and respecting `Retry-After`,
within a 60-second retry window. Individual request timeouts still
apply. Transfer creation is not automatically replayed. If automatic
retries are exhausted, keep the page open and use Resume upload.

A configured concurrency limit is not a throughput guarantee.
Server-local capacity tests do not measure internet or relay performance.

## Logging and privacy

The container defaults disable routine API, NGINX, and PHP access logs.
Docker logs rotate at 5 MB and retain two files per container. These
are size-based limits, not time-based retention. Diagnostic errors
and hosting-provider logs may still contain connection metadata.
External reverse proxies require separate logging configuration.
These settings do not establish a no-logs or anonymity guarantee.
Existing containers must be recreated to adopt changed logging options.

## Publishing and deployment

Keep .env, private keys, databases, uploads, logs, and backups out of Git.
Ignore rules do not remove already-tracked files or earlier commits.
Private deployment overrides belong in ignored compose.override.yaml files.
This public Compose template changes host bindings, storage paths, and networks;
migrate an existing live deployment deliberately. Review about.php so its
deployment descriptions match your own infrastructure.
Retain the bundled third-party icon license notices.
The project is licensed under the [Apache License 2.0](../LICENSE).
