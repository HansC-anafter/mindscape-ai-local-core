# Bootstrap 配置指南

## 概述

Bootstrap 系统使用策略模式处理安装后的初始化操作，所有配置通过 `manifest.yaml` 声明，避免在代码中硬编码业务逻辑。

## 配置方式

在 `manifest.yaml` 中添加 `bootstrap` 字段：

```yaml
bootstrap:
  - type: <strategy_type>
    # ... 策略特定配置
```

## 支持的策略类型

### 1. `python_script` - 执行 Python 脚本

执行能力包中的 Python 脚本。

```yaml
bootstrap:
  - type: python_script
    path: scripts/init.py  # 相对于能力包根目录
    timeout: 60  # 可选，默认 60 秒
```

### 2. `content_vault_init` - 初始化 Content Vault

初始化 Content Vault 系统。

```yaml
bootstrap:
  - type: content_vault_init
    vault_path: ~/content-vault  # 可选，默认路径
    timeout: 30  # 可选，默认 30 秒
```

### 3. `site_hub_runtime_init` - 初始化 Site-Hub Runtime

自动检查并注册 Site-Hub Runtime（如果环境变量已设置）。

```yaml
bootstrap:
  - type: site_hub_runtime_init
    warn_if_missing: true  # 可选，如果环境变量未设置是否警告，默认 true
```

### 4. `conditional` - 条件执行策略

根据条件执行其他策略。用于替代硬编码的能力代码列表。

```yaml
bootstrap:
  - type: conditional
    condition:
      type: capability_code_in  # 条件类型
      value:  # 条件值
        - ig_post
        - ig_post_generation
        - instagram
        - social_media
        - ig_series_manager
        - ig_review_system
    strategy:
      type: content_vault_init
      vault_path: ~/content-vault
```

#### 支持的条件类型

- `capability_code_in`: 能力代码在列表中
  ```yaml
  condition:
    type: capability_code_in
    value: ["ig_post", "instagram"]
  ```

- `capability_code_match`: 能力代码匹配正则表达式
  ```yaml
  condition:
    type: capability_code_match
    value: "^ig_.*"
  ```

- `env_var_set`: 环境变量已设置
  ```yaml
  condition:
    type: env_var_set
    value: "SITE_HUB_API_BASE"
  ```

- `always`: 总是执行
  ```yaml
  condition:
    type: always
  ```

## 迁移示例

### 旧方式（硬编码，已移除）

之前代码中硬编码了 IG 相关能力：

```python
ig_related_codes = [
    'ig_post', 'ig_post_generation', 'instagram', 'social_media',
    'ig_series_manager', 'ig_review_system'
]
if capability_code in ig_related_codes:
    self._bootstrap_content_vault(result)
```

### 新方式（配置驱动）

在 `manifest.yaml` 中声明：

```yaml
bootstrap:
  - type: conditional
    condition:
      type: capability_code_in
      value:
        - ig_post
        - ig_post_generation
        - instagram
        - social_media
        - ig_series_manager
        - ig_review_system
    strategy:
      type: content_vault_init
```

## 扩展策略

如果需要添加新的策略类型：

1. 在 `bootstrap_strategies.py` 中创建新的策略类，继承 `BootstrapStrategy`
2. 实现 `execute()` 和 `get_type()` 方法
3. 在 `bootstrap_registry.py` 中注册新策略

示例：

```python
class MyCustomStrategy(BootstrapStrategy):
    def get_type(self) -> str:
        return "my_custom_strategy"

    def execute(self, local_core_root, cap_dir, capability_code, config, result):
        # 实现自定义逻辑
        return True
```

然后在 `BootstrapRegistry._initialize()` 中注册：

```python
self.register(MyCustomStrategy())
```

## 优势

1. **无硬编码**：所有业务逻辑通过配置声明
2. **可扩展**：轻松添加新的策略类型
3. **可测试**：每个策略独立，易于单元测试
4. **可维护**：配置集中管理，代码更清晰

