# FutureLedger Vue 工作台

`apps/web/` 是与现有 FastAPI Demo API 对接的 Vue 3 + TypeScript + Vite 工作台。

## 启动

先在另一个终端按根目录 README 配置 LLM 并启动 FastAPI，然后运行：

```bash
cd apps/web
npm ci
npm run dev
```

Vite 将 `/api` 代理到 `http://127.0.0.1:8000`。Vue 工作台通过登录页创建演示 session，再调用现有 `/api/ask`、`/api/actions/*` 和 `/api/plans/*` 接口。浏览器不保存密码、不编译 SQL，也不授予转账权限。

## 质量门

```bash
npm run check
npm run build
```

根目录的 `node scripts/check_prototype.cjs` 仍用于旧版 HTML 设计原型；它不是 Vue 工作台的浏览器视觉测试。当前 Vue 前端的实现边界和验收要求见 `docs/plans/2026-11-01-part-a-integration.md`。
