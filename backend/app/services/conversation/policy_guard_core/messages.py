"""User-facing policy guard messages."""


def tool_not_found_blocked() -> str:
    return "\u5de5\u5177\u672a\u5728\u8a3b\u518a\u8868\u4e2d\u627e\u5230\uff0c\u7121\u6cd5\u57f7\u884c"


def tool_not_found_allowed() -> str:
    return "\u5de5\u5177\u672a\u5728\u8a3b\u518a\u8868\u4e2d\u627e\u5230\uff0c\u5df2\u5141\u8a31\u4f46\u9700\u8981\u78ba\u8a8d"


def missing_capability_blocked(tool_id: str) -> str:
    return (
        f"\u5de5\u5177 {tool_id} \u7f3a\u5c11 capability_code\uff0c"
        "\u7121\u6cd5\u57f7\u884c"
    )


def missing_capability_allowed(tool_id: str) -> str:
    return (
        f"\u5de5\u5177 {tool_id} \u7f3a\u5c11 capability_code\uff0c"
        "\u5df2\u5141\u8a31\u4f46\u9700\u8981\u78ba\u8a8d"
    )


def capability_denied(capability_code: str) -> str:
    return (
        f"\u5de5\u5177 {capability_code} "
        "\u5df2\u88ab\u5de5\u4f5c\u5340\u653f\u7b56\u7981\u6b62\u4f7f\u7528"
    )


def capability_not_allowed(capability_code: str) -> str:
    return (
        f"\u5de5\u5177 {capability_code} "
        "\u4e0d\u5728\u5de5\u4f5c\u5340\u5141\u8a31\u7684\u5de5\u5177\u5217\u8868\u4e2d"
    )


def capability_requires_explicit_approval(capability_code: str) -> str:
    return (
        f"\u5de5\u5177 {capability_code} "
        "\u9700\u8981\u660e\u78ba\u78ba\u8a8d"
        "\uff08\u5de5\u4f5c\u5340\u653f\u7b56\u8981\u6c42\uff09"
    )


def chain_too_long(chain_length: int, max_chain: int) -> str:
    return (
        f"\u5de5\u5177\u8abf\u7528\u93c8\u9577\u5ea6 ({chain_length}) "
        f"\u8d85\u904e\u6700\u5927\u9650\u5236 ({max_chain})\uff0c"
        "\u8acb\u7c21\u5316\u64cd\u4f5c\u6d41\u7a0b"
    )


def risk_requires_confirmation(capability_code: str, risk_class: str) -> str:
    return (
        f"\u5de5\u5177 {capability_code} "
        "\u9700\u8981\u78ba\u8a8d"
        f"\uff08\u98a8\u96aa\u7b49\u7d1a\uff1a{risk_class}\uff09"
    )
