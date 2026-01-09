# Parameter Adapter Module

## 架構設計原則

### 中性通用化設計
- **無業務邏輯**：所有策略和適配器都是通用的，不包含特定業務邏輯
- **配置驅動**：參數轉換規則通過契約（Contract）定義，從外部配置加載
- **可擴展性**：通過註冊新策略和契約來支持新工具，無需修改核心代碼

### 職責邊界清晰

#### Core (`core.py`)
- **職責**：策略選擇、協調執行、錯誤處理
- **不負責**：具體參數轉換邏輯、契約定義、上下文創建

#### Context (`context.py`)
- **職責**：執行上下文數據結構定義、上下文構建
- **不負責**：參數轉換、業務邏輯

#### Contracts (`contracts.py`)
- **職責**：契約數據結構定義、契約存儲和查找、從外部源加載契約
- **不負責**：參數轉換、業務邏輯、契約創建（契約從外部加載）

#### Strategies (`strategies/`)
- **職責**：通用的參數轉換模式（基於契約、參數映射等）
- **不負責**：業務特定邏輯、契約定義

#### Validators (`validators.py`)
- **職責**：參數驗證（完整性、類型等）
- **不負責**：參數轉換、契約定義

## 使用方式

### 1. 在 ToolExecutor 中集成

```python
from backend.app.services.parameter_adapter import (
    get_parameter_adapter,
    ExecutionContextBuilder
)

class ToolExecutor:
    def __init__(self):
        self.parameter_adapter = get_parameter_adapter()
        self._execution_context = None

    def set_execution_context(self, workspace_id, profile_id, ...):
        self._execution_context = ExecutionContextBuilder.from_workflow_params(
            workspace_id=workspace_id,
            profile_id=profile_id,
            ...
        )

    async def execute_tool(self, tool_name: str, **kwargs):
        if self._execution_context:
            kwargs = self.parameter_adapter.adapt_parameters(
                tool_name=tool_name,
                raw_params=kwargs,
                execution_context=self._execution_context
            )
        # ... execute tool
```

### 2. 定義工具契約（在 capability manifest.yaml 中）

```yaml
tools:
  - name: intake_router
    backend: "capabilities.yogacoach.tools.intake_router:create_session"
    parameters:
      tenant_id:
        required: false
        injected: true
        source: "context.workspace_id"
        description: "Tenant ID for multi-tenant isolation"
      actor_id:
        required: false
        injected: true
        source: "context.profile_id"
        description: "Who triggered the action"
      subject_user_id:
        required: false
        injected: true
        source: "context.profile_id"
        description: "The person being analyzed"
      teacher_id:
        required: false
        description: "Optional teacher ID"
      channel:
        required: false
        default: "web"
        description: "Channel type"
```

### 3. 註冊參數映射（如果需要）

```python
from backend.app.services.parameter_adapter import get_parameter_adapter

adapter = get_parameter_adapter()
adapter.mapping_strategy.register_mapping(
    tool_name="filesystem_read_file",
    old_param_name="path",
    new_param_name="file_path"
)
```

## 擴展方式

### 添加新的通用策略

1. 在 `strategies/` 目錄創建新策略類
2. 繼承 `ParameterAdaptationStrategy`
3. 實現通用轉換邏輯（不包含業務邏輯）
4. 在 `core.py` 中註冊策略

### 定義工具契約

契約應該在 capability 的 `manifest.yaml` 中定義，通過 `ContractRegistry.load_contracts_from_manifest()` 加載。

## 文件結構

```
parameter_adapter/
├── __init__.py          # 模組導出
├── core.py              # 核心適配器（策略選擇、協調）
├── context.py           # 執行上下文管理
├── contracts.py         # 契約定義和註冊表
├── validators.py        # 參數驗證器
├── strategies/          # 通用策略
│   ├── __init__.py
│   ├── base.py          # 基礎策略接口
│   ├── contract_based.py    # 契約驅動策略（通用）
│   └── parameter_mapping.py # 參數映射策略（通用）
└── README.md            # 本文檔
```

