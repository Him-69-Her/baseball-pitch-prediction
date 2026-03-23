"""Chain status API — connects to Hardhat node for on-chain stats."""
import os
import json
from flask import jsonify

RPC_URL = os.environ.get("RPC_URL", "http://hardhat:8545")

def register_chain_routes(app):
    @app.route("/api/chain")
    def api_chain():
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 3}))
            if not w3.is_connected():
                return jsonify({"connected": False, "error": "Cannot reach Hardhat"})

            result = {
                "connected": True,
                "chain_id": w3.eth.chain_id,
                "block": w3.eth.block_number,
            }

            # Find deployment.json — check shared volume first, then local
            dep = None
            for path in ["/shared/deployment.json", "/app/deployment.json", "deployment.json"]:
                if os.path.exists(path):
                    with open(path) as f:
                        dep = json.load(f)
                    break

            if not dep:
                result["error"] = "deployment.json not found"
                return jsonify(result)

            # Handle both formats:
            # deploy.js format:    dep["contracts"]["TinyHubMarket"]["address"]
            # deploy_v2.js format: dep["TinyHubMarketV2"]
            contract_addr = None
            token_addr = None

            if "contracts" in dep:
                # deploy.js format
                if "TinyHubMarket" in dep["contracts"]:
                    contract_addr = dep["contracts"]["TinyHubMarket"]["address"]
                if "TinyHubToken" in dep["contracts"]:
                    token_addr = dep["contracts"]["TinyHubToken"]["address"]
            else:
                # deploy_v2.js format
                contract_addr = dep.get("TinyHubMarketV2")
                token_addr = dep.get("TinyHubToken")

            if contract_addr:
                abi = [{"inputs":[],"name":"tradeCount","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"}]
                try:
                    c = w3.eth.contract(address=contract_addr, abi=abi)
                    result["trade_count"] = c.functions.tradeCount().call()
                    result["contract"] = contract_addr
                except Exception as e:
                    result["contract_error"] = str(e)[:80]

            if token_addr:
                tabi = [
                    {"inputs":[],"name":"totalSupply","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},
                    {"inputs":[],"name":"symbol","outputs":[{"type":"string"}],"stateMutability":"view","type":"function"},
                ]
                try:
                    t = w3.eth.contract(address=token_addr, abi=tabi)
                    raw = t.functions.totalSupply().call()
                    result["token_supply"] = float(w3.from_wei(raw, "ether"))
                    result["token_symbol"] = t.functions.symbol().call()
                    result["token"] = token_addr
                except Exception as e:
                    result["token_error"] = str(e)[:80]

            return jsonify(result)
        except Exception as e:
            return jsonify({"connected": False, "error": str(e)[:100]})
