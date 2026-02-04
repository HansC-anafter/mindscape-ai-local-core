#!/bin/bash
# MCP Gateway Runner - 自動找到支援 ESM 的 Node.js
# 這讓 MCP Gateway 可以在不同環境下正常運行

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 嘗試找到支援 ESM 的 Node.js (需要 v18+)
find_node() {
    # 優先順序：nvm, homebrew, volta, asdf, fnm, 系統
    local candidates=(
        "$HOME/.nvm/versions/node/*/bin/node"
        "/opt/homebrew/bin/node"
        "$HOME/.volta/bin/node"
        "$HOME/.asdf/shims/node"
        "$HOME/.fnm/node-versions/*/installation/bin/node"
        "/usr/local/bin/node"
        "/usr/bin/node"
    )

    for pattern in "${candidates[@]}"; do
        for node_path in $pattern; do
            if [[ -x "$node_path" ]]; then
                # 檢查版本 >= 18
                local version=$("$node_path" --version 2>/dev/null | sed 's/v//' | cut -d. -f1)
                if [[ "$version" -ge 18 ]]; then
                    echo "$node_path"
                    return 0
                fi
            fi
        done
    done

    # 最後嘗試 PATH 中的 node
    if command -v node &>/dev/null; then
        local version=$(node --version | sed 's/v//' | cut -d. -f1)
        if [[ "$version" -ge 18 ]]; then
            echo "$(command -v node)"
            return 0
        fi
    fi

    return 1
}

NODE_PATH=$(find_node)

if [[ -z "$NODE_PATH" ]]; then
    echo "Error: Node.js v18+ required for ESM support" >&2
    echo "Please install Node.js via nvm, homebrew, or volta" >&2
    exit 1
fi

# 執行 MCP Gateway
exec "$NODE_PATH" "$SCRIPT_DIR/dist/index.js" "$@"
