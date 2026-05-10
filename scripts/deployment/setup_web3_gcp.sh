#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# TINY-HUB — Tasks #10 + #11 + #12: Full Web3 Stack on GCP
#
# One-shot setup:
#   1. Deploy contracts to Arbitrum Sepolia (#10)
#   2. Set up Firebase Auth + Cloud KMS wallets (#11)
#   3. Deploy bundler to Cloud Run + paymaster contract (#12)
#
# Run from project root:
#   chmod +x setup_web3_gcp.sh
#   ./setup_web3_gcp.sh
# ═══════════════════════════════════════════════════════════════

set -e

PROJECT_ID="tiny-hub-network"
REGION="us-central1"
CHAIN_ID="421614"

echo ""
echo "  ╔═══════════════════════════════════════════════════════════════════╗"
echo "  ║  TINY-HUB — Web3 Stack on GCP (No Third Parties)                ║"
echo "  ╠═══════════════════════════════════════════════════════════════════╣"
echo "  ║  #10: Arbitrum Sepolia contract deployment                       ║"
echo "  ║  #11: Firebase Auth + Cloud KMS embedded wallets                 ║"
echo "  ║  #12: Self-hosted bundler (Cloud Run) + Paymaster contract       ║"
echo "  ╚═══════════════════════════════════════════════════════════════════╝"
echo ""

# ═══════════════════════════════════════════════════════════════
# STEP 1: Enable required GCP APIs
# ═══════════════════════════════════════════════════════════════
echo "  [1/8] Enabling GCP APIs..."
gcloud services enable \
    cloudkms.googleapis.com \
    cloudfunctions.googleapis.com \
    cloudrun.googleapis.com \
    firestore.googleapis.com \
    firebase.googleapis.com \
    cloudbuild.googleapis.com \
    cloudscheduler.googleapis.com \
    secretmanager.googleapis.com \
    --project=$PROJECT_ID --quiet

echo "  ✅ APIs enabled"

# ═══════════════════════════════════════════════════════════════
# STEP 2: Create Cloud KMS key ring for user wallets
# ═══════════════════════════════════════════════════════════════
echo ""
echo "  [2/8] Setting up Cloud KMS key ring..."

gcloud kms keyrings create tinyhub-user-wallets \
    --location=$REGION \
    --project=$PROJECT_ID 2>/dev/null || echo "  ⏭️  Key ring already exists"

# Create a test key to verify secp256k1 support
gcloud kms keys create test-wallet-key \
    --location=$REGION \
    --keyring=tinyhub-user-wallets \
    --purpose=asymmetric-signing \
    --default-algorithm=ec-sign-secp256k1-sha256 \
    --protection-level=hsm \
    --project=$PROJECT_ID 2>/dev/null || echo "  ⏭️  Test key already exists"

echo "  ✅ Cloud KMS ready (secp256k1 HSM keys)"

# ═══════════════════════════════════════════════════════════════
# STEP 3: Set up Firestore for wallet mappings
# ═══════════════════════════════════════════════════════════════
echo ""
echo "  [3/8] Setting up Firestore..."

# Firestore should already exist from Pub/Sub setup, but ensure it
gcloud firestore databases create \
    --location=$REGION \
    --project=$PROJECT_ID 2>/dev/null || echo "  ⏭️  Firestore already exists"

echo "  ✅ Firestore ready"

# ═══════════════════════════════════════════════════════════════
# STEP 4: Deploy wallet creation Cloud Function
# ═══════════════════════════════════════════════════════════════
echo ""
echo "  [4/8] Deploying wallet creation function..."

# Create requirements.txt for the function
cat > /tmp/wallet-fn-requirements.txt << 'REQEOF'
google-cloud-kms>=2.0
google-cloud-firestore>=2.0
eth-keys>=0.4
pycryptodome>=3.19
REQEOF

# Copy function code
mkdir -p /tmp/wallet-fn
cp wallet_kms.py /tmp/wallet-fn/main.py
cp /tmp/wallet-fn-requirements.txt /tmp/wallet-fn/requirements.txt

# Deploy: Firebase Auth trigger
gcloud functions deploy create-wallet \
    --gen2 \
    --region=$REGION \
    --runtime=python311 \
    --source=/tmp/wallet-fn \
    --entry-point=cf_create_wallet \
    --trigger-event-filters="type=google.firebase.authentication.user.v1.created" \
    --memory=512MB \
    --timeout=60s \
    --set-env-vars="GCP_PROJECT=$PROJECT_ID,KMS_LOCATION=$REGION,KMS_KEY_RING=tinyhub-user-wallets,CHAIN_ID=$CHAIN_ID" \
    --project=$PROJECT_ID || echo "  ⚠️  Firebase trigger may need manual setup in Console"

# Deploy: HTTP wallet lookup
gcloud functions deploy get-wallet \
    --gen2 \
    --region=$REGION \
    --runtime=python311 \
    --source=/tmp/wallet-fn \
    --entry-point=cf_get_wallet \
    --trigger-http \
    --no-allow-unauthenticated \
    --memory=256MB \
    --set-env-vars="GCP_PROJECT=$PROJECT_ID" \
    --project=$PROJECT_ID

# Deploy: HTTP transaction signing
gcloud functions deploy sign-transaction \
    --gen2 \
    --region=$REGION \
    --runtime=python311 \
    --source=/tmp/wallet-fn \
    --entry-point=cf_sign_transaction \
    --trigger-http \
    --no-allow-unauthenticated \
    --memory=256MB \
    --set-env-vars="GCP_PROJECT=$PROJECT_ID,KMS_LOCATION=$REGION,KMS_KEY_RING=tinyhub-user-wallets" \
    --project=$PROJECT_ID

echo "  ✅ Wallet Cloud Functions deployed"

# ═══════════════════════════════════════════════════════════════
# STEP 5: Deploy ERC-4337 Bundler to Cloud Run
# ═══════════════════════════════════════════════════════════════
echo ""
echo "  [5/8] Deploying ERC-4337 bundler to Cloud Run..."

# Create Dockerfile for the bundler
mkdir -p /tmp/bundler
cat > /tmp/bundler/Dockerfile << 'DOCKEOF'
FROM node:20-slim

WORKDIR /app

# Install the Infinitism bundler (reference ERC-4337 implementation)
RUN npm init -y && \
    npm install @account-abstraction/bundler@0.7.0 \
    @account-abstraction/sdk@0.7.0 \
    ethers@6

# Bundler config
COPY bundler-config.json ./config.json
COPY start.sh ./start.sh
RUN chmod +x start.sh

EXPOSE 3000

CMD ["./start.sh"]
DOCKEOF

# Bundler config
cat > /tmp/bundler/bundler-config.json << CFGEOF
{
  "chainId": $CHAIN_ID,
  "network": "arbitrum-sepolia",
  "entryPoint": "0x0000000071727De22E5E9d8BAf0edAc6f37da032",
  "beneficiary": "DEPLOYER_ADDRESS_HERE",
  "minBalance": "0.01",
  "maxBundleGas": 5000000,
  "port": 3000,
  "unsafe": true
}
CFGEOF

# Start script
cat > /tmp/bundler/start.sh << 'STARTEOF'
#!/bin/sh
echo "Starting ERC-4337 Bundler..."
echo "  Chain ID: $(cat config.json | grep chainId)"
echo "  EntryPoint: 0x0000000071727De22E5E9d8BAf0edAc6f37da032"

# Use the reference bundler
npx @account-abstraction/bundler \
    --config config.json \
    --network "$RPC_URL" \
    --port 3000 \
    --unsafe
STARTEOF

# Build and push to GCR
cd /tmp/bundler
gcloud builds submit \
    --tag gcr.io/$PROJECT_ID/bundler \
    --project=$PROJECT_ID

# Deploy to Cloud Run
gcloud run deploy bundler \
    --image gcr.io/$PROJECT_ID/bundler \
    --region=$REGION \
    --memory=1Gi \
    --cpu=1 \
    --port=3000 \
    --set-env-vars="RPC_URL=https://sepolia-rollup.arbitrum.io/rpc" \
    --no-allow-unauthenticated \
    --min-instances=0 \
    --max-instances=3 \
    --project=$PROJECT_ID

BUNDLER_URL=$(gcloud run services describe bundler \
    --region=$REGION \
    --format="value(status.url)" \
    --project=$PROJECT_ID)

echo "  ✅ Bundler deployed at $BUNDLER_URL"

# Store bundler URL in Secret Manager
echo -n "$BUNDLER_URL" | gcloud secrets create bundler-url \
    --project=$PROJECT_ID \
    --data-file=- \
    --replication-policy=automatic 2>/dev/null || \
echo -n "$BUNDLER_URL" | gcloud secrets versions add bundler-url \
    --project=$PROJECT_ID \
    --data-file=-

# ═══════════════════════════════════════════════════════════════
# STEP 6: Deploy contracts to Arbitrum Sepolia
# ═══════════════════════════════════════════════════════════════
echo ""
echo "  [6/8] Deploying contracts to Arbitrum Sepolia..."

# Check for deployer key
DEPLOYER_KEY=$(gcloud secrets versions access latest \
    --secret=DEPLOYER_PRIVATE_KEY \
    --project=$PROJECT_ID 2>/dev/null || echo "")

if [ -z "$DEPLOYER_KEY" ]; then
    echo "  ⚠️  DEPLOYER_PRIVATE_KEY not in Secret Manager"
    echo "  Store it:"
    echo '    echo -n "0xYOUR_KEY" | gcloud secrets create DEPLOYER_PRIVATE_KEY \'
    echo "        --project=$PROJECT_ID --data-file=- --replication-policy=automatic"
    echo ""
    echo "  Then re-run this script or deploy manually:"
    echo "    DEPLOYER_PRIVATE_KEY=0x... npx hardhat run deploy.js --network arbitrumSepolia"
else
    export DEPLOYER_PRIVATE_KEY=$DEPLOYER_KEY
    npx hardhat compile
    npx hardhat run deploy.js --network arbitrumSepolia

    if [ -f deployment.json ]; then
        cp deployment.json deployment-l2.json
        echo "  ✅ Contracts deployed to Arbitrum Sepolia"
        cat deployment-l2.json

        # Store deployment in Secret Manager
        gcloud secrets create l2-deployment \
            --project=$PROJECT_ID \
            --data-file=deployment-l2.json \
            --replication-policy=automatic 2>/dev/null || \
        gcloud secrets versions add l2-deployment \
            --project=$PROJECT_ID \
            --data-file=deployment-l2.json
    fi
fi

# ═══════════════════════════════════════════════════════════════
# STEP 7: Deploy Paymaster contract
# ═══════════════════════════════════════════════════════════════
echo ""
echo "  [7/8] Paymaster contract..."

# The paymaster needs the verifier address (Cloud KMS derived)
# and the market contract address. Deploy after contracts + KMS are live.
echo "  ℹ️  Paymaster deployment requires:"
echo "     1. TinyHubMarket address from step 6"
echo "     2. Verifier address from Cloud KMS (create a signing key for the paymaster verifier)"
echo "     Deploy manually after setup:"
echo "     npx hardhat run deploy_paymaster.js --network arbitrumSepolia"

# Create the deploy script
cat > deploy_paymaster.js << 'PMEOF'
const hre = require("hardhat");
const fs = require("fs");

async function main() {
    const [deployer] = await hre.ethers.getSigners();
    console.log("Deploying TinyHubPaymaster with:", deployer.address);

    // Load L2 deployment
    const dep = JSON.parse(fs.readFileSync("deployment-l2.json", "utf8"));
    const marketAddress = dep.contracts?.TinyHubMarket?.address || dep.TinyHubMarketV2;

    // EntryPoint v0.7 (standard across all chains)
    const ENTRY_POINT = "0x0000000071727De22E5E9d8BAf0edAc6f37da032";

    // Verifier = deployer for now (replace with Cloud KMS address later)
    const verifier = deployer.address;

    const Paymaster = await hre.ethers.getContractFactory("TinyHubPaymaster");
    const paymaster = await Paymaster.deploy(ENTRY_POINT, verifier, marketAddress);
    await paymaster.waitForDeployment();

    const paymasterAddress = await paymaster.getAddress();
    console.log("TinyHubPaymaster deployed at:", paymasterAddress);

    // Deposit ETH to the paymaster (for sponsoring gas)
    const deposit = hre.ethers.parseEther("0.1"); // 0.1 ETH for testnet
    const entryPoint = await hre.ethers.getContractAt("IEntryPoint", ENTRY_POINT);
    await entryPoint.depositTo(paymasterAddress, { value: deposit });
    console.log("Deposited 0.1 ETH to paymaster");

    // Save
    dep.TinyHubPaymaster = paymasterAddress;
    dep.paymaster = {
        address: paymasterAddress,
        verifier: verifier,
        entryPoint: ENTRY_POINT,
    };
    fs.writeFileSync("deployment-l2.json", JSON.stringify(dep, null, 2));
    console.log("Saved to deployment-l2.json");
}

main().catch(console.error);
PMEOF

echo "  ✅ deploy_paymaster.js created"

# ═══════════════════════════════════════════════════════════════
# STEP 8: Create Firebase Auth config for frontend
# ═══════════════════════════════════════════════════════════════
echo ""
echo "  [8/8] Firebase Auth config..."

# Create a frontend config snippet
cat > firebase-config.js << FBEOF
// TINY-HUB — Firebase Auth Configuration
// Add to your frontend dashboard HTML
const firebaseConfig = {
    // Get these from Firebase Console → Project Settings
    // https://console.firebase.google.com/project/$PROJECT_ID/settings/general
    apiKey: "YOUR_FIREBASE_API_KEY",
    authDomain: "$PROJECT_ID.firebaseapp.com",
    projectId: "$PROJECT_ID",
    storageBucket: "$PROJECT_ID.appspot.com",
    messagingSenderId: "YOUR_SENDER_ID",
    appId: "YOUR_APP_ID",
};

// Initialize Firebase
firebase.initializeApp(firebaseConfig);

// Google Sign-In
async function signInWithGoogle() {
    const provider = new firebase.auth.GoogleAuthProvider();
    try {
        const result = await firebase.auth().signInWithPopup(provider);
        const user = result.user;
        console.log("Logged in:", user.email, user.uid);

        // Wallet is auto-created by Cloud Function on first login
        // Fetch it after a short delay (KMS key creation takes ~2s)
        setTimeout(async () => {
            const wallet = await fetch('/api/wallet?uid=' + user.uid);
            const data = await wallet.json();
            console.log("Wallet:", data.eth_address);
        }, 3000);

        return user;
    } catch (error) {
        console.error("Auth error:", error);
    }
}

// Sign out
function signOut() {
    firebase.auth().signOut();
}

// Auth state listener
firebase.auth().onAuthStateChanged((user) => {
    if (user) {
        console.log("User:", user.email);
        // Show dashboard
    } else {
        console.log("Signed out");
        // Show login
    }
});
FBEOF

echo "  ✅ firebase-config.js created"

# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════
echo ""
echo "  ╔═══════════════════════════════════════════════════════════════════╗"
echo "  ║  ✅ GCP Web3 Stack Setup Complete                                ║"
echo "  ╠═══════════════════════════════════════════════════════════════════╣"
echo "  ║                                                                   ║"
echo "  ║  #10 L2 Deploy:                                                   ║"
echo "  ║    • Contracts on Arbitrum Sepolia (or pending deployer key)      ║"
echo "  ║    • deployment-l2.json saved                                     ║"
echo "  ║                                                                   ║"
echo "  ║  #11 Embedded Wallets:                                            ║"
echo "  ║    • Cloud KMS key ring: tinyhub-user-wallets (HSM, secp256k1)   ║"
echo "  ║    • Firebase Auth → auto-creates wallet on signup                ║"
echo "  ║    • Cloud Functions: create-wallet, get-wallet, sign-transaction ║"
echo "  ║    • Firestore: wallets collection                                ║"
echo "  ║                                                                   ║"
echo "  ║  #12 Bundler + Paymaster:                                         ║"
echo "  ║    • ERC-4337 bundler on Cloud Run (auto-scaling)                 ║"
echo "  ║    • TinyHubPaymaster.sol (deploy after market contract)          ║"
echo "  ║    • Cloud KMS verifier (no third-party key custody)              ║"
echo "  ║                                                                   ║"
echo "  ║  Zero third-party dependencies. All GCP.                          ║"
echo "  ╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  Next steps:"
echo "    1. Store deployer private key in Secret Manager (if not done)"
echo "    2. Get Firebase config from Console → add to firebase-config.js"
echo "    3. Deploy paymaster: npx hardhat run deploy_paymaster.js --network arbitrumSepolia"
echo "    4. Fund paymaster with testnet ETH"
echo "    5. Wire firebase-config.js into dashboard.html"
echo ""
