"""Show the on-chain registration record of a file (Anvil running, contract deployed).

    python scripts/show_chain_record.py              # Alice's newest file
    python scripts/show_chain_record.py <file_id>    # a specific file id (64 hex characters)

It reads the record straight from the FileSharing contract, finds the
FileRegistered event and its transaction, and checks that the record matches
the stored ciphertext and the owner's signature.
"""
import sys
from datetime import datetime, timezone

from app.blockchain.contract_client import FileSharingContractClient
from app.crypto.file_crypto import ciphertext_hash
from app.crypto.keystore import list_files
from app.crypto.signing import verify_file
from app.storage.storage import StorageClient

client = FileSharingContractClient()

if len(sys.argv) > 1:
    text = sys.argv[1].strip().lower().removeprefix("0x")
    file_id = bytes.fromhex(text)
else:
    files = list_files("alice")
    if not files:
        sys.exit("Alice has no files yet. Register one in the GUI first.")
    file_id = files[-1]

owner, ct_hash, storage_id, signature, registered_at = client.get_file(file_id)
ct_hash, storage_id, signature = bytes(ct_hash), bytes(storage_id), bytes(signature)
when = datetime.fromtimestamp(registered_at, tz=timezone.utc).isoformat()

print("=== Record stored in the FileSharing contract (getFile)")
print(f"file id       : 0x{file_id.hex()}")
print(f"owner         : {owner}")
print(f"ctHash        : 0x{ct_hash.hex()}   (SHA-256 of the ciphertext)")
print(f"storage id    : 0x{storage_id.hex()}   (random name of the stored blob)")
print(f"signature     : 0x{signature.hex()[:40]}...  ({len(signature)} bytes)")
print(f"registered at : {when}")
print("Fields NOT stored on chain: plaintext, file name, file key.")

print("\n=== FileRegistered event and transaction")
events = client.get_events("FileRegistered", from_block=0, fileId=file_id)
if not events:
    print("No FileRegistered event found for this file id.")
else:
    event = events[0]
    tx_hash = event["transactionHash"]
    tx = client.web3.eth.get_transaction(tx_hash)
    receipt = client.web3.eth.get_transaction_receipt(tx_hash)
    print(f"transaction   : 0x{bytes(tx_hash).hex()}")
    print(f"block number  : {event['blockNumber']}")
    print(f"sent by       : {tx['from']}")
    print(f"to contract   : {tx['to']}")
    print(f"status        : {'success' if receipt['status'] == 1 else 'failed'}")
    print(f"calldata size : {len(bytes(tx['input']))} bytes (function selector + 3 hashes + signature)")

print("\n=== Checks")
blob = StorageClient().get(storage_id)
print(
    f"ciphertext hash matches ctHash : {ciphertext_hash(blob) == ct_hash}"
    f"   (blob is {len(blob)} bytes)"
)
valid = verify_file(
    owner,
    signature,
    client.get_chain_id(),
    client.get_contract_address(),
    file_id,
    ct_hash,
    storage_id,
)
print(f"owner signature recovers owner : {valid}")
print(
    "The contract ran the same ecrecover check inside registerFile; "
    "the transaction only succeeds if the signer equals the sender."
)