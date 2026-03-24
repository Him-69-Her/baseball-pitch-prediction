// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * TinyHub Energy Token — L2 Arbitrum Version
 * 1 THN = 1 MWh of renewable energy
 *
 * Upgrades from V1:
 *   - Multi-minter: both settler and bridge can mint/burn
 *   - Owner role for managing minters
 *   - Compatible with TinyHubMarketV3 settler pattern
 *
 * Deploy target: Arbitrum Sepolia (chainId 421614)
 */
contract TinyHubTokenL2 {
    string public name = "TinyHub Energy";
    string public symbol = "THN";
    uint8  public decimals = 18;
    uint256 public totalSupply;

    address public owner;
    mapping(address => bool) public minters;  // Settler + bridge wallets

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event Minted(address indexed to, uint256 mwh, string stationId);
    event Burned(address indexed from, uint256 amount, string reason);
    event MinterUpdated(address indexed minter, bool authorized);

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    modifier onlyMinter() {
        require(minters[msg.sender], "Only minter");
        _;
    }

    constructor() {
        owner = msg.sender;
        minters[msg.sender] = true;  // Deployer is first minter
    }

    // ── Admin ───────────────────────────────────────────────

    function setMinter(address _minter, bool _authorized) external onlyOwner {
        minters[_minter] = _authorized;
        emit MinterUpdated(_minter, _authorized);
    }

    function transferOwnership(address _newOwner) external onlyOwner {
        require(_newOwner != address(0), "Zero address");
        owner = _newOwner;
    }

    // ── Minter Functions ────────────────────────────────────

    /// @notice Mint tokens when energy is produced (1 THN = 1 MWh)
    function mint(address _to, uint256 _amount, string calldata _stationId) external onlyMinter {
        balanceOf[_to] += _amount;
        totalSupply += _amount;
        emit Transfer(address(0), _to, _amount);
        emit Minted(_to, _amount, _stationId);
    }

    /// @notice Burn tokens for grid toll (Ameren/ComEd fees)
    function burn(address _from, uint256 _amount, string calldata _reason) external onlyMinter {
        require(balanceOf[_from] >= _amount, "Insufficient balance");
        balanceOf[_from] -= _amount;
        totalSupply -= _amount;
        emit Transfer(_from, address(0), _amount);
        emit Burned(_from, _amount, _reason);
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
