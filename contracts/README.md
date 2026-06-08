# AgentVault — on-chain authorization for Sticky Fingers (L3)

`AgentVault` custodies a token and lets one `operator` (the agent) spend it, but only
within a policy enforced **on-chain**. The three Sticky Fingers arms map to `Mode`:

- **Permissionless** — pays anyone.
- **Mandate** — recipient allowlist + per-tx and total caps.
- **Session** — a single drawn-down budget.

A policy violation reverts; the revert is the containment. `owner` can always `withdraw`
(recovery), so funds can never get stuck. `authorizeSpender()` is the L3b approval path —
the value-movement route a recipient-allowlist on `pay()` does not cover unless
`guardApprovals` is on.

Build + test (forge-std is gitignored; reinstall it):

    forge install foundry-rs/forge-std
    forge test -vv
