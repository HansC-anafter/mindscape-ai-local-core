"""
LangChain 預定義工具清單

為 Config Assistant 提供可推薦給用戶的 LangChain 工具清單。
包含中文描述、API key 需求、使用場景等資訊。
"""

from typing import Dict, List, Optional, Any

# 預定義的 LangChain 工具清單
KNOWN_LANGCHAIN_TOOLS = [
    {
        "name": "wikipedia",
        "display_name": "Wikipedia",
        "description": "搜尋維基百科知識，獲取各種主題的詳細資訊",
        "module": "langchain_community.tools",
        "class": "WikipediaQueryRun",
        "requires_api_key": False,
        "category": "搜尋",
        "use_cases": ["知識查詢", "資料研究", "學術搜尋"],
        "language_support": ["多語言"],
    },
    {
        "name": "arxiv",
        "display_name": "ArXiv",
        "description": "搜尋 ArXiv 學術論文資料庫",
        "module": "langchain_community.tools.arxiv.tool",
        "class": "ArxivQueryRun",
        "requires_api_key": False,
        "category": "搜尋",
        "use_cases": ["學術研究", "論文查詢", "科學文獻"],
    },
    {
        "name": "serpapi",
        "display_name": "SerpAPI (Google搜尋)",
        "description": "使用 Google 搜尋引擎獲取最新的網路資訊",
        "module": "langchain_community.utilities",
        "class": "SerpAPIWrapper",
        "requires_api_key": True,
        "api_key_field": "serpapi_api_key",
        "api_key_url": "https://serpapi.com/",
        "category": "搜尋",
        "use_cases": ["網路搜尋", "即時資訊", "新聞查詢"],
        "note": "需要到 serpapi.com 註冊並獲取 API key"
    },
    {
        "name": "wolfram_alpha",
        "display_name": "Wolfram Alpha",
        "description": "進行數學計算、科學計算和知識查詢",
        "module": "langchain_community.utilities.wolfram_alpha",
        "class": "WolframAlphaAPIWrapper",
        "requires_api_key": True,
        "api_key_field": "wolfram_alpha_appid",
        "api_key_url": "https://products.wolframalpha.com/api/",
        "category": "計算",
        "use_cases": ["數學計算", "單位轉換", "科學計算"],
        "note": "需要到 Wolfram Alpha 網站註冊並獲取 App ID"
    },
    {
        "name": "python_repl",
        "display_name": "Python REPL",
        "description": "執行 Python 程式碼進行計算和資料處理",
        "module": "langchain_experimental.tools",
        "class": "PythonREPLTool",
        "requires_api_key": False,
        "category": "自動化",
        "use_cases": ["程式執行", "資料處理", "計算任務"],
        "danger_level": "critical",
        "note": "⚠️ 高風險工具，可執行任意 Python 程式碼"
    },
    {
        "name": "requests_get",
        "display_name": "HTTP GET",
        "description": "發送 HTTP GET 請求獲取網頁內容",
        "module": "langchain_community.tools.requests.tool",
        "class": "RequestsGetTool",
        "requires_api_key": False,
        "category": "整合",
        "use_cases": ["API 調用", "網頁抓取", "資料獲取"],
    },
    {
        "name": "requests_post",
        "display_name": "HTTP POST",
        "description": "發送 HTTP POST 請求提交資料",
        "module": "langchain_community.tools.requests.tool",
        "class": "RequestsPostTool",
        "requires_api_key": False,
        "category": "整合",
        "use_cases": ["API 調用", "資料提交", "表單發送"],
        "danger_level": "medium"
    },
    {
        "name": "duckduckgo",
        "display_name": "DuckDuckGo搜尋",
        "description": "使用 DuckDuckGo 搜尋引擎（無需 API key）",
        "module": "langchain_community.tools",
        "class": "DuckDuckGoSearchRun",
        "requires_api_key": False,
        "category": "搜尋",
        "use_cases": ["網路搜尋", "隱私搜尋", "免費搜尋"],
        "note": "免費且無需註冊"
    },
]

# 按分類組織的工具索引
TOOLS_BY_CATEGORY = {
    "搜尋": ["wikipedia", "arxiv", "serpapi", "duckduckgo"],
    "計算": ["wolfram_alpha", "python_repl"],
    "整合": ["requests_get", "requests_post"],
    "自動化": ["python_repl"],
}

# 免費工具清單（無需 API key）
FREE_TOOLS = [
    "wikipedia", "arxiv", "duckduckgo",
    "python_repl", "requests_get", "requests_post"
]


def get_langchain_tool_class(tool_name: str) -> Optional[Dict[str, Any]]:
    """
    根據工具名稱獲取工具類資訊

    Args:
        tool_name: 工具名稱（如 "wikipedia"）

    Returns:
        工具資訊字典，如果找不到則返回 None
    """
    for tool in KNOWN_LANGCHAIN_TOOLS:
        if tool["name"] == tool_name:
            return tool
    return None


def get_tools_by_category(category: str) -> List[Dict[str, Any]]:
    """
    獲取指定分類的所有工具

    Args:
        category: 分類名稱（如 "搜尋"）

    Returns:
        工具清單
    """
    tool_names = TOOLS_BY_CATEGORY.get(category, [])
    return [
        tool for tool in KNOWN_LANGCHAIN_TOOLS
        if tool["name"] in tool_names
    ]


def get_free_tools() -> List[Dict[str, Any]]:
    """
    獲取所有免費工具（無需 API key）

    Returns:
        免費工具清單
    """
    return [
        tool for tool in KNOWN_LANGCHAIN_TOOLS
        if tool["name"] in FREE_TOOLS
    ]


def get_tools_for_use_case(use_case: str) -> List[Dict[str, Any]]:
    """
    根據使用場景推薦工具

    Args:
        use_case: 使用場景（如 "知識查詢"）

    Returns:
        推薦工具清單
    """
    return [
        tool for tool in KNOWN_LANGCHAIN_TOOLS
        if use_case in tool.get("use_cases", [])
    ]


def format_tool_for_assistant(tool: Dict[str, Any]) -> str:
    """
    格式化工具資訊供 Config Assistant 使用

    Args:
        tool: 工具資訊字典

    Returns:
        格式化的工具描述字串
    """
    lines = []
    lines.append(f"**{tool['display_name']}** ({tool['name']})")
    lines.append(f"📝 {tool['description']}")

    if tool.get("requires_api_key"):
        lines.append(f"🔑 需要 API key: {tool.get('api_key_field')}")
        if tool.get("api_key_url"):
            lines.append(f"   獲取網址: {tool['api_key_url']}")
    else:
        lines.append("✅ 免費使用，無需 API key")

    if tool.get("use_cases"):
        lines.append(f"💡 適用場景: {', '.join(tool['use_cases'])}")

    if tool.get("danger_level") in ["high", "critical"]:
        lines.append(f"⚠️  {tool.get('note', '高風險工具')}")

    return "\n".join(lines)


def get_assistant_recommendations(user_intent: str) -> List[Dict[str, Any]]:
    """
    根據用戶意圖推薦工具（供 Config Assistant 使用）

    Args:
        user_intent: 用戶意圖描述（如 "我想搜尋資料"）

    Returns:
        推薦工具清單
    """
    intent_lower = user_intent.lower()

    # 搜尋相關
    if any(kw in intent_lower for kw in ["搜尋", "查詢", "search", "find", "資料"]):
        # 優先推薦免費工具
        return [
            get_langchain_tool_class("wikipedia"),
            get_langchain_tool_class("duckduckgo"),
            get_langchain_tool_class("arxiv"),
        ]

    # 計算相關
    if any(kw in intent_lower for kw in ["計算", "數學", "math", "calculate"]):
        return [
            get_langchain_tool_class("wolfram_alpha"),
            get_langchain_tool_class("python_repl"),
        ]

    # API 相關
    if any(kw in intent_lower for kw in ["api", "網頁", "http", "抓取"]):
        return [
            get_langchain_tool_class("requests_get"),
            get_langchain_tool_class("requests_post"),
        ]

    # 預設推薦最常用的免費工具
    return [
        get_langchain_tool_class("wikipedia"),
        get_langchain_tool_class("duckduckgo"),
    ]
