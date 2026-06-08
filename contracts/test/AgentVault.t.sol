// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import {Test} from "forge-std/Test.sol";
import {AgentVault, IERC20} from "../src/AgentVault.sol";

contract MockERC20 {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amt) external { balanceOf[to] += amt; }
    function transfer(address to, uint256 amt) external returns (bool) {
        balanceOf[msg.sender] -= amt; balanceOf[to] += amt; return true;
    }
    function approve(address sp, uint256 amt) external returns (bool) {
        allowance[msg.sender][sp] = amt; return true;
    }
    function transferFrom(address f, address t, uint256 amt) external returns (bool) {
        allowance[f][msg.sender] -= amt; balanceOf[f] -= amt; balanceOf[t] += amt; return true;
    }
}

contract AgentVaultTest is Test {
    MockERC20 token;
    address operator = address(0xA11CE);
    address seller = address(0x5E11E2);
    address attacker = address(0xBAD);

    function setUp() public { token = new MockERC20(); }

    function _vault(AgentVault.Mode m) internal returns (AgentVault v) {
        v = new AgentVault(IERC20(address(token)), operator, m);
        token.mint(address(v), 1000);
    }

    function _allow(AgentVault v) internal {
        address[] memory a = new address[](1); a[0] = seller;
        v.setMandate(a, 100, 100);
    }

    function testPermissionlessPaysAnyone() public {
        AgentVault v = _vault(AgentVault.Mode.Permissionless);
        vm.prank(operator); v.pay(attacker, 100);
        assertEq(token.balanceOf(attacker), 100);
    }

    function testMandateBlocksAttacker() public {
        AgentVault v = _vault(AgentVault.Mode.Mandate); _allow(v);
        vm.prank(operator); v.pay(seller, 50);              // legit ok
        assertEq(token.balanceOf(seller), 50);
        vm.prank(operator);
        vm.expectRevert(abi.encodeWithSelector(AgentVault.RecipientNotAllowed.selector, attacker));
        v.pay(attacker, 50);                                 // attacker blocked
        assertEq(token.balanceOf(attacker), 0);
    }

    function testMandatePerTxCap() public {
        AgentVault v = _vault(AgentVault.Mode.Mandate); _allow(v);
        vm.prank(operator); vm.expectRevert(); v.pay(seller, 101);
    }

    function testSessionBudgetAndReset() public {
        AgentVault v = _vault(AgentVault.Mode.Session); v.setSession(100);
        vm.prank(operator); v.pay(attacker, 100);            // fits budget -> leaks
        assertEq(token.balanceOf(attacker), 100);
        vm.prank(operator); vm.expectRevert(); v.pay(seller, 1);   // budget exhausted
        v.reset();
        vm.prank(operator); v.pay(seller, 1);                // fresh state
        assertEq(token.balanceOf(seller), 1);
    }

    // L3b: a mandate that only guards pay() does NOT stop an approval to the attacker
    function testApproveLeaksPastNaiveMandate() public {
        AgentVault v = _vault(AgentVault.Mode.Mandate); _allow(v);
        vm.prank(operator); v.authorizeSpender(attacker, 500);    // guardApprovals=false
        assertEq(token.allowance(address(v), attacker), 500);
        vm.prank(attacker); token.transferFrom(address(v), attacker, 500);  // drain
        assertEq(token.balanceOf(attacker), 500);
    }

    // ...and the fix: guardApprovals extends the recipient policy to approvals
    function testGuardApprovalsContainsIt() public {
        AgentVault v = _vault(AgentVault.Mode.Mandate); _allow(v);
        v.setGuardApprovals(true);
        vm.prank(operator);
        vm.expectRevert(abi.encodeWithSelector(AgentVault.RecipientNotAllowed.selector, attacker));
        v.authorizeSpender(attacker, 500);
    }

    function testOnlyOperatorCanSpend() public {
        AgentVault v = _vault(AgentVault.Mode.Permissionless);
        vm.expectRevert(AgentVault.NotOperator.selector);
        v.pay(attacker, 1);                                  // caller != operator
    }

    function testOwnerCanAlwaysWithdraw() public {
        AgentVault v = _vault(AgentVault.Mode.Mandate);
        v.withdraw(seller, 1000);
        assertEq(token.balanceOf(seller), 1000);
    }
}
