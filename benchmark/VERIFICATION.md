# 本次验证记录

验证日期：2026-10-27（Asia/Hong_Kong）。离线参考结果与 Role A 模拟银行分组报告；不代表真实银行或完整 B/C 端到端成绩。

|检查|实际结果|范围|
|---|---|---|
|数据生成|3839标准行，3963原始行，124重复|固定种子，两年历史|
|参考分析对齐|180/180|数值和精确证据ID|
|现金流对齐|30/30|全部逐日余额、最低值、日期、可行性|
|unittest|12/12|SHA256、原始导入去重、逐账户对账及历史非负、退款关联、参考查询主体隔离、枚举注入拒绝、范围、状态过滤、空结果、时区边界、手算现金流锚点|
|原型JS smoke|7页面、30情景、工资延期交互通过|Node VM运行时检查；不含浏览器渲染|
|Role A pytest|88项通过|PostgreSQL schema/reset/read/transfer/idempotency/concurrency/fault/mandate/adapter/acceptance|
|Role A-owned 验收|9 PASS、11 A_SIDE_PASS、0 FAIL|共享项仍需 B/C 的编排、追问或同意证据|
|PostgreSQL 对账|5/5 valid|journal、transfer evidence、余额推导、幂等 hash、mandate action|
|其余业务/安全/恢复/沙箱|保持 NOT_RUN|不能用 A_SIDE_PASS 宣称全链路通过|
|PostgreSQL DDL|PostgreSQL 18 容器执行|Alembic migration、runtime/read roles、deferred journal trigger|
|浏览器视觉/移动端|未完成|原生浏览器检查时电脑锁屏；已提供本地预览供查看|

复现命令见 README 与 `services/mock-bank/README.md`。`results.local.json` 和 `outputs/role-a-acceptance.json` 是本机生成报告，Git忽略；每次运行重新写入。真实用户鉴权、真实银行、B 的授权/额度/预约、C 的 scope/consent 和部署沙箱仍未由 Role A 证明。

手算锚点：基准第13天购买最低452200分（第11天）；工资第17天而第13天买最低−187800分（第16天）；改第19天买最低412200分（第16天）。30天生活预算240000分，月末=900000+800000−350000−3000−6800−240000−600000=500200分。
