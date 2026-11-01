# E+F 前端与交付状态

更新日期：2026-11-01

## 已完成并本地验证

- `apps/web/` 已搭建 Vue 3、TypeScript、Vite、Vue Router、Pinia 工程，含总览、账单、代扣、未来账本、任务、偏好、评审及助手路由。
- 离线演示模式下：账单筛选/汇总、代扣保护切换/创建待确认任务、现金流假设编辑/逐日模拟、任务本地状态确认、偏好修改均可交互。
- 助手可选择连接现有 `/api/sessions` 和 `/api/agent/chat`；API 失败时显示可读错误。演示交互不提交资金操作。
- API 模式的助手请求可在偏好页输入当前开发环境 Bearer token；凭据只保存在页面内存，刷新即清除。连接范围仅含会话与 Agent chat。
- Vite `/api` 代理默认端口与 C 开发服务的 8001 端口一致，也可用 `VITE_API_PROXY_TARGET` 覆盖。
- 桌面浏览器检查已打开总览、账单、代扣、未来账本、任务和偏好页；显示模拟银行标识。
- `npm run check` 和 `npm run build` 通过；`node scripts/check_prototype.cjs` 通过（原型 7 页、30 个固定现金流情景、工资延迟交互）。

## 尚未完成的 E+F 验收

- 新 Vue 页面目前除助手会话/聊天外主要使用本地合成数据；账单、代扣、现金流、操作确认/强验证、任务事实状态尚未接通可运行的 A/B/D 服务。
- Vue 任务页当前的本地确认只改变演示状态；生产 API 的确认卡、验证卡、执行状态查证及 SSE 重连尚未实现。
- 新 Vue 工程目前做了手动浏览器页面检查和类型/构建检查；尚无自动化组件/浏览器端到端测试，也未完成全面移动端/视觉回归。
- 既有 `docs/c4-final-report.md` 状态是 C 模块离线检查 189/189；共享 60 项验收为 50 BLOCKED、10 NOT_RUN。此结果不代表 E+F 或全系统验收通过。
- 真实 A/B/D 联调、Worker 跨进程恢复、全链路故障注入、沙箱隔离、Compose/独立机器复建及最终演示证据仍待依赖服务和部署环境。

## 本地后端回归尝试（2026-11-01）

- 在隔离 `.venv` 中安装 `requirements-demo.txt` 与 `requirements-c4.txt`；`pip check` 无依赖冲突。
- 工作区原有 `data/benchmark.sqlite` 是 0 字节。`scripts/prepare_c4_fixture.py` 原先将“文件存在”误判成有效 fixture，现已改为校验 manifest 中各输入文件 SHA256，并从已发布账户/流水构建忽略型只读 SQLite fixture；不会改写 JSON/CSV/gold 数据。
- 定向测试通过：A↔B 1 项、B↔C 1 项、Execution Gate 5 项、D 模块 16 项。
- 全量 `unittest discover` 已运行 215 项，仍有 7 failures、14 errors；所以整体回归失败。UTF-8 模式下 JSON Schema 用例已通过；剩余错误集中于 DAG/API 用例及 Windows 下测试清理未关闭的 SQLite 临时连接。完整机器日志曾临时写入本地工作区，未作为通过证据。
- 修复了 `scripts/c4_unittest.py` 对 `unittest._ErrorHolder` 的处理，避免导入错误时汇总器自身崩溃；其余失败仍需逐项定位，当前没有将它们伪装成通过。
- 本轮复跑 C4 验收文件：44 项中 42 项通过、1 项失败、1 项错误。失败为并发相同 Idempotency-Key 的 C API 用例；错误为 C fixture 测试的主体授权与预期不匹配。测试临时 SQLite 连接现已显式关闭，未改动 C 实现来掩盖失败。
- E/F 本地门槛不等于共享验收通过：前端 API 模式尚未连接真实 A/B/D 服务，60 项全链路共享验收仍未完成。

## 复现命令

```powershell
cd apps/web
npm ci
npm run check
npm run build
cd ../..
node scripts/check_prototype.cjs
```

演示默认使用合成数据，界面持续显示模拟环境。不要将演示状态写成真实银行执行结果。
