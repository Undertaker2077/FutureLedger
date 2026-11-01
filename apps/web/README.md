# E+F 前端与交付

## 启动前端

```powershell
cd apps/web
npm ci
npm run dev
```

默认 `VITE_DEMO_MODE` 为 mock，所有演示内容都使用合成数据，且不会提交资金操作。要启用现有 C 应用 API：

```powershell
$env:VITE_DEMO_MODE='false'
npm run dev
```

Vite 默认将 `/api` 代理到 `http://127.0.0.1:8001`（与 C API 开发启动端口一致）；若服务运行在其他地址，设置 `VITE_API_PROXY_TARGET`，例如 `http://127.0.0.1:8010`。服务端必须自行配置认证和适配器；当前 C API 默认拒绝未认证请求，且未配置的银行/现金流依赖会返回明确错误。浏览器不持久化凭据、不授予权限。

API 模式下，在“偏好设置”中输入当前开发服务签发的 Bearer token，助手会调用 `POST /api/sessions` 与 `POST /api/agent/chat`。token 只保存在当前页面内存，刷新后需重新输入；不要输入生产凭据。账单、代扣、现金流和任务页的内容仍为本地合成演示，不能据此判断后端执行或银行状态。

## 质量门

```powershell
npm run check
npm run build
cd ../..
node scripts/check_prototype.cjs
```

原型检查范围是 prototype 的 7 个页面、30 个现金流固定情景和工资延迟交互；它不是新 Vue 应用的端到端测试。Vue 工作台的页面能力、已执行质量门和剩余集成缺口见 `docs/ef-delivery-status.md` 与 `docs/c4-final-report.md`。
