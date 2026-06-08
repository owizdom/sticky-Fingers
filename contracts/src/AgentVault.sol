// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @title AgentVault — an ON-CHAIN authorization layer for an agent's payments.
/// @notice Custodies a token and lets one `operator` (the agent) spend it, but only
/// within a policy enforced here, on-chain. The three Sticky Fingers arms map to the
/// three Modes; a policy violation reverts, and that revert *is* the containment.
/// `owner` can always withdraw (recovery), so funds can never get stuck.
contract AgentVault {
    enum Mode { Permissionless, Mandate, Session }

    IERC20 public immutable token;
    address public owner;       // can withdraw / reconfigure (recovery + setup)
    address public operator;    // the agent; the only address allowed to spend

    Mode public mode;

    // mandate params
    mapping(address => bool) public allowed;   // recipient allowlist
    uint256 public maxPerTx;
    uint256 public maxTotal;
    // session param
    uint256 public budget;
    // running state (reset per run via reset())
    uint256 public spent;       // mandate total / session drawn

    // L3b: does the policy also cover the approval path? A naive mandate guards
    // `pay` but NOT `authorizeSpender`, so a tricked agent can hand the attacker an
    // allowance to drain later. guardApprovals=true extends the policy to approvals.
    bool public guardApprovals;

    error NotOperator();
    error NotOwner();
    error RecipientNotAllowed(address who);
    error OverPerTxCap(uint256 amount, uint256 cap);
    error OverTotalCap(uint256 spent, uint256 amount, uint256 cap);
    error OverBudget(uint256 drawn, uint256 amount, uint256 budget);

    event Paid(address indexed recipient, uint256 amount);
    event Approved(address indexed spender, uint256 amount);

    modifier onlyOperator() { if (msg.sender != operator) revert NotOperator(); _; }
    modifier onlyOwner() { if (msg.sender != owner) revert NotOwner(); _; }

    constructor(IERC20 _token, address _operator, Mode _mode) {
        token = _token;
        owner = msg.sender;
        operator = _operator;
        mode = _mode;
    }

    // ---------- config (owner) ----------
    function setMandate(address[] calldata recipients, uint256 _maxPerTx, uint256 _maxTotal)
        external onlyOwner
    {
        for (uint256 i; i < recipients.length; i++) allowed[recipients[i]] = true;
        maxPerTx = _maxPerTx;
        maxTotal = _maxTotal;
    }
    function setSession(uint256 _budget) external onlyOwner { budget = _budget; }
    function setGuardApprovals(bool g) external onlyOwner { guardApprovals = g; }
    function reset() external onlyOwner { spent = 0; }   // fresh policy state per run

    // ---------- the spend path (operator = agent) ----------
    function pay(address recipient, uint256 amount) external onlyOperator {
        if (mode == Mode.Mandate) {
            if (!allowed[recipient]) revert RecipientNotAllowed(recipient);
            if (amount > maxPerTx) revert OverPerTxCap(amount, maxPerTx);
            if (spent + amount > maxTotal) revert OverTotalCap(spent, amount, maxTotal);
            spent += amount;
        } else if (mode == Mode.Session) {
            if (spent + amount > budget) revert OverBudget(spent, amount, budget);
            spent += amount;
        } // Permissionless: no checks.
        token.transfer(recipient, amount);
        emit Paid(recipient, amount);
    }

    // ---------- L3b: the alternate value-movement path ----------
    /// @notice Grant an ERC-20 allowance from the vault. Real session keys / smart
    /// accounts commonly permit this. With guardApprovals=false a Mandate that only
    /// checks `pay` does NOT stop the agent approving an attacker (the leak); with
    /// guardApprovals=true the same recipient/amount policy applies to approvals.
    function authorizeSpender(address spender, uint256 amount) external onlyOperator {
        if (guardApprovals && mode == Mode.Mandate) {
            if (!allowed[spender]) revert RecipientNotAllowed(spender);
            if (amount > maxPerTx) revert OverPerTxCap(amount, maxPerTx);
        } else if (guardApprovals && mode == Mode.Session) {
            if (spent + amount > budget) revert OverBudget(spent, amount, budget);
        }
        token.approve(spender, amount);
        emit Approved(spender, amount);
    }

    // ---------- recovery (owner) ----------
    function withdraw(address to, uint256 amount) external onlyOwner {
        token.transfer(to, amount);
    }
    function balance() external view returns (uint256) {
        return token.balanceOf(address(this));
    }
}
