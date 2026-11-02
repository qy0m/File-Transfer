"""Encrypted storage checks using temporary data and private API processes.

On Linux, run npm ci && npm run build, then:
    .venv/bin/python scripts/test-storage-limits.py
Requires Node.js 24+ and this environment's installed API requirements.
"""
import base64
from contextlib import contextmanager
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

PROJECT = Path(__file__).resolve().parents[1]
ENCRYPTION_JS = PROJECT / "frontend/public/assets/js/encryption.js"
FIXTURE_JS = r"""
import {pathToFileURL} from 'node:url';
globalThis.isSecureContext = true;
const e = await import(pathToFileURL(process.argv[1]).href);
const file = new File(
    [new Uint8Array(Number(process.argv[2])).fill(120)],
    'quota-test.txt'
);
const plan = await e.createEncryptionPlan([file], [file.name]);
const chunks = [];
for (
    let offset = 0;
    offset < e.wireSize(file.size);
    offset += e.WIRE_CHUNK
) {
    chunks.push(
        Buffer.from(await e.encryptedChunk(plan, 0, file, offset))
    );
}
console.log(JSON.stringify({
    body: {
        encryption: plan.encryption,
        files: plan.files.map(f => ({
            name: f.opaque,
            relative_path: f.opaque,
            size_bytes: e.wireSize(f.size)
        }))
    },
    bytes: Buffer.concat(chunks).toString('base64')
}));
"""


def fixture(plain_size):
    result = subprocess.run(
        [
            "node", "--input-type=module", "-e", FIXTURE_JS,
            str(ENCRYPTION_JS), str(plain_size),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    value = json.loads(result.stdout)
    value["bytes"] = base64.b64decode(value["bytes"])
    return value


class Client:
    def __init__(self, origin):
        self.origin = origin
        self.cookies = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))

    def call(
        self, method, path, payload=None, expected=200,
        headers=None, timeout=15,
    ):
        binary = isinstance(payload, bytes)
        if binary:
            data = payload
        elif payload is not None:
            data = json.dumps(payload).encode()
        else:
            data = None

        request_headers = {
            "Origin": self.origin,
            "X-Requested-With": "transfer-serv",
            "X-Transfer-Client-IP": "203.0.113.10",
        }
        if payload is not None:
            request_headers["Content-Type"] = (
                "application/octet-stream"
                if binary else "application/json"
            )
        request_headers.update(headers or {})
        request = Request(
            self.origin + path,
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            response = self.opener.open(request, timeout=timeout)
        except HTTPError as error:
            response = error

        with response:
            body = response.read()
            if response.status != expected:
                raise AssertionError(
                    f"{method} {path}: expected {expected}, "
                    f"got {response.status}: {body[:300]!r}"
                )
            if "application/json" in response.headers.get(
                "Content-Type", ""
            ):
                return json.loads(body)
            return body

    def register(self, username):
        credentials = {
            "username": username,
            "password": secrets.token_urlsafe(32),
        }
        self.call("POST", "/auth/register", credentials, 201)
        return credentials

    def create(self, plain_size, expected=201, headers=None):
        data = fixture(plain_size)
        transfer = self.call(
            "POST", "/transfers", data["body"], expected, headers
        )
        return transfer, data["bytes"]

    def complete(self, transfer, encrypted):
        transfer_id = transfer["id"]
        file_id = transfer["files"][0]["id"]
        self.call(
            "PUT",
            f"/transfers/{transfer_id}/files/{file_id}/chunks?offset=0",
            encrypted,
            headers={"X-Upload-Token": transfer["upload_token"]},
        )
        downloaded = self.call(
            "GET",
            f"/transfers/{transfer_id}/files/{file_id}/download",
        )
        assert downloaded == encrypted, "Stored encrypted bytes changed."


@contextmanager
def temporary_api(**limits):
    with tempfile.TemporaryDirectory(
        prefix="filevoya-storage-test-"
    ) as directory:
        root = Path(directory)
        with socket.socket(
            socket.AF_INET, socket.SOCK_STREAM
        ) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            port = listener.getsockname()[1]
            origin = f"http://127.0.0.1:{port}"
            environment = {
                **os.environ,
                "PYTHONPATH": str(PROJECT / "api"),
                "DATABASE_PATH": str(root / "test.sqlite3"),
                "UPLOAD_PATH": str(root / "uploads"),
                "APP_ORIGIN": origin,
                "COOKIE_SECURE": "0",
                "TRUSTED_PROXY_NETWORKS": "127.0.0.1/32",
                "MIN_FREE_DISK_BYTES": "0",
                "MAX_STORAGE_BYTES": "1000",
                "MAX_STORED_TRANSFERS": "100",
                "MAX_ACTIVE_BYTES_PER_CLIENT": "10000",
                "MAX_DAILY_BYTES_PER_CLIENT": "100000",
                "MAX_DAILY_TRANSFERS_PER_CLIENT": "100",
                "FILEVOYA_TEST_FD": str(listener.fileno()),
                "FILEVOYA_TEST_PORT": str(port),
                **{
                    key: str(value)
                    for key, value in limits.items()
                },
            }
            runner = (
                "import os,socket,uvicorn; "
                "sock=socket.socket(fileno=int("
                "os.environ['FILEVOYA_TEST_FD'])); "
                "config=uvicorn.Config("
                "'app.main:app',host='127.0.0.1',"
                "port=int(os.environ['FILEVOYA_TEST_PORT']),"
                "proxy_headers=False,log_level='error'); "
                "uvicorn.Server(config).run(sockets=[sock])"
            )
            with (root / "server.log").open("w+") as log:
                process = subprocess.Popen(
                    [sys.executable, "-c", runner],
                    cwd=PROJECT,
                    env=environment,
                    pass_fds=(listener.fileno(),),
                    stdout=log,
                    stderr=log,
                )
                try:
                    client = Client(origin)
                    for _ in range(60):
                        if process.poll() is not None:
                            break
                        ready = False
                        try:
                            ready = client.call(
                                "GET", "/health", timeout=0.5
                            )["ok"]
                        except (
                            URLError, TimeoutError, ConnectionError
                        ):
                            time.sleep(0.1)
                        if ready:
                            yield client
                            return
                    log.seek(0)
                    raise RuntimeError(
                        "Temporary API did not start:\n" + log.read()
                    )
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


def main():
    if os.name != "posix":
        raise SystemExit(
            "Run this test on Linux or another POSIX system."
        )
    if not shutil.which("node") or not ENCRYPTION_JS.is_file():
        raise SystemExit(
            "Install Node.js 24+, then run npm ci "
            "and npm run build first."
        )

    with temporary_api(
        MAX_STORAGE_BYTES=100, MAX_STORED_TRANSFERS=2
    ) as client:
        client.register("quota-owner")
        first, data = client.create(44)  # 60 encrypted bytes.
        client.create(25, 507)  # 41 bytes exceed the remaining 40.
        client.complete(first, data)
        client.create(24)  # 40 bytes fill the remaining pool.
        client.create(0, 507)
        result = client.call(
            "DELETE", "/account/transfers/" + first["id"]
        )
        assert result["storage_deleted"] is True
        client.call(
            "GET", "/transfers/" + first["id"], expected=404
        )
        client.create(44)
        print("PASS: encrypted reservations and owner deletion.")

    with temporary_api(MAX_STORED_TRANSFERS=2) as client:
        for _ in range(2):
            transfer, data = client.create(0)
            client.complete(transfer, data)
        client.create(0, 507)  # Byte capacity remains available.
        print(
            "PASS: transfer record cap independently of stored bytes."
        )

    with temporary_api(
        MAX_ACTIVE_BYTES_PER_CLIENT=80,
        MAX_DAILY_BYTES_PER_CLIENT=120,
    ) as client:
        owner = client.register("quota-owner")
        first, data = client.create(44)
        client.complete(first, data)
        client.cookies.clear()
        client.create(5, 429)  # 60 + 21 exceeds the shared IP cap.
        client.register("quota-second")
        client.create(5, 429)
        client.call("POST", "/auth/login", owner)
        client.call(
            "DELETE", "/account/transfers/" + first["id"]
        )
        second, data = client.create(44)
        client.complete(second, data)
        client.call(
            "DELETE", "/account/transfers/" + second["id"]
        )
        client.create(0, 429)  # Daily allocation is not refunded.
        print(
            "PASS: shared-IP limits across cookies/accounts "
            "and daily allocation retention."
        )

    with temporary_api(
        MAX_DAILY_TRANSFERS_PER_CLIENT=3
    ) as client:
        for _ in range(3):
            transfer, data = client.create(0)
            client.complete(transfer, data)
        client.create(0, 429)
        client.cookies.clear()
        client.create(
            0,
            headers={"X-Transfer-Client-IP": "203.0.113.11"},
        )
        print(
            "PASS: daily transfer count "
            "and independent client IP budgets."
        )

    print(
        "All encrypted storage-limit checks passed. "
        "Temporary test data removed."
    )


if __name__ == "__main__":
    main()
