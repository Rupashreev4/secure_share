"""Pre-demo check: is the chain up, is the contract deployed, are the users funded?

    python scripts/check_ready.py

Run it before every demo and after every Anvil restart. It prints READY or says
exactly what to run next.
"""
import sys

from app.blockchain.contract_client import FileSharingContractClient
from app.crypto.keystore import get_public_info, user_exists

problems = []

try:
    client = FileSharingContractClient()
except Exception as exc:
    sys.exit(f"[NOT READY] Could not load the contract settings: {exc}\n"
             "Run: python scripts/export_contract_data.py, then python scripts/deploy_contract.py")

if not client.is_connected():
    sys.exit("[NOT READY] Cannot reach the blockchain. Start Anvil in another terminal: "
             "anvil")

web3 = client.web3
address = client.get_contract_address()
print(f"Blockchain reachable : yes (chain id {web3.eth.chain_id}, block {web3.eth.block_number})")
print(f"Contract address     : {address}")

code_size = len(web3.eth.get_code(address)) if address else 0
print(f"Contract code size   : {code_size} bytes")
if code_size == 0:
    problems.append("The contract is not on this chain (Anvil was restarted). "
                    "Run: python scripts/deploy_contract.py")

for name in ("alice", "bob", "mallory"):
    if not user_exists(name):
        print(f"{name:8} : no keystore")
        problems.append(f"User {name} is missing. Run: python scripts/deploy_contract.py")
        continue
    user_address = get_public_info(name)["address"]
    balance = web3.from_wei(web3.eth.get_balance(user_address), "ether")
    print(f"{name:8} : {user_address}  {balance} ETH")
    if balance == 0:
        problems.append(f"{name} has no ETH for transactions. "
                        "Run: python scripts/deploy_contract.py")

if problems:
    print("\n[NOT READY]")
    for item in dict.fromkeys(problems):
        print(" - " + item)
    print("Afterwards press 'Reload contract settings' in the GUI sidebar.")
    sys.exit(1)

print("\n[READY] Chain, contract and users are in place.")