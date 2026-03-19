## TeaBuy 后端完善计划（面向 HMOS 前端联调，端到端下单优先）

### 1. 简要总结
基于现状扫描结果：
1. 前端工程 `/Users/chandyoung/Projects.localized/teabuy-hmos` 当前真正调用后端的核心仅有 `POST /auth/login` 与 `GET /home`，其余电商页多为本地状态和静态数据，多个 `Repository/UseCase/VM` 文件为空。
2. 后端工程 `/Users/chandyoung/Projects.localized/teabuy-backend` 已有完整雏形（购物车、订单、支付 mock、退款、地址、首页配置），但在安全性、契约稳定性、可观测性、管理员权限、种子数据与测试覆盖上还不够“可长期演进”。
3. 本计划按你确认的策略执行：  
`端到端可下单优先`、`后端兼容前端模型`、`保留 mock + 完整状态机`、`新增管理员鉴权`、`提供 seed 脚本`、`基础可观测`。

### 2. 目标与完成标准
1. 在不破坏现有前端页面结构的前提下，后端提供完整可联调交易链路：登录 -> 首页 -> 商品 -> 购物车 -> 结算 -> 下单 -> mock 支付 -> 订单状态流转 -> 退款。
2. 所有面向前端的接口返回稳定、文档化的字段，避免前端依赖隐式默认值。
3. 管理接口必须有明确权限隔离，普通用户无法调用发货、退款审核、首页运营配置接口。
4. 具备可重复初始化的联调数据能力（seed），并有可排障的日志与请求追踪。
5. 自动化测试覆盖关键成功路径与失败路径，达到“改动可回归”。

### 3. 对外接口与契约改造（兼容优先，不做破坏性删除）
1. 统一响应保持 `{code,message,data}`，新增统一错误结构扩展字段：`requestId`, `details`（可选）。
2. 鉴权相关：
   - 保持 `POST /api/v1/auth/login`。
   - 新增 `POST /api/v1/auth/register` 结果字段补齐前端常用信息（user 简要对象）。
   - 新增 `POST /api/v1/auth/refresh` 校验 refresh token 类型与版本（支持会话失效）。
   - 新增 `POST /api/v1/auth/logout` 支持 refresh 版本递增。
3. 商品与列表：
   - `GET /api/v1/catalog/products` 返回字段补齐：`id,name,subtitle,imageUrl,priceCent,priceText,marketPriceCent,soldCount,badgePrimary,badgeSecondary,status,stock`。
   - `GET /api/v1/catalog/products/{id}` 返回可直接驱动商品详情页的聚合字段：主图、轮播图、规格列表、库存、服务标记、推荐列表。
4. 购物车：
   - 保持现有 `GET/POST/PATCH/DELETE /api/v1/cart/items` 与批量选中接口。
   - `GET /api/v1/cart` 增补前端可直接渲染字段：`productName,subtitle,imageUrl,priceText,badges,subtotalText`。
5. 结算与订单：
   - `POST /api/v1/orders/preview` 保持并补齐：`items[]`,`subtotalCent`,`shippingCent`,`discountCent`,`payableCent`,`addressRequired`。
   - `POST /api/v1/orders` 保持 `Idempotency-Key` 必填，返回 `orderNo,status,totalCent,paymentRequired`。
   - `GET /api/v1/orders/{orderNo}` 增补字段：`statusTimeline`, `address`, `priceSnapshot`, `canCancel`, `canPay`, `canRefund`, `canConfirmDelivery`。
   - `GET /api/v1/orders` 支持分页和状态筛选：`?status=&page=&pageSize=`。
6. 支付与退款（mock）：
   - 保持 `POST /api/v1/payments/mock/create` 与 `callback`。
   - `callback` 增加签名/来源最小校验（即便 mock 也做防误触机制）和幂等处理。
   - 退款接口保持，新增 `GET /api/v1/refunds/{id}`，并在审批时写入审核人和时间。
7. 地址/个人中心/通知：
   - 地址接口保持，新增“读取默认地址”便捷字段或端点（用于结算页首屏）。
   - `GET /api/v1/me/overview` 补齐未读、订单分状态计数。
   - 通知保留未读计数与一键已读，新增分页列表接口。
8. 首页与运营配置：
   - 保持 `GET /api/v1/home` 和 `/api/v1/internal/home/*-config` 结构。
   - 明确 `updatedAt` 语义（Unix 秒）并保证变更即递增，服务前端图片缓存版本策略。

### 4. 权限与安全改造
1. 引入角色模型：`users.role`（`user`/`admin`），默认 `user`。
2. 新增管理员鉴权依赖，以下接口仅 admin 可调用：
   - `/api/v1/internal/*`
   - `/api/v1/orders/{orderNo}/ship`
   - `/api/v1/refunds/{refundId}/approve`
   - `/api/v1/refunds/{refundId}/reject`
3. 认证增强：
   - access/refresh token 区分类型并严格校验。
   - refresh token 与 `user_sessions.refresh_version` 绑定，logout 后旧 refresh 失效。
4. 输入校验补强：
   - 数量、评分、分页参数、状态枚举、ID 格式统一校验。
   - 统一 4xx 业务错误码表。

### 5. 数据模型与迁移计划
1. 新增或调整字段：
   - `users.role`
   - `payments.callback_no`, `payments.callback_payload`, `payments.updated_at`
   - `refunds.reviewed_by`, `refunds.reviewed_at`, `refunds.reject_reason`
   - `orders.updated_at`
2. 新增审计表：
   - `order_status_logs(order_id,from_status,to_status,operator_id,operator_role,reason,created_at)`
3. 索引优化：
   - `orders(user_id,status,created_at desc)`
   - `payments(order_id,created_at desc)`
   - `refunds(user_id,status,created_at desc)`
4. Alembic 迁移拆分为可回滚小步提交，避免一次大迁移风险。

### 6. 可观测性与运行保障
1. 每个请求生成/透传 `X-Request-Id`，写入日志并回传响应头。
2. 结构化日志最小字段：`timestamp,level,requestId,path,method,userId,role,statusCode,latencyMs,errorCode`。
3. 核心业务埋点：
   - 下单创建成功/失败
   - 支付回调处理成功/失败
   - 退款申请/审核
   - 订单超时取消任务执行结果
4. 异常处理保持统一出口，避免泄露内部堆栈给客户端。

### 7. 联调 seed 与环境策略
1. 新增 seed 命令（例如 `python -m app.scripts.seed_dev`）：
   - 初始化分类、商品、SKU、媒体、首页模块
   - 初始化一个 admin 账号与若干普通用户
   - 初始化演示地址、购物车、订单样本
2. 支持幂等 seed（重复执行不会产生脏重复）。
3. 提供 `.env.example` 脱敏模板，移除真实凭据；联调环境用独立数据库。

### 8. 测试计划（必须落地）
1. 单元测试：
   - 定价计算、运费阈值、状态机流转、权限判断、token 校验。
2. 集成测试（SQLite/测试库）：
   - 登录、首页读取、购物车增改删、下单幂等、库存扣减/回补、支付回调、退款审核。
3. 权限测试：
   - 普通用户调用 admin 接口必须 `403`。
4. 回归测试：
   - 现有 `health`、`order_flow` 用例保留并扩展。
5. 契约测试：
   - 为前端关键接口建立 JSON 结构断言，防字段回归。

### 9. 实施里程碑（按顺序）
1. 里程碑 A（基础治理）：
   - 错误模型统一、requestId、角色字段迁移、admin 鉴权框架。
2. 里程碑 B（交易链路加固）：
   - 订单/支付/退款状态机与幂等完善，库存一致性补强。
3. 里程碑 C（前端契约补齐）：
   - 商品/购物车/订单详情返回字段补齐，保证前端可直接消费。
4. 里程碑 D（运营与种子）：
   - internal 配置鉴权、seed 脚本、联调文档。
5. 里程碑 E（测试与发布）：
   - 自动化测试补齐、预发布验证、上线检查清单。

### 10. 验收场景（上线前必须全部通过）
1. 普通用户可完整完成一次下单并成功支付，订单状态正确流转到 `COMPLETED`。
2. 订单取消、超时取消、退款通过都会正确回补库存，且不会重复回补。
3. 同一 `Idempotency-Key` 重试不会创建重复订单。
4. 普通用户无法调用任何 admin 接口。
5. 首页模块配置更新后，客户端按 `updatedAt` 刷新内容。
6. seed 在空库和非空库都可安全执行。
7. 关键接口失败时可通过 `requestId` 快速追踪日志。

### 11. 明确假设与默认值
1. 本轮不接入真实支付渠道，只做 mock 支付的工程化增强。
2. 前端短期仍以现有页面结构为主，后端优先做“兼容型增强”。
3. 管理端暂不单独开发 UI，先通过受保护接口满足运维/运营能力。
4. 数据库继续使用现有 SQLAlchemy + Alembic 体系，不引入新 ORM/框架。
5. 发布目标环境仍以当前 Vercel + 数据库配置方式为基础。
