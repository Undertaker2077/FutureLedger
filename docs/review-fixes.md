# 仓库审查问题修复记录

基于 `6fb2586`，分支 `codex/fix-reviewed-defects`。本轮处理审查报告中已复现的问题，保持合成数据与发布的 gold 文件不变。

## 改动

- B 在提交前重新检查授权到期、参数 hash、版本及是否使用，并使用上海业务日期计算日额度。缺少密码校验器时拒绝强验证。
- 排队操作的取消与 Worker 抢占通过 SQLite 事务互斥；成功取消会关闭 Outbox 并释放额度。抢占后仅返回已提交或待查证。
- 未来日期返回 `UNSUPPORTED_SCHEDULE`，不再提前扣款；已过期日期也拒绝提交。
- 执行异常统一回滚，避免一次无效操作破坏后续数据库事务。同一连接的操作通过锁串行化。
- A/B 提交丢失回包时保留 `PENDING_UNKNOWN` 和额度。B 把主体、原幂等键及结果绑定保存进执行数据库；A 新增主体隔离的只读按键查询接口。重启后状态查询可以核实银行事实，无需再付款。
- 现金流购买事件使用传入的 `goal_cents`；默认 600000 分的既有 oracle 保持不变。
- Vue 转账密码错误保留登录；每张卡拥有独立授权、过期重验证及完成状态，避免卡片串用授权和重复确认。
- Vue 首页显示当前登录用户的账户快照，登录/转账后刷新；删除固定余额、姓名、交易和财务洞察展示。加载失败显示错误，不显示旧余额。
- Vue 会话代次隔离丢弃旧请求的成功和错误响应，避免注销或切换用户后的数据串用及误注销。
- 开发工厂显式接通 A 的余额、收款人及报价读取，转账 Agent 可以生成待确认提议，仍不自动确认付款。
- 修复启动限制测试对环境变量的依赖、银行权限测试硬编码端口；前端锁文件改用官方 npm 域名，保留版本及 integrity；CI 增加前端测试和构建。

## 本次实际验证

|检查|结果|
|---|---|
|完整根目录 unittest|231 通过，0 失败|
|C4 quality runner|全部 12 个 gate 通过|
|PostgreSQL 银行 pytest|103 通过，0 失败|
|银行对账|5/5 通过，valid=true|
|前端 npm test|5 通过，0 失败|
|Vue 类型检查和生产构建|通过|
|参考 oracle|210/210 通过|
|Agent local 分析 / mock cashflow|180/180、30/30 通过，非真实模型成绩|

银行测试包括真实 PostgreSQL 提交成功后丢回包、B 关闭重启、只读查证为成功、只扣一次及对账的集成回归。独立审查发现的跨会话迟到响应问题也已补充测试并修复。测试输出存在本云任务的 `/workspace/futureledger-fix-evidence/`，不会把机器路径当作可移植 CI 依赖。

复验命令（仓库根目录，使用已安装依赖的 Python 环境）：

```bash
python scripts/run_c4_quality.py --output /tmp/futureledger-c4-evidence
npm ci --prefix apps/web
npm test --prefix apps/web
npm run check --prefix apps/web
npm run build --prefix apps/web
```

银行测试按 `services/mock-bank/README.md` 启动独立 PostgreSQL，并设置 `BANK_TEST_DATABASE_URL`、`PYTHONPATH=.:services/mock-bank`、test/reset 两个保护变量后运行 `python -m pytest services/mock-bank/tests -q`。本次验证使用 Python 3.12.14、Node 24.19.0、PostgreSQL 18.6。

## 仍然明确未完成

完整账单/代扣/任务/设置管理页面、正式 D 服务和代扣范围确认、预约调度、C 会话/DAG/SSE 持久化、生产认证和真实银行均不在本次修复中。银行执行恢复需要配置文件形式的 `FUTURELEDGER_EXECUTION_DB`；默认内存数据库不保留重启状态。真实 LLM、真实浏览器视觉/移动端及完整产品 E2E 未验证，不能承诺系统完全无 bug。
