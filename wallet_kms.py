"""
TINY-HUB — Task #11: Embedded Wallets via Firebase Auth + Cloud KMS
===================================================================
Replaces Privy with native GCP services.

Flow:
  1. User clicks "Sign in with Google" on dashboard
  2. Firebase Auth handles OAuth → returns firebase_uid
  3. Cloud Function triggers on auth.user().onCreate()
  4. Cloud KMS creates secp256k1 signing key for this user
  5. Derives Ethereum address from public key
  6. Stores mapping in Firestore: uid → eth_address → kms_key
  7. User has a wallet — never sees a private key

Deploy:
  gcloud functions deploy create-wallet \\
      --gen2 --runtime python311 --trigger-event-filters="type=google.firebase.authentication.user.v1.created" \\
      --region us-central1 --project tinyhub-platform-dev

Also includes:
  - sign-transaction: Cloud Function to sign txs with user's KMS key
  - get-wallet: HTTP function to look up a user's wallet address
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timezone

# ── GCP imports ─────────────────────────────────────────────
from google.cloud import kms_v1, firestore
from google.protobuf import duration_pb2

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "tinyhub-data-dev")
LOCATION = os.environ.get("KMS_LOCATION", "us-central1")
KEY_RING_ID = os.environ.get("KMS_KEY_RING", "tinyhub-user-wallets")
CHAIN_ID = int(os.environ.get("CHAIN_ID", "421614"))  # Arbitrum Sepolia

# ── Clients ─────────────────────────────────────────────────
kms_client = kms_v1.KeyManagementServiceClient()
db = firestore.Client(project=PROJECT_ID)


def _ensure_key_ring():
    """Create the key ring if it doesn't exist."""
    key_ring_path = kms_client.key_ring_path(PROJECT_ID, LOCATION, KEY_RING_ID)
    try:
        kms_client.get_key_ring(request={"name": key_ring_path})
    except Exception:
        parent = f"projects/{PROJECT_ID}/locations/{LOCATION}"
        kms_client.create_key_ring(
            request={
                "parent": parent,
                "key_ring_id": KEY_RING_ID,
                "key_ring": {},
            }
        )
        logger.info(f"Created key ring: {KEY_RING_ID}")


def _derive_eth_address_from_pem(pem_key: str) -> str:
    """Derive Ethereum address from a PEM-encoded secp256k1 public key."""
    import base64
    
    # Strip PEM headers
    lines = pem_key.strip().split("\n")
    b64_data = "".join(l for l in lines if not l.startswith("-----"))
    der_bytes = base64.b64decode(b64_data)
    
    # secp256k1 uncompressed public key is the last 65 bytes of DER
    # (starts with 0x04 prefix for uncompressed)
    # The DER structure for EC public keys has the key at the end
    # Find the 0x04 byte followed by 64 bytes
    for i in range(len(der_bytes) - 65, -1, -1):
        if der_bytes[i] == 0x04:
            pub_bytes = der_bytes[i + 1: i + 65]  # 64 bytes (x, y)
            break
    else:
        raise ValueError("Could not find uncompressed public key in DER")
    
    # Ethereum address = last 20 bytes of keccak256(pub_x || pub_y)
    from Crypto.Hash import keccak
    k = keccak.new(digest_bits=256)
    k.update(pub_bytes)
    address = "0x" + k.hexdigest()[-40:]
    return address.lower()


def _derive_eth_address_simple(pem_key: str) -> str:
    """Fallback: derive ETH address using web3."""
    try:
        from eth_keys import keys
        import base64
        
        lines = pem_key.strip().split("\n")
        b64_data = "".join(l for l in lines if not l.startswith("-----"))
        der_bytes = base64.b64decode(b64_data)
        
        # Find the 65-byte uncompressed key (0x04 + 32 + 32)
        for i in range(len(der_bytes) - 65, -1, -1):
            if der_bytes[i] == 0x04:
                pub_bytes = der_bytes[i + 1: i + 65]
                break
        else:
            raise ValueError("Uncompressed key not found")
        
        pk = keys.PublicKey(pub_bytes)
        return pk.to_checksum_address().lower()
    except ImportError:
        return _derive_eth_address_from_pem(pem_key)


def create_wallet_for_user(uid: str, email: str = "") -> dict:
    """
    Create a Cloud KMS signing key and derive an Ethereum address.
    
    Returns:
        {"uid": "...", "eth_address": "0x...", "kms_key": "...", "created_at": "..."}
    """
    _ensure_key_ring()
    
    key_ring_path = kms_client.key_ring_path(PROJECT_ID, LOCATION, KEY_RING_ID)
    key_id = f"user-{uid}"
    
    # Check if wallet already exists
    doc = db.collection("wallets").document(uid).get()
    if doc.exists:
        return doc.to_dict()
    
    # Create asymmetric signing key (secp256k1)
    try:
        crypto_key = kms_client.create_crypto_key(
            request={
                "parent": key_ring_path,
                "crypto_key_id": key_id,
                "crypto_key": {
                    "purpose": kms_v1.CryptoKey.CryptoKeyPurpose.ASYMMETRIC_SIGN,
                    "version_template": {
                        "algorithm": kms_v1.CryptoKeyVersion.CryptoKeyVersionAlgorithm.EC_SIGN_SECP256K1_SHA256,
                        "protection_level": kms_v1.ProtectionLevel.HSM,
                    },
                },
            }
        )
        logger.info(f"Created KMS key: {key_id}")
    except Exception as e:
        if "ALREADY_EXISTS" in str(e):
            logger.info(f"KMS key already exists: {key_id}")
        else:
            raise
    
    # Get the public key
    key_version_path = kms_client.crypto_key_version_path(
        PROJECT_ID, LOCATION, KEY_RING_ID, key_id, "1"
    )
    
    # Wait for key to become active
    import time
    for _ in range(10):
        try:
            pub_key_response = kms_client.get_public_key(
                request={"name": key_version_path}
            )
            break
        except Exception:
            time.sleep(1)
    else:
        raise TimeoutError(f"KMS key {key_id} not ready after 10s")
    
    # Derive Ethereum address
    eth_address = _derive_eth_address_simple(pub_key_response.pem)
    
    # Store in Firestore
    wallet_data = {
        "uid": uid,
        "email": email,
        "eth_address": eth_address,
        "kms_key": key_version_path,
        "chain_id": CHAIN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.collection("wallets").document(uid).set(wallet_data)
    
    logger.info(f"Wallet created: {uid} → {eth_address}")
    return wallet_data


def sign_transaction_with_kms(uid: str, tx_hash: bytes) -> bytes:
    """
    Sign a transaction hash using the user's Cloud KMS key.
    
    Args:
        uid: Firebase user ID
        tx_hash: 32-byte hash to sign
    
    Returns:
        65-byte signature (r + s + v)
    """
    # Look up KMS key for this user
    doc = db.collection("wallets").document(uid).get()
    if not doc.exists:
        raise ValueError(f"No wallet found for user {uid}")
    
    kms_key_path = doc.to_dict()["kms_key"]
    
    # Sign with KMS
    import hashlib
    digest = {"sha256": tx_hash}
    
    response = kms_client.asymmetric_sign(
        request={
            "name": kms_key_path,
            "digest": digest,
        }
    )
    
    return response.signature


def get_wallet(uid: str) -> dict:
    """Look up a user's wallet address."""
    doc = db.collection("wallets").document(uid).get()
    if doc.exists:
        return doc.to_dict()
    return None


# ═══════════════════════════════════════════════════════════════
# Cloud Function Entry Points
# ═══════════════════════════════════════════════════════════════

def cf_create_wallet(cloud_event):
    """
    Cloud Functions gen 2 entry: Firebase Auth onCreate trigger.
    Automatically creates a wallet when a new user signs up.
    """
    try:
        # Firebase Auth event data
        uid = cloud_event.data.get("uid", "")
        email = cloud_event.data.get("email", "")
        
        if not uid:
            logger.error("No UID in auth event")
            return
        
        result = create_wallet_for_user(uid, email)
        logger.info(f"Auto-created wallet for {email}: {result['eth_address']}")
    except Exception as e:
        logger.error(f"Failed to create wallet: {e}")


def cf_get_wallet(request):
    """
    Cloud Functions gen 2 entry: HTTP trigger.
    GET /get-wallet?uid=<firebase_uid>
    """
    uid = request.args.get("uid", "")
    if not uid:
        return json.dumps({"error": "uid required"}), 400
    
    wallet = get_wallet(uid)
    if wallet:
        return json.dumps(wallet), 200
    return json.dumps({"error": "wallet not found"}), 404


def cf_sign_transaction(request):
    """
    Cloud Functions gen 2 entry: HTTP trigger.
    POST /sign-transaction
    Body: {"uid": "...", "tx_hash": "0x..."}
    
    Returns the KMS signature for constructing a UserOperation.
    """
    data = request.get_json(silent=True) or {}
    uid = data.get("uid", "")
    tx_hash_hex = data.get("tx_hash", "")
    
    if not uid or not tx_hash_hex:
        return json.dumps({"error": "uid and tx_hash required"}), 400
    
    try:
        tx_hash = bytes.fromhex(tx_hash_hex.replace("0x", ""))
        signature = sign_transaction_with_kms(uid, tx_hash)
        return json.dumps({
            "signature": "0x" + signature.hex(),
            "signer": get_wallet(uid)["eth_address"],
        }), 200
    except Exception as e:
        return json.dumps({"error": str(e)}), 500
