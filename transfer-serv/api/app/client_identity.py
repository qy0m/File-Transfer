import hashlib
import ipaddress
import os

from fastapi import HTTPException, Request


TRUSTED_PROXY_NETWORKS = tuple(
    ipaddress.ip_network(value.strip())
    for value in os.environ.get("TRUSTED_PROXY_NETWORKS", "").split(",")
    if value.strip()
)

def client_key(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"

    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        address = None

    if address is not None and any(
        address in network for network in TRUSTED_PROXY_NETWORKS
    ):
        forwarded = request.headers.get("x-transfer-client-ip")

        if forwarded is not None:
            try:
                address = ipaddress.ip_address(forwarded)
            except ValueError as error:
                raise HTTPException(
                    400,
                    "Invalid client address.",
                ) from error

    identity = str(address) if address is not None else peer

    return hashlib.sha256(identity.encode("utf-8")).hexdigest()