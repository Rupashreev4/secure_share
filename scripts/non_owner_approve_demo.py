"""Demo: a non-owner tries to approve an access request (Anvil running, contract deployed).

    python scripts/non_owner_approve_demo.py

Alice registers a file and Bob requests access. Mallory, who does not own the
file, tries to approve Bob, first straight at the contract and then through
the application. Both are refused and Bob's request stays Pending. Then Alice
approves and the status changes to Approved.
"""
import os
import sys

from app import workflow as wf
from app.blockchain.contract_client import FileSharingContractClient
from app.crypto.keystore import get_public_info, load_signing_key

client = FileSharingContractClient()  # also loads .env
PASS = {
    name: os.getenv(f"{name.upper()}_PASSPHRASE", f"{name}-demo-pass")
    for name in ("alice", "bob", "mallory")
}


def status_of(file_id, address):
    return wf.STATUS_NAMES.get(client.get_status(file_id, address), "?")


def must(result, label):
    if not result.ok:
        sys.exit(f"[ABORT] {label} failed: {result.error}")
    return result


alice = get_public_info("alice")["address"]
bob = get_public_info("bob")["address"]
mallory = get_public_info("mallory")["address"]
print(f"Owner (alice)   : {alice}")
print(f"Requester (bob) : {bob}")
print(f"Attacker (mallory, not the owner): {mallory}")

print("\n1. Alice registers a file and Bob requests access")
created = must(
    wf.protect_and_register(client, "alice", PASS["alice"], b"non-owner demo file"),
    "Alice register",
)
file_id = created.data["file_id"]
must(wf.request_access(client, "bob", PASS["bob"], file_id), "Bob request")
print(f"   file id: 0x{file_id.hex()}")
print(f"   Bob's request status: {status_of(file_id, bob)}")

print("\n2. Mallory sends approveRequest straight to the contract")
mallory_key = load_signing_key("mallory", PASS["mallory"])
try:
    client.approve_request(file_id, bob, b"\x01" * 92, private_key=mallory_key)
    print("   [FAIL] The contract accepted the approval")
except Exception as exc:
    text = " ".join(str(exc).split())
    print(f"   [REFUSED] Contract reverted: {text[:140]}")
print(f"   Bob's request status is still: {status_of(file_id, bob)}")

print("\n3. Mallory tries the same through the application workflow")
attempt = wf.approve(client, "mallory", PASS["mallory"], file_id, bob)
failed = attempt.steps[-1].name if attempt.steps else "?"
print(f"   [REFUSED] stopped at '{failed}': {attempt.error}")
print(f"   Bob's request status is still: {status_of(file_id, bob)}")

print("\n4. Alice, the real owner, approves")
must(wf.approve(client, "alice", PASS["alice"], file_id, bob), "Alice approve")
print(f"   Bob's request status: {status_of(file_id, bob)}")