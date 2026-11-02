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

    # IPv4-mapped IPv6 must use the same bucket as the IPv4 address.
    if isinstance(address, ipaddress.IPv6Address):
        mapped = address.ipv4_mapped
        if mapped is not None:
            address = mapped

    # Privacy addresses within one IPv6 /64 share abuse and upload limits.
    # Keep existing IPv4 identities unchanged.
    identity = (
        str(ipaddress.IPv6Network((address, 64), strict=False))
        if isinstance(address, ipaddress.IPv6Address)
        else str(address) if address is not None else peer
    )

    return hashlib.sha256(identity.encode("utf-8")).hexdigest()