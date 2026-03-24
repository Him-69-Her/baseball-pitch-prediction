# Tiny-Hub Network — L2 Arbitrum Sepolia Migration

## What Changed

### New Contracts
- **TinyHubMarketV3.sol** — replaces V2 with on-chain idempotency (`settledMessages` mapping), `onlySettler` access control, pausable, and atomic `settleTrade()` / `settleBridge()` that combines list+purchase into 1 tx (saves gas on L2)
- **TinyHubTokenL2.sol** — replaces V1 with multi-minter pattern (`onlyMinter` instead of single `onlyBridge`)

### New Scripts
- **deploy_l2.js** — deploys both contracts to Arbitrum Sepolia, wires settler/minter roles, saves `deployment_l2.json`
- **d91_settler_l2.py** — dual-mode settler (`NETWORK=local` or `NETWORK=l2`), signed txs on L2, Secret Manager key loading
- **d91_bridge_l2.py** — dual-mode bridge, same pattern
- **start_l2.sh** — launch script with `./start_l2.sh` (L2) or `./start_l2.sh local` (Hardhat)

### Updated Config
- **hardhat.config.js** — optimizer enabled (200 runs), Arbiscan verification config
- **.github/workflows/ci-cd.yml** — L2 compile check + deploy job with GitHub environment secrets
- **.env.example** — all required env vars documented

---

## Deploy Steps

### 1. Generate a deployer wallet
```bash
# Create a new wallet (save the private key securely)
node -e "const w = require('ethers').Wallet.createRandom(); console.log('Address:', w.address); console.log('Key:', w.privateKey)"
```

### 2. Fund with test ETH
Go to https://faucet.quicknode.com/arbitrum/sepolia and request ETH for your deployer address.

### 3. Store the private key
```bash
# Option A: GCP Secret Manager (recommended)
echo -n "0xYOUR_KEY" | gcloud secrets create SETTLER_PRIVATE_KEY --data-file=-
echo -n "0xYOUR_KEY" | gcloud secrets create DEPLOYER_PRIVATE_KEY --data-file=-

# Option B: Environment variable
export DEPLOYER_PRIVATE_KEY="0xYOUR_KEY"
export SETTLER_PRIVATE_KEY="0xYOUR_KEY"
```

### 4. Compile contracts
```bash
npx hardhat compile
```

### 5. Run tests
```bash
npx hardhat test test/TinyHubMarketV3.test.js
```

### 6. Deploy to Arbitrum Sepolia
```bash
npx hardhat run deploy_l2.js --network arbitrumSepolia
```

This creates `deployment_l2.json` with contract addresses.

### 7. Verify on Arbiscan (optional)
```bash
npx hardhat verify --network arbitrumSepolia <MarketV3_ADDRESS>
npx hardhat verify --network arbitrumSepolia <TokenL2_ADDRESS>
```

### 8. Copy deployment file to VM
```bash
scp deployment_l2.json your-user@35.209.110.230:~/tiny-hub/
```

### 9. Start services in L2 mode
```bash
ssh your-user@35.209.110.230
cd ~/tiny-hub
chmod +x start_l2.sh
./start_l2.sh        # L2 mode
# or
./start_l2.sh local  # Hardhat mode (backward compat)
```

---

## GitHub Secrets Needed

Add these to your repo → Settings → Environments → `arbitrum-sepolia`:

| Secret | Value |
|--------|-------|
| `DEPLOYER_PRIVATE_KEY` | Wallet private key with test ETH |
| `SETTLER_ADDRESS` | Wallet address for settler role |
| `ARBISCAN_API_KEY` | From arbiscan.io (for verification) |

---

## Architecture: Local vs L2

| Component | Local (Hardhat) | L2 (Arbitrum Sepolia) |
|-----------|----------------|----------------------|
| Chain | localhost:8545, chain 31337 | sepolia-rollup.arbitrum.io, chain 421614 |
| Contracts | MarketV3 + TokenL2 (same code) | MarketV3 + TokenL2 (same code) |
| Idempotency | Python `seen_ids` (fallback) | On-chain `settledMessages` mapping |
| Tx signing | Unsigned `send_transaction` | Signed with private key |
| Key source | Hardhat pre-funded accounts | GCP Secret Manager or env var |
| Gas | Free | ~$0.001 per settleTrade |
| Settlement | 2-step: list → purchase | 1-step: atomic `settleTrade()` |
| Batch mode | Optional (`BATCH_MODE=true`) | Default ON — 1 tx/hour |
| Deploy file | `deployment.json` | `deployment_l2.json` |

---

## Batch Settlement

The batch system aggregates trades per building per district, then flushes one `settleBatch()` transaction per hour instead of one `settleTrade()` per trade.

**How it works:**
1. `BatchAggregator` buffers incoming trades from Pub/Sub
2. Nets energy per building — if Station A has 3 trades (0.1, 0.2, 0.15 MWh), it becomes one entry: 0.45 MWh at the volume-weighted average price
3. Every hour (configurable via `BATCH_INTERVAL`), it calls `settleBatch()` on MarketV3 with all entries
4. The contract checks idempotency per-entry — duplicates are skipped (not reverted), so one bad entry doesn't kill the batch
5. Max 200 entries per batch (gas safety cap)

**Config:**
```bash
BATCH_MODE=true          # Enable batch (default on L2)
BATCH_INTERVAL=3600      # Flush every 3600 seconds (1 hour)
```

**Why it matters:** At ~300 trades/hour, per-trade settlement burns 300 txs × ~$0.001 = $0.30/hour. Batch settlement compresses that to 1 tx with ~50-100 netted entries, saving ~99% on gas.

---

## Next: Chainlink Functions

With L2 live, the next step is Chainlink Functions for on-chain MISO/PJM price verification. This will:
1. Call MISO API from a Chainlink Function
2. Return the real LMP price on-chain
3. MarketV3 can validate that `settled_price` is within tolerance of the oracle price
4. Prevents fraud: settlers can't fabricate prices

Requires: Chainlink Functions subscription on Arbitrum Sepolia + a new `PriceOracle.sol` contract.
