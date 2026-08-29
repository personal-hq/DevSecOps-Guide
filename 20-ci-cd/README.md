# CI/CD

自建 CI Runner 的隔离取舍、分支保护的实测边界、网络踩坑、标签命名机制，以及四个常见风险的应对优先级。

> **本文所有实测结果绑定这两个版本**：**Forgejo 16.0.3**（`16.0.3+gitea-1.22.0`）+
> **forgejo-runner 13.0.0**。状态码、事件行为、ephemeral 语义都可能随大版本变。
> **重测触发 = Forgejo 或 Runner 升大版本**（16→17、13→14）——升完把本页的实测表
> 重跑一遍再用，不要直接沿用。

## 一、Runner 隔离——轴选对

常见错误是按"贡献者可信度"分层——那是 GitHub 公开仓库的思维，防的是陌生人提交恶意 PR。内部服务器不是这个问题，正确的轴是**"job 里跑的是谁的代码"**，答案永远是：第三方依赖的代码。即使 100% 员工可信，`npm install` 仍然会执行依赖的 postinstall 脚本，而这个脚本握着 CI token。

| 方案 | 隔离了什么 | 没隔离什么 | 成本 |
|---|---|---|---|
| 挂宿主 docker.sock | 无 | job = 宿主 root | 最低 |
| DinD 边车 | 宿主其他容器和卷 | 并发 job 之间；dind 自身 privileged | 低 |
| ephemeral | 跨 job 残留（token 复用、缓存投毒） | 单次运行内隔离级别不变 | 中，见下 |
| LXC | 每 job 独立命名空间 | — | 高：无镜像缓存、不支持服务容器 |
| 独立 VM | 真隔离 | — | 最高 |

**DinD 和 ephemeral 是正交的**：DinD 挡横向（同机其他容器/卷不被碰），ephemeral 挡纵向（job 之间不留 token、缓存这些残留）。建议内部服务器**DinD + 按组织收窄作用域**，LXC 不要——对内部团队是净亏损：换来的命名空间隔离，代价是镜像缓存和服务容器都没了。

## 二、ephemeral 的真实成本（实测）

两个发现，都是实测踩出来的，不是文档看出来的。

**1. `forgejo-runner daemon` 不支持 ephemeral。** 实测报错原文：

```
Error: connection "acme" requires an ephemeral runner, which is not supported in daemon-mode
```

配套命令是 `one-job`——领一个 job、跑完退出，不是常驻 daemon。

**2. 改用 `one-job` 后跑通一个 job，然后 runner 永久注销自己**，实例列表里消失。容器重启用同一个已失效的 UUID/token 重新注册必然失败：

```
fail to invoke Declare  error="unauthenticated: unregistered runner"
```

**结论：`restart: unless-stopped` 完全不成立。** ephemeral 的真实形态是每跑一个 job 前重新 `forgejo-cli actions register` 生成新 UUID/token，需要一个 supervisor 脚本负责这个循环。这不是一行配置，是一个要维护的编排组件，大致形状（具体注册参数按环境填）：

```bash
while true; do
  TOKEN=$(forgejo-cli actions register --scope "<org>" --labels "<labels>")
  forgejo-runner --config runner-ephemeral.yaml one-job --token "$TOKEN"
  # one-job 跑完一个 job 就退出、该 UUID 已被注销，回到循环头重新注册
done
```

## 三、分支保护——全部实测

这一节是本文档最有价值的部分，每条都是真实调用 API 或点过界面验证的，不是读文档得出的推断。

| 行为 | 实测结果 |
|---|---|
| 作者批准自己的 PR | ❌ `422 approve your own pull is not allowed` |
| write 协作者 `force_merge=true` | ❌ `405 Does not have enough approvals` |
| **owner/管理员 `force_merge=true`** | ✅ **200 绕过成功** |
| 同上，`apply_to_admins=true` | ✅ **200 仍然绕过** |
| owner/管理员删除保护规则 | ✅ `204` 成功 |
| `protected_file_patterns` 直推 | ❌ `403 path is protected and can not be changed` |
| `protected_file_patterns` PR 合并 | ❌ `405 Changed protected files` |
| `status_check_contexts:["*"]` 且仓库无 CI | ❌ `405 Not all required status checks successful`（**fail closed，永久卡死**，不是真空通过） |
| 同上，加一个能过的 workflow | ✅ 200 合并成功 |
| CODEOWNERS 自动请求审查 | ✅ **完全可用**（此前判定"未复现"是环境配置错误，见下方专节） |
| 必检 context 写 job 名（`gate-check`） | ❌ `405 Not all required status checks successful`——**名字对不上 = 永久卡死**，见下 |
| 同上，改成实际上报名 | ✅ 200 合并成功 |
| 必检 job 被 `paths-ignore` 跳过 | ❌ `405 Not all required status checks successful`（跳过的 job **从不上报 status**） |
| `pull_request_target` 事件 | ✅ **支持并触发**（所以这条攻击面在 Forgejo 上是活的） |
| 标签保护，白名单内用户打 `v*` | ✅ 201 |
| 标签保护，白名单外 write 协作者打 `v*` | ❌ `422 user not allowed to create protected tag` |

> 分支保护完整约束 writer，对 owner/管理员是**建议性的**。管理员可以 `force_merge`，也可以直接删掉规则，`apply_to_admins` 两者都挡不住。所以**"谁是仓库管理员"是比任何保护规则配置都更重要的控制点。**

### 必检 context 的名字不是 job 名

Forgejo 上报的 context 是 **`<workflow 名> / <job 名> (<事件>)`**：

```
保护规则里写的：  ['gate-check']
实际上报的：      'gate / gate-check (pull_request)'
```

**写错的后果不是"门禁失效"，是"永久无法满足"**——job 明明跑成功了，合并照样 405。
改成实际上报名后立刻放行。

这和 `["*"]` 的行为是同一个设计：**fail closed**。好处是不会静默放行；代价是
**改 workflow 名或 job 名会立刻锁死该分支**，而错误信息不会告诉你名字对不上。

更刺眼的一种：**workflow 文件没写 `name:` 时，前半截是空的**，context 变成以斜杠开头的
`/ no-checkout (push)`——凭直觉绝不可能猜到要往规则里填这个。

取实际名字：`GET /repos/{owner}/{repo}/commits/{sha}/statuses`，逐字抄 `context` 字段。

同一个机制还有一个推论：**必检 job 不能用 `paths-ignore`**。被跳过的 job 从不上报
status，于是"只改文档"的 PR 变成永远合不了——不存在"跳过却算通过"这种放行。

### 管理员绕过为什么是"静默"的——两种静默，第二种更糟

上表说管理员能 `force_merge`、能删规则，所以只能靠审计兜底。**那审计到底看得到什么？**
实测（对比 `action` / `comment` / `notice` 三张表的前后水位）：

**一、删除保护规则：完全无痕。**

`DELETE /repos/{o}/{r}/branch_protections/main` → `204`，之后 `action` 零新增、
`notice` 零行，`protected_branch` 表里那行**直接消失**。没有任何记录说这条规则存在过、
谁删的、什么时候删的。

**二、`force_merge`：有痕，但和正常合并一模一样。**

| 记录位置 | `force_merge` 留下的 | 正常合并留下的 |
|---|---|---|
| `action` 表 | op_type 7（开 PR）/ 5（push）/ 11（合并 PR） | 一样 |
| `comment` 表 | type 29 + type 28 | 一样 |
| `notice` 表 | 0 行 | 0 行 |
| PR API | `merged: true`、`merged_by: <人>`，**没有任何含 `force` 的字段** | 一样 |

> ⚠️ `comment` 里那个 `is_force_push` 字段指的是 **git 强推**，不是强制合并。名字很像，
> 拿它当"有没有绕过门禁"的判据会得到错误答案。

审计日志说的是「forgejo-admin 合并了 PR #23」——**门禁全绿时这句话长得一模一样。**
这才是"静默"的真正含义：不是没有记录，是**记录里没有"发生了绕过"这个事实**。

**推论（决定你要建什么）**：定期轮询 `/branch_protections` 存快照做差分，能抓到第一种；
**抓不到第二种**——`force_merge` 之后规则原封不动地还在，快照没有任何变化。

要发现 `force_merge`，只能**事后重算这次合并当时该不该被放行**：取 PR 的
`/reviews` 数、取 head sha 的 `/statuses`，再对着规则重跑一遍判定，和"它已经合了"对比。
**这是要自己写的一段东西，不是配一条告警。** 谁写这条 §审计 要求，谁就得先认这个成本。

### CODEOWNERS：此前的"未复现"是环境配置错误

**Forgejo v16 上 CODEOWNERS 完全可用。** 之前测试没触发不是平台限制，是自建环境的配置问题——原因是同时存在三个 CODEOWNERS 文件，且根目录那个用了 glob 语法。清理成单一文件 + Go 正则后立即生效。

官方文档（`/docs/v16.0/user/collaboration/pull-requests-and-git-flow/`）：

- **位置**：仓库根目录、`docs/` 或 `.forgejo/`
- **语法**：**Go 正则**，不是 glob
- **触发**：变更文件路径匹配非否定规则时，自动请求对应用户/团队审查

实测（**仓库里只有根目录一份** `CODEOWNERS`，内容 `^secrets/.*  @renovate`；`.gitea/`、`.forgejo/`、`docs/` 三处均已确认不存在）：

| 验证渠道 | 结果 |
|---|---|
| API `requested_reviewers` | `['renovate']` |
| API `/reviews` | `[('renovate', 'REQUEST_REVIEW')]` |
| PR 页面 HTML | 出现 `codeowner` 10 处 |
| 反向对照：不碰 `secrets/` 的 PR | 无自动请求，未误伤 |

**⚠️ 两个坑叠在一起，才会误判成"不支持"**：

1. **只放根目录一份。** Forgejo 出于上游 Gitea 兼容还认 `.gitea/CODEOWNERS`，`docs/` 和 `.forgejo/` 也是合法位置——但这不是"四个选项"，是**四个制造冲突的机会**。规范直接写死根目录，其余一律不许出现。
2. **语法是 Go 正则，不是 glob。** 根目录那份如果写成 `src/**`，规则静默零匹配、不报错，看起来就像整个功能没做。

第一次判定"本实例不支持"就是这两条同时踩：三个 CODEOWNERS 文件并存，且根目录用了 glob。清成单一根文件 + 正则后立刻生效。

**更正一个下错的结论。** 原判断"Forgejo 没有 GitHub 那种'改动这些文件则审批数 +1'的原生能力"字面成立，但据此得出"路径级强制审查做不到"是**错的**。不需要"+1"，配 `block_on_official_review_requests: true` 就能等效强制。实测完整闭环：

1. PR 改动 `secrets/final.env` → CODEOWNERS 自动请求 `renovate` 审查（`REQUEST_REVIEW`）
2. 非 code owner 的 owner 账号批准（满足 `required_approvals=1`）→ 合并被拦：`405 not allowed to merge [reason: There are official review requests]`
3. code owner `renovate` 批准 → 合并成功，`200`

（2026-08-29 在"只有根目录一份 CODEOWNERS"的干净状态下重跑，三步结果完全一致。）

**机制不是把审批数从 1 提到 2，而是未完成的正式审查请求会阻塞合并。** 效果等价于路径级强制审查。

### 推荐规则集

```json
{
  "enable_push": false,
  "required_approvals": 1,
  "dismiss_stale_approvals": true,
  "block_on_rejected_reviews": true,
  "block_on_outdated_branch": true,
  "enable_status_check": true,
  "status_check_contexts": ["*"],
  "apply_to_admins": true
}
```

逐条：

- `enable_push: false`——关掉不经 PR 直接 push 的口子，开着的话后面所有规则都无意义
- `required_approvals: 1`——至少一人审查，设 0 等于没有门槛
- **`dismiss_stale_approvals: true`——这条最关键。** 不开的话：提一个干净的 PR → 拿到审批 → 再悄悄推一个恶意提交 → 直接合并，必需审查完全形同虚设，因为审批是对着旧代码给的
- `block_on_rejected_reviews: true`——有人明确 Request Changes 时不让合并
- `block_on_outdated_branch: true`——分支落后主干时不让合并，避免"审查的代码"和"实际合并的代码"不是同一份
- `enable_status_check` + `status_check_contexts: ["*"]`——见下面的运维陷阱
- `apply_to_admins: true`——挡不住 `force_merge`，但至少让管理员的"正常合并"路径也过一遍检查

### `["*"]` 的运维陷阱

不能组织级统一套用。任何没有 CI 的仓库会被这条规则直接锁死——没有 status check 就永远满足不了"全部通过"，然后有人来要求关掉整条保护规则。**新仓库先给一个 trivial workflow，再开保护**，顺序反了就会被当成"这功能不能用"。

### 三条流程约定（技术管不了，写进工程规范）

**敏感路径双人审**：

| 手段 | 效果 | 代价 |
|---|---|---|
| **敏感代码拆独立仓** + `required_approvals: 2` | ✅ **首选**。边界由权限系统强制，同时隔离 CI、secrets、runner 作用域 | 要动组织结构和依赖关系 |
| CODEOWNERS + `block_on_official_review_requests` | 拆不动的大仓用这个。按路径自动请求负责人，未审完不能合并（实测闭环，见上） | 见下方警告 |
| 全仓 `required_approvals: 2` | 敏感目录被覆盖 | 普通改动也变慢 |
| `protected_file_patterns` | **冻结**该路径（直推和合并都拒） | 正规 PR 也改不了，只适合几乎永不改的文件 |

> ⚠️ **CODEOWNERS 能用，不代表它该当首选。** 我们这两个仓拆无可拆，所以用了它——
> 那是实例约束，不是排序依据。拆仓更好的理由不是 CODEOWNERS 不好用，而是：
> 仓边界由权限系统强制，而 CODEOWNERS 是**被保护仓自己内部的一个正则文件**；
> Go 正则写成 glob 会**静默零匹配、不报错**——我们据此误判过"Forgejo 不支持 CODEOWNERS"；
> 拆仓还顺带隔离了 CI、secrets 和 runner 作用域，CODEOWNERS 一个都不隔离。
>
> **不要因为一个手段被验证可用，就把它排到首选。**

**禁止纯 LGTM**：平台无此开关，空批准照样计入 `required_approvals`。写进工程规范 + 抽查，不当平台红线。

**不允许自己审自己**：平台已强制作者不能 Approve（见上表 422），但**`required_approvals` 为 0 时等于没有这条规则**——这条防线依赖审批数门槛本身开着才有意义。

> 配好之后按 [`gate-qa-checklist.md`](gate-qa-checklist.md) 逐条自查——那份清单按**绕过路径**组织，覆盖 PR 之外的口子（标签、发版、`pull_request_target`、忽略文件）。

## 四、已知的 CI 网络坑

job 容器由 DinD 守护进程创建，落在独立网桥上，解析不到 compose 服务名 → `actions/checkout` 报 `Could not resolve host`。

修法：固定子网 + 给 forgejo 静态 IP + runner 配置 `container.options: "--add-host=forgejo:<IP>"`。

**改网络时两处必须同步改**——固定 IP 一变，`--add-host` 里的地址跟着变，漏改一处症状照样复现。

## 五、标签命名

标签是"名字 → 镜像"的映射，名字不代表发行版。`ubuntu-latest` 可以是指向 Debian 镜像的**兼容别名**——从 GitHub 抄的 workflow 都写这个，照抄不代表跑在 Ubuntu 上。

镜像**必须带 node**：Forgejo 用容器里的 node 执行 JS action（`actions/checkout` 本身就是），裸 debian/ubuntu 镜像会失败。

## 六、四个风险的解决方案

按发生概率排序，容器逃逸排最后不是因为不重要，是因为前三个更容易先出事。

1. **CI token 作用域过宽** → 按组织注册 runner 而非全局（`--scope <org>`）。**最好修，优先做。**
2. **secrets 进日志** → 三层应对：工具层（逐个确认脱敏行为）+ 平台层（压缩日志保留期）+ 流程层（发现即轮换）
3. **依赖投毒** → Renovate 锁版本 + `npm ci --ignore-scripts` + 构建产物与发布分离
4. **容器逃逸** → 概率最低，DinD 现状可接受

## 七、「接受 ≠ 生效」——三处写进去不报错也不干活的配置

Forgejo 上有一类特别难发现的失败：配置**被接受**（API 返回 2xx、workflow 正常跑），
但**不产生任何效果**，也不给任何警告。踩过三次，形态一样，值得单独成节。

### 1. `permissions:` 不收回自动 token 的写权限

同一个 workflow 两个 job，唯一差异是 job 级 `permissions`，都用自动 token
往**非保护分支**推一个提交：

| job | YAML | 结果 |
|---|---|---|
| `restricted` | `contents: read` | ✅ 分支建出来了 |
| `control` | `contents: write` | ✅ 分支建出来了 |

两条分支、两个不同 commit，**`contents: read` 那个照样推成功**。对照组证明推送
通路本身没问题，所以不是测法问题——**这个键被解析、被忽略**。

> 注意判据：两个 job 的 Actions 状态都是 `success`，但那只是 shell 退出码。
> **决定性证据是两条分支都真的存在**，不是 job 绿了。

**收回写权限的是保护分支，不是 YAML。** 这个键可以留着当意图注释，但**不要对研发说
"写了 permissions 就安全"**。升 Forgejo 大版本后用同一组对照重测一次。

### 2. 不支持的 webhook 事件被静默丢弃

给 webhook 加一个 Forgejo 不支持的事件名，**API 返回 201，不报错，然后把它扔掉**：

```
POST /repos/{o}/{r}/hooks
  events = ["branch_protection", "repository", "push", "release"]
  → 201 Created

GET 同一个 hook
  → events = ['push', 'repository', 'release']      ← branch_protection 没了
```

随后连改两次分支保护规则（两次都 200），`hook_task` 表**一条都没排**。
对照组推一个提交，立刻排了 2 条 push task——所以不是测法问题，是**真的没有这个事件**。

> **"接受"不等于"生效"。** 这和 `permissions:` 是同一个失败模式：写进去、被接受、
> 不报错、不干活。**验收方法**：创建 hook 之后 `GET` 回来比对 `events` 数组，
> 少了哪个就是哪个不支持。

**所以"分支保护被关掉"这类告警在 Forgejo 上没有推送通道**，只能轮询（见上一节）。

### 3. Webhook 默认拒绝私网地址——SIEM 收不到且静默失败

投递失败原文：

```
Delivery: Post "http://172.28.0.1:9999/": dial tcp 172.28.0.1:9999:
webhook can only call allowed HTTP servers (check your webhook.ALLOWED_HOST_LIST
setting), deny '172.28.0.1(172.28.0.1:9999)'
```

`app.ini` 里没有 `[webhook]` 段时走内置默认，**私网/回环地址一律拒绝**（防 SSRF，
默认是对的）。但内部 SIEM、日志收集器、告警网关**基本都在私网**——不显式加白就全部投递失败。

失败**不会**出现在仪表盘或通知里，只在 hook 的投递历史（`hook_task.response_content`）
里看得到。配完 webhook 一定要去翻一次投递记录，别看到"hook 创建成功"就以为通了。
