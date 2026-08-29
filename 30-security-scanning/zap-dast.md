# ZAP DAST

## 与前三个工具的根本区别

gitleaks / trivy / semgrep 扫的是仓库内容本身，任何仓库、任何时候都能跑。ZAP 不一样，它是 **DAST**（Dynamic Application Security Testing）——测的是服务跑起来之后的行为，前提是要有一个能接收 HTTP 请求的服务。**纯库、没有对外 HTTP 服务的仓库，ZAP 的三种扫描方式都用不上。**

## 三个打包脚本的实测差异

来自各脚本 `-h` 输出，不是记忆：

| | spider 默认时限 | `-a` 包含的规则 | 性质 |
|---|---|---|---|
| baseline | **1 分钟** | alpha **被动**规则 | 只被动观察 |
| full-scan | **无限制** | alpha **主动**+被动 | **真的发起攻击** |
| api-scan | 不爬，读 spec | alpha 被动 | 按 OpenAPI/SOAP/GraphQL 定向 |

## 触发矩阵

- **baseline**——应该自动化：部署 staging 后跑一次，或者定时
- **full-scan**——只能定时或手动：spider 无上限、真的发起攻击、会往表单里灌数据，**绝不能指向生产**
- **api-scan**——有 spec 时比 baseline 更准，按接口定向而不是靠爬虫发现

## Forgejo 触发器支持（全部实测）

| 触发器 | 支持情况 |
|---|---|
| `workflow_dispatch` + inputs | ✅ 支持——派发 API 返回 204，产生 `event=workflow_dispatch` 的运行 |
| `schedule` | ✅ 支持——`action_schedule_spec` 表登记了 cron 和 next 时间戳 |
| `workflow_run` | ❌ **实测未触发**——探针写了三种 workflow 名字、两种 types，之后跑两轮 ci，17 次运行 0 个该事件 |

**所以"部署成功后自动扫"不能用 `workflow_run`。** 替代方案三选一：

1. 作为部署 workflow 的最后一个 job（`needs: deploy`）——**推荐**，不需要跨 workflow 通信
2. 部署脚本结束时调 dispatch API
3. schedule 兜底，不追求"部署后立刻扫"

## Automation Framework（官方主推方向）

用 `-autorun <plan.yaml>` 跑一个声明式的 plan；`-autogenmin`/`-autogenmax`/`-autogenconf` 生成模板——这四个 flag 实测存在。三个打包脚本本质上是预制好的 plan（例如 `api-scan` 就是一个带 `openapi` job 的 plan）。

比命令行强在四处：

**1. `tests:` 断言——最重要。** `spider` job 可以挂一条统计断言：

```yaml
jobs:
  - type: spider
    parameters:
      maxDuration: 5
    tests:
      - name: "爬到的 URL 数量不能太少"
        type: stats
        statistic: "automation.spider.urls.added"
        operator: ">="
        value: 20
        onFail: error
```

这是 DAST 版的"已知坏样本"（参见 [00-principles.md](../00-principles.md) 第一条）。ZAP 最典型的失效是登录没成功、只爬到登录页、然后给一份很干净的报告——干净是因为什么都没扫到，不是因为没洞。用爬取 URL 数当哨兵，失效会主动报错，而不是安静地产出一份看起来正常的报告。`activeScan`/`passiveScan-wait` 还能断言特定告警的有无：

```yaml
tests:
  - name: "已修复的越权漏洞不允许回归"
    type: alert
    scanRuleId: <规则 ID>
    action: passIfAbsent
    onFail: error
```

这样可以锁定"已经修复的洞不许回归"。

**2. `alertFilter` 比 `.zap/rules.tsv` 精细得多。** 按 url/parameter/evidence 加正则匹配，把某条告警改判成 `False Positive`，可以限定只在某个路径下豁免：

```yaml
- type: alertFilter
  parameters:
    deleteGlobalAlerts: false
  alertFilters:
    - ruleId: <规则 ID>
      newRisk: "False Positive"
      url: "https://staging.example.internal/health.*"
      urlRegex: true
```

做基线分诊应该用这个，不要用命令行脚本自带的规则文件。

**3. `activeScan-policy` 让主动扫描不再是全有全无。** 按 `alertTags` 挑规则、按规则单独设 strength/threshold，可以做成分钟级的定向扫描：

```yaml
- type: activeScan
  parameters:
    policy: "injection-only"

- type: activeScan-policy
  parameters:
    name: "injection-only"
  policyDefinition:
    defaultThreshold: "off"
    rules:
      - id: <规则 ID>   # 例如 SQL 注入类规则
        threshold: high
        strength: high
      - id: <规则 ID>   # 例如 XSS 类规则
        threshold: high
        strength: high
```

**这纠正的是一个概念混淆**：`full-scan.py`（无 spider 上限 + 全量主动规则）不能进门禁，
不等于"任何主动扫描都不能限时"。`activeScan-policy` 让主动扫描不再是全有全无。

**但它仍然不进 PR 合入门。两个理由，都是硬的：**

1. **冷 PR 没有活 URL。** DAST 打的是跑起来的服务。一个还没被部署到任何地方的 PR，
   物理上没有扫描目标。要在 PR 上跑 DAST，前提是**每个 PR 都有独立预览环境**——
   那是另一整套基础设施，**我们没有，也没验证过**。
2. **超 PR 预算。** [`05-architecture.md`](../05-architecture.md) 定的是 PR CI
   **合计** ≤5 分钟（semgrep + trivy lockfile + 单测）。再加 5 分钟定向主动扫是
   翻倍，不是"踩线"。同一份文档里"慢的东西不进 PR 门禁"和"限时 5 分钟可以进门禁"
   自相矛盾——**以前者为准**。

**限时定向计划的正确挂载点是"预发已经起来"之后的 job，挡的是晋升生产，不是合并。**
这也是公司方案的规定（不挡冷 PR；`activeScan` 不进组织级模板）。

**4. 其它 job 类型**：`openapi`/`graphql`/`soap`/`postman`/`har` 导入现成接口定义；`spiderAjax`/`spiderClient`——现代 SPA 用传统 spider 爬不动，需要执行 JS 才能发现路由；`exitStatus`（CI 门禁接口，按 `errorLevel`/`warnLevel` 决定退出码）；`env.parameters.failOnWarning`/`continueOnFailure`（plan 级别的失败策略，决定一个 job 失败要不要影响后续 job）。

## 最小可用 plan

```yaml
env:
  contexts:
    - name: "app"
      urls:
        - "https://staging.example.internal"

jobs:
  - type: spider
    parameters:
      context: "app"
      url: "https://staging.example.internal"
      maxDuration: 5
    tests:
      - name: "爬取 URL 数量哨兵"
        type: stats
        statistic: "automation.spider.urls.added"
        operator: ">="
        value: 20
        onFail: error

  - type: passiveScan-wait
    parameters:
      maxDuration: 5

  - type: report
    parameters:
      template: "risk-confidence-html"
      reportDir: "/zap/wrk"
      reportFile: "zap-report"

  - type: exitStatus
    parameters:
      errorLevel: "High"
```

**没有那个 `tests` 哨兵，后面所有配置都可能是在给一份空扫描做精装修。** 报告好看不代表扫到了东西。

## 三个实操坑

1. 部署后先 curl 健康检查，确认服务真的起来了，再启动 ZAP——服务没起来 ZAP 会对着一个连接失败的目标跑完整个流程，产出一份没有意义的"干净"报告
2. 不配认证等于白扫——ZAP 只能看到登录页，报告"很干净"是因为什么都没扫到，不是因为没洞
3. 要能当门禁，必须先做基线分诊（用 `alertFilter` 标掉已知的误报/可接受项），不然第一次跑就会因为一堆噪音把门禁堵死

## 本环境特有的坑

ZAP 容器要能打到目标 URL。runner 在 compose 网络里，job 容器却在 DinD 的独立网桥上——和 `actions/checkout` 解析不到 forgejo 是同一类问题，修法参见 [20-ci-cd/README.md](../20-ci-cd/README.md)"已知的 CI 网络坑"一节。

---

## 实做记录：baseline 的退出码不能当判据（2026-08-29）

对一个**故意不设任何安全响应头**的 Express 应用跑 `zap-baseline.py`，汇总行是：

```
FAIL-NEW: 0   FAIL-INPROG: 0   WARN-NEW: 11   WARN-INPROG: 0   INFO: 0   IGNORE: 0   PASS: 56
```

命中的正是种下的那些：`Cookie No HttpOnly ×2`、`Cookie without SameSite ×2`、
`Missing Anti-clickjacking ×3`、`X-Content-Type-Options Missing ×3`、`CSP Not Set ×3`，
外加 `X-Powered-By` 泄露、`Permissions-Policy`、`COEP`。

**它们全是 WARN，没有一条 FAIL。** 但要说清楚退出码到底怎么算——这一点很容易搞错
（本文初稿就写错过，实测后更正）：

| 命令 | 退出码 | 说明 |
|---|---|---|
| `zap-baseline.py -t <url>` | **2** | 默认行为：**有 warning 就非零退出**，门禁会红 |
| `zap-baseline.py -t <url> **-I**` | **0** | `-I` = 不因 warning 返回失败 |

所以危险的不是 ZAP 的默认值，是 **`-I` 这个参数**：它看起来像个无害的降噪开关，
实际把整道门禁变成空壳——一个连 CSP、X-Frame-Options、HttpOnly 都没有的应用，
加了 `-I` 就是"过"。

> **凡是在 DAST 命令里看到 `-I`，都要问一句"那这道闸还挡什么"。**
> 要降噪应该用 `-c <rules.tsv>` 逐条豁免（有记录、可审查），
> 或者 AF plan 里的 `alertFilter`，**不是把整类结果一刀切成不失败**。

门禁接法三选一：默认退出码（最简单）、AF plan 的 `exitStatus.warnLevel`、
或者在 job 里自己断言：

```bash
for rule in "Content Security Policy" "Anti-clickjacking" "X-Content-Type-Options"; do
  grep -q "$rule" /tmp/zap.txt || { echo "没命中 $rule —— ZAP 没真打到应用"; exit 1; }
done
```

**这个断言是反向的**：应用故意有这些问题，**扫不出来才说明扫描器坏了**。
这就是 [00-principles](../00-principles.md) 第 1 条在 DAST 上的具体形态——
canary 不一定是一个仓库，也可以是"预期必须命中的一组规则"。

---

## 三种模式什么时候跑（实测校准）

关键区别**不是**被动/主动，是**怎么发现目标**：

| | 发现方式 | 规则 | 什么时候跑 |
|---|---|---|---|
| **baseline** | 爬 HTML 链接 | 只被动 | **每次部署预发**。分钟级，不发攻击载荷 |
| **api-scan** | **读 OpenAPI/GraphQL/SOAP spec** | 被动为主 | 目标是 API 时**必须**用它 |
| **full-scan** | 爬虫无上限 | 被动 + **主动** | **只能定时或手动**：大改版、新产品上线前、或夜间/每周 |

**api-scan 那条最容易漏**：REST API 没有 HTML 链接可爬，**爬虫对它几乎什么都发现不了**，
于是 baseline 报"干净"——干净是因为它没看到接口，不是因为没问题。
这是[名词详解](../01-glossary.md)里「DAST 报告很干净」陷阱的另一个成因：
不是没配认证，是**没配发现**。

**full-scan 绝不能进任何自动门禁**：主动扫描会真的提交表单、改数据，
对目标要有书面授权。要在门禁里做主动扫描，用 AF 的 `activeScan-policy`
限时限规则挂在预发那一步。

同一个演示应用实测（修完响应头之后）：

| | 规则数 | 结果 |
|---|---|---|
| baseline | PASS 64 | WARN 1 |
| **full-scan** | **PASS 140** | **FAIL 0 / WARN 1** |

主动扫描多跑了一倍多的规则。这个应用只有两个页面，几分钟就完；
真实应用是小时级，这就是它不能进门禁的直接原因。

## DinD 下给 ZAP 传配置文件：三个坑叠在一起

在 Forgejo Actions（runner + dind 边车）里跑 ZAP 并带 `-c rules.tsv`，
**连踩三次才通**。三个都不指向真正的原因：

| # | 现象 | 真正的原因 |
|---|---|---|
| 1 | `FileNotFoundError: /zap/wrk/.zap/rules.tsv` | `docker run -v <path>` 的 path 由 **dind 守护进程**解析，不是 job 容器里的路径。挂 `$PWD` 没有意义 |
| 2 | `Error response from daemon: Could not find the file /zap/wrk in container` | 镜像里**没有 `/zap/wrk`**（那是给 `-v` 用的挂载点），往未 `start` 的容器 `docker cp` 到不存在的目录会失败 |
| 3 | **打印 usage 然后退出**（看起来完全像参数写错） | `zap-baseline.py` 只要给了 `-c`，就把 `base_dir` 钉成 `/zap/wrk` **并要求它存在** |

解法是**命名卷**——卷由 dind 管理，两边都看得到，一次解决三条：

```bash
docker volume create zapwrk
docker run --rm -i -v zapwrk:/w alpine sh -c 'cat > /w/rules.tsv' < .zap/rules.tsv
docker run --rm --network dast-net -v zapwrk:/zap/wrk \
  ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py -t http://staging:3000 -j -c rules.tsv
```

### `rules.tsv` 必须至少三列

```
规则ID <TAB> 动作(IGNORE|INFO|WARN|FAIL) <TAB> 说明 [<TAB> URL正则]
```

只写两列会报 `Unexpected number of tokens on line - there should be at least 3`，
ZAP 以**退出码 3** 结束。退出码 3 是"配置错误"不是"扫描失败"，但门禁一样红——
**红了先看是不是配置问题，别直接去改应用。**

第三列就是理由。写清楚：一个没人看得懂理由的 `IGNORE`，和直接加 `-I` 没有区别，
只是分散成了很多行。

## 「零告警」的 DAST 门禁达不到，别去追

同一个应用一路收敛：

| 动作 | WARN 数 |
|---|---|
| 什么都不做 | 11 |
| 挂 `helmet()` | 5 |
| 补 COEP + Permissions-Policy | 3 |
| CSP 从 helmet 默认收紧到 `'self'` | 1（`10055` 从 ×8 降到 ×2） |
| 剩下的写进 `rules.tsv` 并说明理由 | **0，门禁绿** |

最后那条是**判断**不是妥协：剩余的 `10055` 是那些不回退 `default-src` 的指令
（frame / worker / font 之类），这个应用没有这些场景。**继续追零告警，
下一步就是给自己加 `-I`——那才是真正的失控。**

分层效果实测（同一条 `release` workflow，`promote` 用 `needs: dast`）：

| DAST | `promote` |
|---|---|
| failure | **一个 run 都没有** |
| success | success |

**合入门已经放行了（代码在 main 里），不代表可以上生产。** 这就是分层。

---

## 实测：baseline 打 API 服务 = 5% 覆盖率的假绿（2026-08-29）

在同一个本地 k3s 部署上，用**同一条命令**打两个服务，对照极其干净：

| 目标 | 类型 | 爬到 URL | 报告 | 实际路由数 | 覆盖率 |
|---|---|---|---|---|---|
| `web` | SPA（有 HTML） | 16 | `WARN-NEW: 8 / PASS: 59` | — | — |
| `control` | **纯 API** | **5** | `WARN-NEW: 1 / PASS: 66` | **101** | **≈5%** |

`control` 有 **101 条路由**，爬虫找到 **5 个 URL**，只报了 1 条通用告警
（`Storable and Cacheable Content`）。

**这份报告看起来比 web 的还漂亮——WARN 更少、PASS 更多。**
拿它说"API 服务很干净"是完全错的：它不是干净，是**根本没被扫**。

> **这是"绿色的扫描器什么都不说明"在 DAST 上最典型的形态。**
> 而且它比扫描器坏掉更隐蔽——扫描器工作正常、报告格式完整、退出码有意义，
> 唯独**目标发现率只有 5%**，而这个数字不在报告里。

### 判断"扫到了没有"的两个硬指标

报告顶上那行 `Total of N URLs` 才是关键，不是 WARN 数：

1. **`Total of N URLs` 对不对得上你的实际接口数？** 差一个数量级就说明爬虫没进去。
2. **PASS 数高不代表覆盖好**——没爬到的路径，所有规则都算 PASS。

### SPA 也有同样的问题，只是没那么极端

`web` 那次爬到 16 个 URL。它是个 SPA——**传统爬虫跟不了客户端路由**，
所以 16 个只是入口和静态资源，不是真实页面数。要爬 SPA 得用
`spiderAjax` / `spiderClient`（AF 里的 job），会执行 JS 才能发现路由。

**结论：baseline 的爬虫适用范围比想象中窄。** 服务端渲染的多页应用它够用；
SPA 要加 AJAX 爬虫；**纯 API 只能靠 spec（`api-scan`），爬虫在那里等于没有。**

### 没有 OpenAPI spec 的 API 怎么办

多数内部系统没有 spec，但**未必没有等价物**。实测那个仓就有：
`contract/api/*.routes.json`——为前端契约测试生成的路由表，
每条带 `method` / `path`（含 `{id}` 参数）/ `pathParams` / `requestBody` / `responseType`，
共 103 条。**这正好是 OpenAPI 需要的全部字段**，转换是机械的。

所以在说"我们没有 spec，做不了 API DAST"之前，先找一遍：

- 前端的 API 客户端层（常有生成的类型和路由表）
- 契约测试 / 金标文件
- 路由注册代码（能静态提取的话）
- 网关/反代的路由配置

**有路由表就能造 spec，有 spec 才谈得上 API 的 DAST。**
