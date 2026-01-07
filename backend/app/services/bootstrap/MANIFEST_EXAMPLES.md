# Manifest.yaml Bootstrap 配置示例

## 基础示例

### 1. 执行 Python 脚本

```yaml
bootstrap:
  - type: python_script
    path: scripts/setup.py
    timeout: 60
```

### 2. 初始化 Content Vault

```yaml
bootstrap:
  - type: content_vault_init
    vault_path: ~/content-vault
    timeout: 30
```

### 3. 初始化 Site-Hub Runtime（条件执行）

```yaml
bootstrap:
  - type: site_hub_runtime_init
    warn_if_missing: true
```

## 条件执行示例

### 为特定能力代码列表执行操作

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
      vault_path: ~/content-vault
```

### 使用正则表达式匹配能力代码

```yaml
bootstrap:
  - type: conditional
    condition:
      type: capability_code_match
      value: "^ig_.*"
    strategy:
      type: content_vault_init
```

### 根据环境变量决定是否执行

```yaml
bootstrap:
  - type: conditional
    condition:
      type: env_var_set
      value: "SITE_HUB_API_BASE"
    strategy:
      type: site_hub_runtime_init
      warn_if_missing: false
```

### 总是执行（无条件）

```yaml
bootstrap:
  - type: conditional
    condition:
      type: always
    strategy:
      type: python_script
      path: scripts/always_run.py
```

## 组合多个 Bootstrap 操作

```yaml
bootstrap:
  # 1. 总是执行初始化脚本
  - type: python_script
    path: scripts/init.py

  # 2. 如果是 IG 相关能力，初始化 Content Vault
  - type: conditional
    condition:
      type: capability_code_in
      value:
        - ig_post
        - instagram
    strategy:
      type: content_vault_init

  # 3. 如果环境变量设置，初始化 Site-Hub
  - type: conditional
    condition:
      type: env_var_set
      value: "SITE_HUB_API_BASE"
    strategy:
      type: site_hub_runtime_init
```

## 完整示例：IG Post 能力包

```yaml
name: IG Post Generation
code: ig_post
version: 1.0.0

# ... 其他配置 ...

bootstrap:
  # 自动初始化 Content Vault（如果能力代码匹配）
  - type: conditional
    condition:
      type: capability_code_in
      value:
        - ig_post
        - ig_post_generation
        - instagram
        - social_media
    strategy:
      type: content_vault_init
      vault_path: ~/content-vault

  # 执行自定义初始化脚本
  - type: python_script
    path: scripts/init_ig_templates.py
    timeout: 30
```

## 完整示例：Site-Hub Integration 能力包

```yaml
name: Site-Hub Integration
code: site_hub_integration
version: 1.0.0

# ... 其他配置 ...

bootstrap:
  # 如果环境变量已设置，尝试自动注册 runtime
  - type: site_hub_runtime_init
    warn_if_missing: true

  # 执行其他初始化
  - type: python_script
    path: scripts/validate_connection.py
```

