# 本次验证记录

验证日期：2026-10-28（Asia/Hong_Kong）。离线参考结果与 Role A 模拟银行分组报告；不代表真实银行或完整 B/C 端到端成绩。

|检查|实际结果|范围|
|---|---|---|
|数据生成|3839标准行，3963原始行，124重复|固定种子，两年历史|
|生产分析路径|180/180|`Ledger.execute` 对全部分析案例的数值和精确证据 ID|
|生产现金流路径|30/30|`demo.cashflow.simulate_cashflow` 对全部案例的逐日余额、最低值、日期和可行性|
|Part D 聚焦测试|16/16|现金流锚点、分析边界、API 会话/校验/只读性、210 条生产基准对齐|
|参考分析对齐|180/180|独立 oracle 的离线基准结果，单独记录，不作为生产实现|
|参考现金流对齐|30/30|独立 oracle 的离线基准结果，单独记录，不作为生产实现|
|完整 `unittest discover`|环境阻塞|本 Windows 沙箱创建 FastAPI `TestClient` 时 asyncio 事件循环挂起；Part D 和参考测试已分别运行|
|原型JS smoke|7页面、30情景、工资延期交互通过|Node VM运行时检查；不含浏览器渲染|
|Role A pytest|101项通过|PostgreSQL 18.6 schema/reset/read/transfer/idempotency/concurrency/fault/mandate/adapter/acceptance|
|Role A-owned 验收|9 PASS、11 A_SIDE_PASS、0 FAIL|共享项仍需 B/C 的编排、追问或同意证据|
|PostgreSQL 对账|5/5 valid|journal、transfer evidence、余额推导、幂等 hash、mandate action|
|其余业务/安全/恢复/沙箱|保持 NOT_RUN|不能用 A_SIDE_PASS 宣称全链路通过|
|PostgreSQL DDL|PostgreSQL 18.6 容器执行|Alembic migration、runtime/read roles、deferred journal trigger|
|浏览器视觉/移动端|未完成|原生浏览器检查时电脑锁屏；已提供本地预览供查看|

复现命令见 README 与 `services/mock-bank/README.md`。`results.local.json` 和 `outputs/role-a-acceptance.json` 是本机生成报告，Git忽略；每次运行重新写入。真实用户鉴权、真实银行、B 的授权/额度/预约、C 的 scope/consent 和部署沙箱仍未由 Role A 证明。生产基准测试位于 `tests/test_part_d.py`，不会从生产模块导入 `scripts/reference_engine.py`。

手算锚点：基准第13天购买最低452200分（第11天）；工资第17天而第13天买最低−187800分（第16天）；改第19天买最低412200分（第16天）。30天生活预算240000分，月末=900000+800000−350000−3000−6800−240000−600000=500200分。
