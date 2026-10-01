"""Versioned, integrity-protected transport envelope for the local bridge.

Integrity uses HMAC-SHA256 with externally supplied key material. No key is stored here.
This authenticates transport messages; it does not authorize live execution.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from hashlib import sha256
import hmac
import json

from platform_domain.bridge_protocol import BridgeRequest

BRIDGE_ENVELOPE_SCHEMA = "1"

@dataclass(frozen=True)
class SignedBridgeEnvelope:
    schema_version: str
    request: BridgeRequest
    signature: str

    def validate(self) -> None:
        if self.schema_version != BRIDGE_ENVELOPE_SCHEMA:
            raise ValueError("unsupported bridge envelope schema")
        if not isinstance(self.request, BridgeRequest):
            raise ValueError("request must be BridgeRequest")
        self.request.validate()
        if type(self.signature) is not str or len(self.signature) != 64 or any(
            char not in "0123456789abcdef" for char in self.signature
        ):
            raise ValueError("signature must be lowercase HMAC-SHA256")

def canonical_bridge_request(request: BridgeRequest) -> bytes:
    if not isinstance(request, BridgeRequest):
        raise ValueError("request must be BridgeRequest")
    request.validate()
    payload = asdict(request)
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")

def sign_bridge_request(request: BridgeRequest, *, key: bytes) -> SignedBridgeEnvelope:
    if type(key) is not bytes or len(key) < 32:
        raise ValueError("bridge signing key must contain at least 32 bytes")
    signature = hmac.new(key, canonical_bridge_request(request), sha256).hexdigest()
    return SignedBridgeEnvelope(BRIDGE_ENVELOPE_SCHEMA, request, signature)

def verify_bridge_envelope(envelope: SignedBridgeEnvelope, *, key: bytes) -> bool:
    if type(key) is not bytes or len(key) < 32 or not isinstance(envelope, SignedBridgeEnvelope):
        return False
    try:
        envelope.validate()
        expected = hmac.new(
            key, canonical_bridge_request(envelope.request), sha256
        ).hexdigest()
    except (TypeError, ValueError, OverflowError):
        return False
    return hmac.compare_digest(envelope.signature, expected)
