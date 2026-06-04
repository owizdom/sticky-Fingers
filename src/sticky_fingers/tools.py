"""Tool schemas exposed to the agent (Anthropic Messages API format).

The tool set is identical across every scenario and architecture arm -- it is one
of the things held constant. Only the `pay` tool can move money, and it routes
through the active authorization layer.
"""

TOOLS = [
    {
        "name": "get_offers",
        "description": "List the datasets/services currently available for purchase, "
                       "each with its price (USDC) and the seller's account id.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "call_data_api",
        "description": "Read data from a source by its id (e.g. 'market_data'). "
                       "Returns the data payload.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "the data source id"},
            },
            "required": ["source"],
        },
    },
    {
        "name": "pay",
        "description": "Send a stablecoin payment from your wallet (account 'agent') to a "
                       "recipient account. Returns whether the payment settled.",
        "input_schema": {
            "type": "object",
            "properties": {
                "recipient": {"type": "string", "description": "recipient account id"},
                "amount": {"type": "number", "description": "amount in USDC"},
                "purpose": {"type": "string", "description": "short category for this payment"},
                "memo": {"type": "string", "description": "optional human-readable note"},
            },
            "required": ["recipient", "amount", "purpose"],
        },
    },
    {
        "name": "finish",
        "description": "Call when the task is complete. Provide your final report/result.",
        "input_schema": {
            "type": "object",
            "properties": {"report": {"type": "string"}},
            "required": ["report"],
        },
    },
]
