import http.cookiejar
import json

from urllib.error import HTTPError
from urllib.request import (
    HTTPCookieProcessor,
    Request,
    build_opener,
)

BASE = "http://127.0.0.1:8002"

opener = build_opener(
    HTTPCookieProcessor(http.cookiejar.CookieJar())
)

def call(
    method,
    path,
    payload=None,
    expected=200,
    extra_headers=None,
):
    binary = isinstance(payload, bytes)

    data = (
        payload if binary
        else json.dumps(payload).encode("utf-8")
        if payload is not None
        else None
    )

    headers = {
        "Content-Type": (
            "application/octet-stream"
            if binary
            else "application/json"
        ),
        "X-Requested-With": "transfer-serv",
    }

    headers.update(extra_headers or {})

    request = Request(
        BASE + path,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        response = opener.open(request, timeout=15)
    except HTTPError as error:
        response = error

    with response:
        status = response.status
        body = json.loads(response.read())

    assert status == expected, (
        method,
        path,
        status,
        body,
    )

    return body



def create(size, expected=201):
    return call(
        "POST",
        "/transfers",
        {
            "files": [
                {
                    "name": "quota-test.txt",
                    "size_bytes": size,
                }
            ]
        },
        expected,
    )

call(
    "POST",
    "/auth/register",
    {
        "username": "quota-test",
        "password": "Local-quota-test-password!",
    },
    201,
)

first = create(60)
create(41, 507)

print("PASS: pending upload reserves capacity.")

call(
    "PUT",
    (
        f"/transfers/{first['id']}/files/"
        f"{first['files'][0]['id']}/chunks?offset=0"
    ),
    b"x" * 60,
    extra_headers={
        "X-Upload-Token": first["upload_token"],
    },
)

call("GET", "/transfers/" + first["id"])

create(40)
create(0, 507)

print(
    "PASS: ready uploads keep their reservation; "
    "record cap blocks zero_byte transfers."
)

result = call(
    "DELETE",
    "/account/transfers/" + first["id"],
)

assert result["storage_deleted"] is True

call(
    "GET",
    "/transfers/" + first["id"],
    expected=404,
)

create(60)

print("PASS: deletion releases capacity.")
print("All storage-limit checks passed.")