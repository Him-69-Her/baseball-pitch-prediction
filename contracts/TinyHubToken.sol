// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * TINY-HUB-NETWORK — Energy Token
 * 1 THN = 1 MWh of renewable energy
 *
 * The bridge mints tokens when energy is produced (seller lists).
 * Tokens transfer to the buyer when a trade settles.
 * ComEd toll is burned on each trade.
 */
contract TinyHubToken {
    string public name = "TinyHub Energy";
    string public symbol = "THN";
    uint8 public decimals = 18;
    uint256 public totalSupply;

    address public bridge;  // Only the bridge can mint/burn

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event Minted(address indexed to, uint256 mwh, string stationId);
    event Burned(address indexed from, uint256 amount, string reason);

    modifier onlyBridge() {
        require(msg.sender == bridge, "Only bridge");
        _;
    }

    constructor() {
        bridge = msg.sender;
    }

    // ── Bridge Functions ────────────────────────────────────

    /// @notice Mint tokens when energy is produced (1 THN = 1 MWh)
    function mint(address _to, uint256 _amount, string calldata _stationId) external onlyBridge {
        balanceOf[_to] += _amount;
        totalSupply += _amount;
        emit Transfer(address(0), _to, _amount);
        emit Minted(_to, _amount, _stationId);
    }

    /// @notice Burn tokens for ComEd toll or grid fees
    function burn(address _from, uint256 _amount, string calldata _reason) external onlyBridge {
        require(balanceOf[_from] >= _amount, "Insufficient balance");
        balanceOf[_from] -= _amount;
        totalSupply -= _amount;
        emit Transfer(_from, address(0), _amount);
        emit Burned(_from, _amount, _reason);
    }

    /// @notice Transfer bridge role (e.g., to a multisig later)
    function setBridge(address _newBridge) external onlyBridge {
        bridge = _newBridge;
    }

    // ── Standard ERC-20 ─────────────────────────────────────

    function transfer(address _to, uint256 _amount) external returns (bool) {
        require(balanceOf[msg.sender] >= _amount, "Insufficient balance");
        balanceOf[msg.sender] -= _amount;
        balanceOf[_to] += _amount;
        emit Transfer(msg.sender, _to, _amount);
        return true;
    }

    function approve(address _spender, uint256 _amount) external returns (bool) {
        allowance[msg.sender][_spender] = _amount;
        emit Approval(msg.sender, _spender, _amount);
        return true;
    }

    function transferFrom(address _from, address _to, uint256 _amount) external returns (bool) {
        require(balanceOf[_from] >= _amount, "Insufficient balance");
        require(allowance[_from][msg.sender] >= _amount, "Allowance exceeded");
        allowance[_from][msg.sender] -= _amount;
        balanceOf[_from] -= _amount;
        balanceOf[_to] += _amount;
        emit Transfer(_from, _to, _amount);
        return true;
    }
}
