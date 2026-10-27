"""SecureShare GUI (Member 4: Frontend Integrator).

Run from the project root, with Anvil running and the contract deployed:

    streamlit run app/gui/streamlit_app.py

Design rule: this file contains NO cryptography and NO blockchain logic.
Every button calls a function in app/workflow.py, which returns a Result
(ok, steps, data, error). The GUI only collects input and shows each step.

The only direct reads are public, read-only values: the list of demo users,
a user's public address, and the current request status on the chain.
"""
import hashlib
import re

import streamlit as st

from app import workflow as wf
from app.blockchain.contract_client import FileSharingContractClient
from app.config import KEYSTORE_DIR
from app.crypto.keystore import get_public_info

HEX64 = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")

st.set_page_config(page_title="SecureShare", page_icon="🔐", layout="wide")


# ---------------------------------------------------------------------------
# Connection and small helpers
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_client():
    """One shared blockchain client. Transactions are signed per call with the
    chosen user's key, so nothing user-specific is stored on the client."""
    return FileSharingContractClient()


def connect():
    """Return a working client, or stop the page with a clear instruction."""
    try:
        client = get_client()
    except Exception as exc:
        st.error(f"Could not load the contract settings: {exc}")
        st.info(
            "In a terminal run `python scripts/export_contract_data.py` and "
            "`python scripts/deploy_contract.py` (Anvil must be running), "
            "then reload this page."
        )
        st.stop()

    if not client.is_connected():
        st.error(f"Cannot reach the blockchain at {client.rpc_url}.")
        st.info("Start Anvil in another terminal, deploy the contract, then reload.")
        st.stop()

    if client.get_contract_address() is None:
        st.error("The contract has no deployed address yet.")
        st.info(
            "Run `python scripts/deploy_contract.py` and make sure "
            "CONTRACT_DATA_FILE in .env points to the local data file."
        )
        st.stop()
    return client


def demo_users():
    if not KEYSTORE_DIR.exists():
        return []
    return sorted(p.stem for p in KEYSTORE_DIR.glob("*.json"))


def parse_file_id(text):
    """Turn 64 hex characters into 32 bytes, or None with a clear warning."""
    text = (text or "").strip()
    if not text:
        return None
    if not HEX64.match(text):
        st.warning("A file id is exactly 64 hexadecimal characters.")
        return None
    return bytes.fromhex(text[2:] if text.lower().startswith("0x") else text)


def fmt_value(value):
    """Readable form of an event argument for the audit table."""
    if isinstance(value, (bytes, bytearray)):
        text = "0x" + bytes(value).hex()
    else:
        text = str(value)
    return text if len(text) <= 22 else text[:20] + "…"


def sha256_hex(data):
    """Display-only digest so owner and requester can compare the file."""
    return hashlib.sha256(data).hexdigest()


def describe_file(data):
    """Guess the file type from its first bytes.

    Returns (extension, mime type, text or None). The system stores no file
    name, so the requester needs the right extension to open the file.
    """
    if data.startswith(b"%PDF"):
        return ".pdf", "application/pdf", None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png", None
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg", None
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif", "image/gif", None
    if data.startswith(b"PK\x03\x04"):
        if b"word/document.xml" in data:
            return ".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", None
        if b"xl/workbook.xml" in data:
            return ".xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", None
        if b"ppt/presentation.xml" in data:
            return ".pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", None
        return ".zip", "application/zip", None
    for encoding in ("utf-8-sig", "utf-16"):
        if encoding == "utf-16" and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
            continue
        try:
            return ".txt", "text/plain", data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return ".bin", "application/octet-stream", None


# ---------------------------------------------------------------------------
# Running a workflow and showing every step
# ---------------------------------------------------------------------------
def run(label, fn, *args):
    """Call a workflow, remember the result, and rerun so every list on the
    page reflects the new chain state. The result is shown at the top."""
    with st.spinner(f"{label}..."):
        result = fn(*args)
    st.session_state.setdefault("activity", []).insert(
        0, (label, result.ok, result.error)
    )
    st.session_state["flash"] = (label, result)
    st.rerun()


def show_result(label, result):
    state = "complete" if result.ok else "error"
    title = f"{label}: done" if result.ok else f"{label}: failed"
    with st.status(title, expanded=True, state=state):
        for step in result.steps:
            icon = "✅" if step.ok else "❌"
            st.write(f"{icon} **{step.name}** – {step.detail}")
    if not result.ok:
        st.error(result.error)
        return

    file_id = result.data.get("file_id")
    if file_id:
        st.success("File protected and registered. Give this file id to the requester:")
        st.code(file_id.hex(), language=None)

    if "plaintext" in result.data:
        st.session_state["decrypted"] = result.data["plaintext"]


# ---------------------------------------------------------------------------
# Sidebar: who is logged in, connection details, recent activity
# ---------------------------------------------------------------------------
def sidebar(client):
    st.sidebar.title("SecureShare")
    users = demo_users()
    if not users:
        st.sidebar.error("No users found. Run scripts/deploy_contract.py first.")
        st.stop()

    user = st.sidebar.selectbox("Log in as", users)
    passphrase = st.sidebar.text_input(
        "Passphrase", type="password", key=f"pw_{user}"
    )
    address = get_public_info(user)["address"]
    st.sidebar.caption(f"Address: {address}")

    with st.sidebar.expander("Blockchain connection", expanded=False):
        try:
            st.write(f"Chain id: {client.get_chain_id()}")
        except Exception as exc:
            st.write(f"Chain check failed: {exc}")
        st.write(f"Contract: {client.get_contract_address()}")
        if st.button("Reload contract settings"):
            st.cache_resource.clear()
            st.rerun()

    with st.sidebar.expander("Recent activity", expanded=False):
        activity = st.session_state.get("activity", [])
        if not activity:
            st.caption("Nothing yet.")
        for label, ok, error in activity[:8]:
            st.write(("✅ " if ok else "❌ ") + label + ("" if ok else f" ({error})"))

    return user, passphrase, address


# ---------------------------------------------------------------------------
# Owner page
# ---------------------------------------------------------------------------
def owner_page(client, user, passphrase):
    ready = bool(passphrase)
    if not ready:
        st.info("Enter your passphrase in the sidebar to enable actions.")

    st.subheader("Protect and register a file")
    st.caption(
        "The file is encrypted on this computer with a new random key. "
        "Only ciphertext goes to storage; the chain records hashes, addresses "
        "and your signature."
    )
    upload = st.file_uploader("Choose a file", key="owner_upload")
    if upload:
        original = upload.getvalue()
        st.caption(
            f"{upload.name}: {len(original)} bytes, SHA-256 {sha256_hex(original)}. "
            "The requester's decrypted file must show the same digest."
        )
    if st.button(
        "Encrypt, sign and register",
        type="primary",
        disabled=not (ready and upload),
    ):
        run(
            "Encrypt, sign and register",
            wf.protect_and_register,
            client,
            user,
            passphrase,
            upload.getvalue(),
        )

    st.divider()
    st.subheader("My files and access requests")
    files = wf.list_my_files(client, user)
    if not files.ok:
        st.error(files.error)
        return
    file_ids = list(reversed(files.data["files"]))
    if not file_ids:
        st.info("No files yet. Protect a file above and it will appear here.")
        return

    for file_id in file_ids:
        with st.expander(f"File {file_id.hex()[:16]}…", expanded=len(file_ids) == 1):
            st.caption("File id (share this with requesters):")
            st.code(file_id.hex(), language=None)

            requests = wf.list_requests(client, file_id)
            if not requests.ok:
                st.error(requests.error)
                continue

            # One row per requester: the contract allows one request each.
            latest = {r["requester"]: r for r in requests.data["requests"]}
            if not latest:
                st.caption("No access requests yet.")

            for req in latest.values():
                key = f"{file_id.hex()}-{req['requester']}"
                left, middle, right = st.columns([3, 2, 1])
                left.write(f"Requester: `{req['requester']}`")
                middle.write(f"Key fingerprint: `{req['fingerprint']}`")
                right.write(f"**{req['status']}**")

                if req["status"] == "Pending":
                    verified = st.checkbox(
                        "I checked this fingerprint with the requester",
                        key=f"chk-{key}",
                    )
                    approve_col, reject_col = st.columns(2)
                    if approve_col.button(
                        "Approve and share key",
                        key=f"ap-{key}",
                        type="primary",
                        disabled=not (ready and verified),
                    ):
                        run(
                            "Approve request",
                            wf.approve,
                            client,
                            user,
                            passphrase,
                            file_id,
                            req["requester"],
                        )
                    if reject_col.button(
                        "Reject", key=f"rj-{key}", disabled=not ready
                    ):
                        run(
                            "Reject request",
                            wf.reject,
                            client,
                            user,
                            passphrase,
                            file_id,
                            req["requester"],
                        )
                elif req["status"] == "Approved":
                    if st.button(
                        "Revoke access", key=f"rv-{key}", disabled=not ready
                    ):
                        run(
                            "Revoke access",
                            wf.revoke,
                            client,
                            user,
                            passphrase,
                            file_id,
                            req["requester"],
                        )

            st.markdown("**Attack demo: tamper with the stored ciphertext**")
            st.caption(
                "Simulates a malicious storage provider changing one bit. "
                "The requester's verification should then fail."
            )
            if st.button("Tamper with stored file", key=f"tp-{file_id.hex()}"):
                run("Tamper with stored file", wf.demo_tamper, client, file_id)


# ---------------------------------------------------------------------------
# Requester page
# ---------------------------------------------------------------------------
def requester_page(client, user, passphrase, address):
    ready = bool(passphrase)
    if not ready:
        st.info("Enter your passphrase in the sidebar to enable actions.")

    st.subheader("Request access to a file")
    file_id = parse_file_id(st.text_input("File id (64 hex characters)"))

    status = None
    if file_id is not None:
        try:
            status = wf.STATUS_NAMES.get(client.get_status(file_id, address), "?")
        except Exception as exc:
            st.error(f"Could not read the status: {exc}")
        if status is not None:
            st.metric("Your request status", status)
            if status == "Rejected" or status == "Revoked":
                st.caption("The contract allows one request per user per file.")

    request_col, decrypt_col = st.columns(2)
    if request_col.button(
        "Request access",
        type="primary",
        disabled=not (ready and file_id is not None and status == "None"),
    ):
        run("Request access", wf.request_access, client, user, passphrase, file_id)

    if decrypt_col.button(
        "Fetch, verify and decrypt",
        disabled=not (ready and file_id is not None),
    ):
        st.session_state.pop("decrypted", None)
        run(
            "Fetch, verify and decrypt",
            wf.fetch_verify_decrypt,
            client,
            user,
            passphrase,
            file_id,
        )

    plaintext = st.session_state.get("decrypted")
    if plaintext is not None:
        extension, mime, text = describe_file(plaintext)
        digest = sha256_hex(plaintext)
        st.success("The file was verified and decrypted.")
        st.caption(
            f"{len(plaintext)} bytes, detected type {extension}, SHA-256 {digest}"
        )
        if text is not None and len(text) <= 2000:
            st.text_area("Preview", text, height=140)
        elif text is None:
            st.caption(
                "No text preview for this file type. Save it with the "
                "extension shown above and open it in the matching program."
            )
        name = st.text_input(
            "Save as",
            value=f"decrypted_file{extension}",
            key=f"saveas_{digest[:12]}",
            help="The system does not store file names. Use the original extension.",
        )
        st.download_button(
            "Download decrypted file", plaintext, file_name=name, mime=mime
        )
        if st.button("Clear decrypted data from this page"):
            st.session_state.pop("decrypted", None)
            st.rerun()

    st.divider()
    st.subheader("My requests")
    mine = wf.list_my_requests(client, user)
    if not mine.ok:
        st.error(mine.error)
    elif not mine.data["requests"]:
        st.caption("You have not requested any files yet.")
    else:
        st.dataframe(
            [
                {"File id": r["file_id"].hex(), "Status": r["status"]}
                for r in mine.data["requests"]
            ]
        )

    with st.expander("Security demo: try to approve someone else's file"):
        st.caption(
            "Any user can try the owner action. It must be refused: this user "
            "has no key for the file, and the contract only accepts the owner."
        )
        target = st.text_input("Requester address to approve", key="demo_target")
        if st.button(
            "Try to approve",
            disabled=not (ready and file_id is not None and target.strip()),
        ):
            run(
                "Unauthorised approval attempt",
                wf.approve,
                client,
                user,
                passphrase,
                file_id,
                target.strip(),
            )


# ---------------------------------------------------------------------------
# Audit log page
# ---------------------------------------------------------------------------
def audit_page(client):
    st.subheader("Audit log")
    st.caption(
        "Every registration, request, approval, rejection and revocation is an "
        "event on the chain. Wrapped keys are not shown here."
    )
    log = wf.get_audit_log(client)
    if not log.ok:
        st.error(log.error)
        return
    rows = []
    for event in log.data["events"]:
        tx = event["transaction_hash"]
        rows.append(
            {
                "Block": event["block_number"],
                "Event": event["event"],
                "Transaction": tx.hex() if hasattr(tx, "hex") else str(tx),
                "Details": ", ".join(
                    f"{k}={fmt_value(v)}" for k, v in event["args"].items()
                ),
            }
        )
    if rows:
        st.dataframe(rows)
    else:
        st.info("No events yet.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    client = connect()
    user, passphrase, address = sidebar(client)

    st.title("SecureShare")
    st.caption(f"Signed in as **{user}**")

    flash = st.session_state.pop("flash", None)
    if flash:
        show_result(*flash)

    owner_tab, requester_tab, audit_tab = st.tabs(
        ["Owner", "Requester", "Audit log"]
    )
    with owner_tab:
        owner_page(client, user, passphrase)
    with requester_tab:
        requester_page(client, user, passphrase, address)
    with audit_tab:
        audit_page(client)


main()