# 仓库模板

开库即带门禁。两种模板，**分开是必须的**——给没有 workflow 的仓套 status check
会让它永久不能合（fail-closed，见 [20-ci-cd](../20-ci-cd/README.md) §三）。

| 模板 | 给谁 | 分支保护 |
|---|---|---|
| [`template-service/`](template-service/) | 有 CI 的应用仓 | 禁直推 + approvals≥1 + `status_check_contexts:["*"]` |
| [`template-docs/`](template-docs/) | 文档仓、纯配置仓 | 禁直推 + approvals≥1，**不开 status check** |

## 为什么是"复制"而不是"可复用 workflow"

方案 §8.4 的设计是把门禁集中成可复用 workflow，业务仓只 `uses:` 它——**那个设计
在 Forgejo 16.0.3 上跑不通**。实测：

| 被调用方位置 | 结果 |
|---|---|
| 用户名下的仓 | ✅ 正常展开并执行 |
| **org 名下的仓** | ❌ `expanding reusable workflow failed to access user <org>: user does not exist` |

完全相同的 workflow，唯一变量是被调用方的 owner 类型。而方案要求 platform 仓在
org 下（§6.2 禁止个人用户仓库作生产源），两条规矩在这个版本上打架。

**失败还是静默的**：run 一个都不创建，PR 页面和 API 都看不出异常，只有服务端日志
（`jobparser.Parse: invalid workflow`）里有。看不到 run 就以为"还没跑"，实际是永远不会跑。

所以现阶段只能复制。**代价要认**：门禁散在 N 个仓里，改 gitleaks 版本要改 N 遍——
这就是我们在文档里治了一整天的"单一真相源"问题，换到了 CI 配置上。缓解办法是加一条
漂移检查（对比各仓的 `ci.yml` 与模板的差异），不是假装没这回事。

**升级重测**：Forgejo 升大版本后重跑这个实验；如果 org 侧修好了，改回可复用 workflow，
这一节和模板都要跟着改。

## 用法

Forgejo 的模板仓功能：把 `template-service/` 的内容推成一个仓，在
`Settings → Repository → Template` 勾上，之后 `New Repository` 可以选它作模板。

新仓建完还要**手工配分支保护**（模板不带保护规则）。必检名从
`GET /repos/{o}/{r}/commits/{sha}/statuses` 的 `context` 字段**逐字抄**——
它的格式是 `<workflow 名> / <job id> (<事件>)`，猜名字会把分支锁死。
