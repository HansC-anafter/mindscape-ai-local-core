# Shell Package Migration Notes

## 当前状态

这是一个准备阶段的 package 结构，用于后续将 web-console 中的 Shell 核心功能迁移到这里。

## 目录结构

```
packages/shell/
├── src/
│   ├── pages/          # 页面组件（从 web-console/src/app/ 迁移）
│   ├── components/     # 可复用组件
│   ├── lib/            # 工具函数和 API 客户端
│   └── index.ts        # 入口文件
├── package.json
├── tsconfig.json
└── README.md
```

## 下一步

1. 迁移核心页面组件到 `src/pages/`
2. 迁移核心组件到 `src/components/`
3. 迁移 API 客户端抽象到 `src/lib/`
4. 更新 web-console 使用 `workspace:*` 依赖

## 注意事项

- 所有代码都在 local-core repo 内（100% 开源）
- 不依赖任何外部私有 repo
- 使用 pnpm workspace 管理依赖

