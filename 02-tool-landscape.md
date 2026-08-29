# 工具全景：开源与商业选项

结论先行：**我们当前的五件套（Semgrep / ZAP / Trivy / Renovate / Gitleaks）在各自类别里
不是随手抓的，但每个都有明确的替换触发条件**——本文把这些条件写清楚，另外把候选清单里
几个会咬人的许可证坑标出来。

数据抓取时间：**2026-08-29**。所有开源项目的 Stars / 最后推送 / 是否 archived
都是当天用 GitHub API 实测的，不是记忆。查不到或验证失败的项目不进表格，会在正文说明。
商业产品**不做**功能或价格验证——销售页背后的东西会变，本文只写方向。

> **这些数字只对抓取日成立。** Stars 每天变，许可证和 archived 状态也会变。
> **重测触发 = 你要引用某一行的 star / 许可证 / 活跃度去做决策之前**，当场重查一次，
> 不要拿这张表当长期事实。

## 验证状态

本文所有开源项目的**许可证、star 数、最后推送时间、是否归档**均通过 GitHub API 实查，
非凭记忆。其中五条关键结论（Bearer 非 OSI、sonar-java 许可证、三个项目已归档、
一个路径 404）经过**第二次独立复核**，全部属实。

商业产品的**价格与功能边界无法验证**（会变、常在销售页背后），文中只写能力方向，
相关条目均标注「采购前自行确认」。

## 怎么读

- 表格里的许可证列是**实测 SPDX 标识**；GitHub 自动识别不出来的（`NOASSERTION`），
  我去读了 LICENSE 原文，能确认的写实际许可证名并注明"核实文本"，读不出来的老实写"未识别"。
- 三个标记贯穿全文：**⚠️ 已归档**（`archived: true`）、**⚠️ 维护状态存疑**
  （最后推送超过 12 个月，或有官方声明降级维护）、**⚠️ 许可证陷阱**（非 OSI、
  source-available、或"仓库许可证"和"实际能用的东西"不是一回事）。
- 商业产品条目统一在末尾标 **——这不是
  客套话，是本文唯一诚实的写法。

---

## 一、SAST（静态代码分析）

### 开源选项

| 工具 | 许可证 | Stars | 最后推送 | 定位 / 适合什么 |
|---|---|---|---|---|
| [semgrep/semgrep](https://github.com/semgrep/semgrep) | LGPL-2.1 | 16.4k | 2026-08-28 | 多语言模式匹配 + 污点分析，规则生态最大，当前在用 |
| [opengrep/opengrep](https://github.com/opengrep/opengrep) | LGPL-2.1 | 3.0k | 2026-08-29 | Semgrep CE 的许可证干净 fork；**跨文件能力未在本仓证明**，见下方说明 |
| [github/codeql](https://github.com/github/codeql) | MIT（仓库）⚠️ 见下 | 10.0k | 2026-08-29 | 跨文件数据流分析强，GitHub 生态集成深 |
| [SonarSource/sonarqube](https://github.com/SonarSource/sonarqube) | LGPL-3.0（服务端）⚠️ 见下 | 10.9k | 2026-08-28 | SAST + 代码质量 + 技术债一体化 |
| [securego/gosec](https://github.com/securego/gosec) | Apache-2.0 | 8.9k | 2026-08-26 | Go 专用 |
| [PyCQA/bandit](https://github.com/PyCQA/bandit) | Apache-2.0 | 8.2k | 2026-08-24 | Python 专用 |
| [bearer/bearer](https://github.com/bearer/bearer) | **Elastic-2.0** ⚠️ 非开源 | 2.7k | 2026-08-24 | 以数据流/PII 追踪为特色，见下方说明 |
| [microsoft/DevSkim](https://github.com/microsoft/DevSkim) | MIT | 1.0k | 2026-08-26 | IDE 内轻量规则匹配，非深度引擎，适合做补充 |

> ⚠️ **Semgrep 的 LGPL-2.1 没变，但这数字不能单独看。** `semgrep/semgrep` 仓库本身
> 确实是 LGPL-2.1（已核实）。但 2024-12 Semgrep 官方把开源版更名为 "Community
> Edition"，同时把跨文件污点分析、指纹追踪、部分 metavariable 能力移进付费的商业平台，
> 规则库也换成限制性的 "Semgrep Rules License"（非 OSI）。2025-01，Aikido、Jit、
> Amplify Security、Endor Labs、Orca Security 等 10+ 家安全厂商把最后一版功能完整的
> CE 代码 fork 成了 **Opengrep**（`opengrep/opengrep`，同为 LGPL-2.1，已核实，
> 无付费墙、无企业版路径，社区维护）。想要 Semgrep 曾经的完整能力又不想被逐步移进
> 付费墙，Opengrep 值得放进候选。
>
> ⚠️ **SonarQube 主仓库是 LGPL-3.0，但真正扫代码的引擎不是。** `SonarSource/sonarqube`
> 服务端确实 LGPL-3.0（已核实）。但 2024 年底起，各语言分析器插件（`sonar-java`、
> `sonar-python` 等独立仓库）改用 **Sonar Source-Available License v1**（非 OSI；
> 已核实 `sonar-java` 的 GitHub 许可证字段为 `Other`/未识别，与 SSAL 的性质一致）。
> 同期 "Community Edition" 改名 "Community Build"。没有分析器插件服务端分析不了
> 任何代码——只看主仓库的 LGPL-3.0 徽章会漏掉这层。
>
> ⚠️ **CodeQL 的 MIT 只覆盖查询库，不覆盖"你能拿它扫谁"。** `github/codeql`
> （查询和库）标注 MIT（已核实）。但实际使用受独立的 *CodeQL Terms and Conditions*
> 约束：免费仅限 OSI 许可的开源代码库、学术研究，或特定 CI/CD 场景；**拿去分析闭源/
> 私有代码库需要 GitHub Advanced Security 的商业授权**。"MIT 所以随便用"是这份候选
> 清单里最容易踩的坑。
>
> ⚠️ **Bearer 不是 OSI 开源许可证** —— 是 Elastic License 2.0（source-available）。
> 把它和标准开源工具并列会让人误以为随便用。
>
> **但「非 OSI」不等于「不能用」，这两件事必须分开。** 其 README 原文：
>
> > "you can use it **freely inside your organization** to protect your applications
> > without any commercial requirements"
>
> 禁止的是：*"provide Bearer CLI to third parties as a hosted or managed service"* ——
> 即拿它当托管服务对外提供。**内部自用是明确允许的。**
>
> 对比 CodeQL 就能看出差别有多大：CodeQL 是**禁止**在私有代码库上使用（见
> [30-security-scanning/sast-engine-comparison.md](30-security-scanning/sast-engine-comparison.md)），
> Bearer 是**允许**内部使用、禁止转卖成服务。
>
> **教训：看到「非 OSI」不要直接判死刑，要读条款里到底禁了什么。**
> 反过来也一样——看到 MIT 标签也不代表就能随便用（CodeQL 就是）。

### 商业选项

- **Checkmarx（One）**——SAST 起家，现扩展到 SCA/IaC/容器的一体化平台，企业合规报告成熟。
- **Fortify（OpenText）**——老牌 SAST，语言覆盖广，偏大型企业审计场景。
- **Veracode**——SaaS 化 SAST/SCA/DAST，以"扫描即服务"和合规报告见长。
- **Semgrep AppSec Platform**——Semgrep 官方商业化产品，补回 CE 移走的跨文件分析等能力。
- **GitHub Advanced Security**——CodeQL 的商业授权路径，深度绑定 GitHub 工作流。

### 我们当前选了什么，为什么

**Semgrep。** 和 gitleaks/trivy/ZAP 做四工具分工（密钥/依赖+配置/代码模式/运行时），
LGPL-2.1 作为工具本身用没有传染性问题。一个已经验证过的关键事实反过来定义了别的选择：
**Semgrep 没有脱敏选项，命中密钥会明文进 CI 日志**，所以密钥检测必须交给有 `--redact`
的 gitleaks，这不是"两个工具重叠"，是刻意分工。

### 什么时候该换

- 需要跨文件/跨函数污点分析，Semgrep CE / Opengrep 的单文件规则连续漏掉真实存在的
  注入链（不是"担心漏"，是已经复盘出具体案例）。
- 同一批高危发现，工程师平均**分诊耗时超过修复耗时**——说明规则噪音已经压过了信号。
- 需要对闭源代码跑 CodeQL 的跨文件查询：这条不是"值不值得换"，是不满足免费条款时
  必须买 GHAS，没有灰色地带。

---

## 二、DAST（动态扫描）

### 开源选项

| 工具 | 许可证 | Stars | 最后推送 | 定位 / 适合什么 |
|---|---|---|---|---|
| [zaproxy/zaproxy](https://github.com/zaproxy/zaproxy) | Apache-2.0 | 15.7k | 2026-08-27 | 通用 Web DAST，baseline/full-scan/api-scan 三种模式，当前在用 |
| [projectdiscovery/nuclei](https://github.com/projectdiscovery/nuclei) | MIT | 30.9k | 2026-08-26 | 模板化探测，偏已知 CVE/指纹/错配，不是完整爬虫式 DAST |
| [sqlmapproject/sqlmap](https://github.com/sqlmapproject/sqlmap) | GPL-2.0-or-later（核实文本） | 38.3k | 2026-08-28 | 单一用途：SQL 注入专项利用 |
| [Arachni/arachni](https://github.com/Arachni/arachni) | 自定义许可证（非 OSI）⚠️ **已归档** | 4.0k | 2026-04-22 | 不建议采用，见下 |
| [andresriancho/w3af](https://github.com/andresriancho/w3af) | 未检测到 LICENSE 文件 ⚠️ 维护状态存疑 | 4.9k | 2023-02-22 | 事实性停滞，见下 |

> ⚠️ **Arachni 双重问题。** `archived: true`（已核实），且 `LICENSE.md` 实测内容是
> "Arachni Public Source License 1.0"——Ecsypno 公司自定义条款，不在 SPDX/OSI 列表里，
> 不能当普通开源工具对待。既已归档又许可证非标，直接排除。
>
> ⚠️ **w3af 实质性死亡。** 最后一次推送 **2023-02-22**，距今 3 年半；GitHub 的
> `/license` 端点返回 404，根目录没有能被自动识别的 LICENSE 文件。38k+ star 的
> sqlmap 和它常被放在同一张表里，但活跃度完全不是一个量级。
>
> Nuclei 和 sqlmap 值得单独说明**定位差异**：两者都不是 ZAP 的替代品。Nuclei 更接近
> "拿社区模板库扫已知问题"，sqlmap 是纯 SQL 注入的深度利用工具——都适合**补充**
> 而不是取代通用 DAST 爬虫。

### 商业选项

- **Burp Suite Enterprise**（PortSwigger）——业界渗透测试事实标准的自动化/CI 版本，扫描深度和插件生态强。
- **Checkmarx / Veracode 的 DAST 模块**——并入各自的一体化平台，报告和 SAST/SCA 结果打通。

### 我们当前选了什么，为什么

**ZAP。** Apache-2.0 无陷阱，三个脚本模式（baseline 被动可自动化 / full-scan 真实攻击
只能定时或手动 / api-scan 按 spec）已经摸清楚各自的适用边界。已知的最大失效模式
**没配认证 → 只扫到登录页 → 报告很干净**——这条本身就是判断"扫描是不是真的在跑"的
标尺，不是靠"看起来正常"。

### 什么时候该换

- ZAP 报告连续多次只覆盖登录页之后的 0-1 个 URL（认证配置从没跟上应用改版），
  且没人有空修——工具选型解决不了组织问题，但如果长期如此，说明需要一个把认证
  管理当作核心功能而不是配置项的产品。
- 需要在生产或类生产环境做持续、低干扰扫描：ZAP full-scan 是真实攻击性负载，
  自建 CI runner 上跑容易把 runner 或目标环境打满。

---

## 三、SCA（依赖成分分析）

### 开源选项

| 工具 | 许可证 | Stars | 最后推送 | 定位 / 适合什么 |
|---|---|---|---|---|
| [aquasecurity/trivy](https://github.com/aquasecurity/trivy) | Apache-2.0 | 37.7k | 2026-08-28 | 依赖 + 配置 + 密钥 + 镜像四合一，当前在用 |
| [anchore/grype](https://github.com/anchore/grype) | Apache-2.0 | 12.8k | 2026-08-28 | 专注 SCA/镜像漏洞，和 syft 是同一家的姊妹项目 |
| [google/osv-scanner](https://github.com/google/osv-scanner) | Apache-2.0 | 10.9k | 2026-08-28 | 基于 OSV.dev 数据源，多生态锁文件支持好 |
| [DependencyTrack/dependency-track](https://github.com/DependencyTrack/dependency-track) | Apache-2.0 | 4.2k | 2026-08-29 | 更偏平台：吃 SBOM、持续监控，见十节 |
| [dependency-check/DependencyCheck](https://github.com/dependency-check/DependencyCheck) | Apache-2.0 | 7.7k | 2026-08-28 | OWASP Dependency-Check，见下方地址说明 |

> ⚠️ **候选清单给的 `jeremylong/DependencyCheck` 地址已归档**（`archived: true`，
> 已核实，归档于 2025-09-27）。项目没有死，只是搬家——现在的正主在
> **`dependency-check/DependencyCheck`**（Apache-2.0，7.7k★，2026-08-28 仍有推送）。
> 旧地址目前只是一个指向新家的 55★ 存根仓库，star 历史留在了新地址。用旧链接会让人
> 误判这个老牌工具已经死掉。

### 商业选项

- **Snyk**——SCA 里做**可达性分析**较早也较成熟的一家，IDE/PR 集成深。
- **Mend**（原 WhiteSource）——老牌 SCA + 许可证合规，企业审计报告成熟。
- **Sonatype Nexus Lifecycle**——和 Nexus 制品库联动，偏"在依赖进仓库那一刻拦截"。
- **JFrog Xray**——和 Artifactory 联动，同样是制品库层拦截的思路。

### 我们当前选了什么，为什么

**Trivy。** 一个 Apache-2.0 单二进制覆盖 SCA + IaC 配置检查 + 镜像扫描三个类别
（见六、七节），运维面比装三个独立工具小得多，这是选型时看得见的直接收益。
**Trivy 常被叫成 SAST，它不是**——它不读业务代码逻辑，只对账依赖清单和已知漏洞库，
这条边界要记住，否则会误以为"上了 Trivy 就不需要 Semgrep"。

### 什么时候该换

- CVE 告警量大到没人能靠人工判断"可达性"（这个漏洞你的代码到底调没调到那段有问题
  的函数）——Trivy/Grype/OSV-Scanner 都不做可达性分析，**分诊耗时明显超过修复耗时**
  是切换的信号，而不是"CVE 数量看着多"。
- 需要出具给客户或审计方的正式许可证合规报告（不只是漏洞），这块开源工具普遍薄弱。

---

## 四、依赖更新自动化

### 开源选项

| 工具 | 许可证 | Stars | 最后推送 | 定位 / 适合什么 |
|---|---|---|---|---|
| [renovatebot/renovate](https://github.com/renovatebot/renovate) | AGPL-3.0 | 22.4k | 2026-08-29 | 多生态、配置粒度细，当前在用 |
| [dependabot/dependabot-core](https://github.com/dependabot/dependabot-core) | MIT | 5.7k | 2026-08-29 | 见下方地址说明 |

> ⚠️ **候选清单给的 `github/dependabot-core` 查不到（404）**，正确路径是
> **`dependabot/dependabot-core`**（MIT，已核实，5.7k★，2026-08-29 仍有推送，
> 组织名是 `dependabot` 不是 `github`）。另外这不是一个可以直接"装上跑"的产品——
> 它是 Dependabot 更新逻辑的核心库，多数人用的是 GitHub 托管的 Dependabot 服务，
> 自建需要额外搭 runner 编排，运作模型和 Renovate 作为一个独立 CI 机器人不一样。

### 商业选项

依赖更新在商业市场里通常不单独成类，而是并入 SCA 平台（Snyk、Mend 都自带升级建议
和自动 PR），见三节。

### 我们当前选了什么，为什么

**Renovate。** AGPL-3.0 当独立 CI 机器人跑不触发传染性问题，但这条要写进选型记录里，
不能假装不知道。多生态支持和配置继承粒度上目前比 Dependabot 更适合非 GitHub-only
的环境。已知坑：镜像必须用 `-full` 变体（默认镜像没有包管理器）、
`GITHUB_COM_TOKEN` 是配额问题不是权限问题、**关闭 PR 等于永久忽略**（调试要
`recreateWhen=always`）。

### 什么时候该换

- 仓库数/生态数增长到 Renovate 的 PR 噪音让人开始**批量关闭而不逐条看**——这正是
  会触发"永久忽略"那个坑的场景，信号和后果是同一件事。
- 需要跨仓库的策略式治理（例如"全组织禁止升级到某个已知问题版本"），配置继承在
  这个规模下开始变成手工同步而不是自动生效。

---

## 五、Secret Scanning（密钥扫描）

### 开源选项

| 工具 | 许可证 | Stars | 最后推送 | 定位 / 适合什么 |
|---|---|---|---|---|
| [gitleaks/gitleaks](https://github.com/gitleaks/gitleaks) | MIT | 29.0k | 2026-08-26 | 扫 git 历史，有 `--redact`，当前在用 |
| [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | AGPL-3.0 | 27.6k | 2026-08-28 | 有效性验证能力强（拿疑似密钥去调 API 确认死活） |
| [Yelp/detect-secrets](https://github.com/Yelp/detect-secrets) | Apache-2.0 | 4.6k | 2026-04-02 | 侧重"建基线 + 阻止新增"的工作流 |
| [awslabs/git-secrets](https://github.com/awslabs/git-secrets) | Apache-2.0 | 13.4k | 2025-09-17 | 接近一年未更新，活跃度低但未达 12 个月归档线 |

### 商业选项

密钥扫描同样很少单独售卖，多数并入一体化平台（GitHub Advanced Security 的
secret scanning、GitLab Ultimate 都含此能力），见十一节。

### 我们当前选了什么，为什么

**Gitleaks。** MIT、有 `--redact`——这条直接对应上面 Semgrep 那条"没有脱敏选项"
的已知限制，密钥检测必须交给能脱敏的工具，否则命中的密钥会原样进 CI 日志，等于
自己制造一次新泄露。**关键差异在扫描范围**：只扫工作区 vs 扫整个 git 历史，密钥
一旦提交，删文件重新提交没用，历史里还在——这是选型时必须确认的能力，不是可选项。

### 什么时候该换

- 需要"有效性验证"（疑似密钥自动去调 API 确认死活）把误报砍下去，又不想自建这套
  外呼逻辑和秘钥管理——TruffleHog 已经做了这个能力，是升级路径而非另起炉灶；
  真正要换商业的信号是需要**跨渠道**（Slack、工单系统、日志聚合，而不只是 git）
  的密钥扫描，这超出 gitleaks/trufflehog 的设计范围。

---

## 六、IaC / 配置扫描

### 开源选项

| 工具 | 许可证 | Stars | 最后推送 | 定位 / 适合什么 |
|---|---|---|---|---|
| [aquasecurity/trivy](https://github.com/aquasecurity/trivy)（misconfig） | Apache-2.0 | 37.7k | 2026-08-28 | 当前在用，和 SCA/镜像扫描共用一个二进制 |
| [bridgecrewio/checkov](https://github.com/bridgecrewio/checkov) | Apache-2.0 | 9.0k | 2026-08-27 | 规则数量和云资源覆盖面通常被认为业界最全 |
| [open-policy-agent/conftest](https://github.com/open-policy-agent/conftest) | Apache-2.0（核实文本） | 3.3k | 2026-08-25 | 基于 OPA/Rego，适合自定义策略而非内置规则库 |
| [stackrox/kube-linter](https://github.com/stackrox/kube-linter) | Apache-2.0 | 3.5k | 2026-08-26 | 专注 Kubernetes manifest，范围比 checkov/trivy 窄 |
| [Checkmarx/kics](https://github.com/Checkmarx/kics) | Apache-2.0 | 2.7k | 2026-08-25 | 多 IaC 格式覆盖广，候选清单没有，见文末补充 |
| [aquasecurity/tfsec](https://github.com/aquasecurity/tfsec) | MIT ⚠️ 官方维护模式 | 7.0k | 2026-03-25 | 已并入 Trivy，见下 |
| [tenable/terrascan](https://github.com/tenable/terrascan) | Apache-2.0 ⚠️ **已归档** | 5.2k | 2025-11-20 | 已被 Tenable 弃用，见下 |

> ⚠️ **tfsec 不是"还能用"，是"官方已经不投入"。** Aqua 2023 年就宣布把 tfsec
> 并入 Trivy，2024 年完成引擎合并；仓库自己的说明是"tfsec 会继续存在一段时间，
> 但工程投入方向是 Trivy"。最后一个版本 v1.28.14 停在 2025-05，此后新出的
> Terraform 特性不会再有新检查规则覆盖。tfsec 的每条检查 ID（如 `AVD-AWS-0086`）
> 在 Trivy 里原样可用，迁移不需要重新映射基线——所以结论很直接：新项目直接用
> Trivy，不要新引入 tfsec。
>
> ⚠️ **terrascan 已被原厂弃用。** `archived: true`（已核实，2025-11-20 归档）。
> Tenable 收购 Accurics 后接手过 terrascan，2025-07 的 EOL 文档显示 Nessus
> 10.10.0 起不再内置它，官网 `runterrascan.io` 现在直接跳转到 Tenable 云安全的
> 商业产品页。不建议新项目采用。

### 商业选项

- **Aqua（Security）**——云原生安全平台，IaC 扫描是其中一环，和运行时防护联动。
- **Sysdig**——同样是运行时优先的云原生安全平台，IaC/镜像扫描并入更大的可观测性叙事。
- **Snyk IaC**——并入 Snyk 平台，和 SCA/容器结果共用一套优先级排序。

### 我们当前选了什么，为什么

**Trivy 的 misconfig 子命令。** 和 SCA、镜像扫描共用同一个 Apache-2.0 二进制，
这是三个类别里反复出现的同一条理由：运维面小。checkov 的规则覆盖面公认更全，
但目前没有触发切换的具体信号（见下）。

### 什么时候该换

- 云资源和 Terraform module 规模变大后，Trivy misconfig 对新发布的云资源类型
  连续出现规则空白，且切到 checkov/KICS 验证过确实能补上——这时候补一个专项工具
  比死等 Trivy 补规则划算。
- 需要"这条 Terraform 变更会打开哪些新的安全组/新的公网入口"这类**变更影响半径**
  分析——静态规则匹配类工具基本不做这个，是商业云安全平台的强项。

---

## 七、容器镜像扫描

### 开源选项

| 工具 | 许可证 | Stars | 最后推送 | 定位 / 适合什么 |
|---|---|---|---|---|
| [aquasecurity/trivy](https://github.com/aquasecurity/trivy) | Apache-2.0 | 37.7k | 2026-08-28 | 当前在用 |
| [anchore/grype](https://github.com/anchore/grype) | Apache-2.0 | 12.8k | 2026-08-28 | 和 syft 是姊妹项目，SBOM→漏洞比对链路顺 |
| [quay/clair](https://github.com/quay/clair) | Apache-2.0 | 11.1k | 2026-08-25 | 服务化架构（需要部署+API），不是单文件 CLI |
| [goodwithtech/dockle](https://github.com/goodwithtech/dockle) | Apache-2.0 | 3.3k | 2026-08-10 | 查 Dockerfile 最佳实践/加固，**不是** CVE 扫描 |

> Dockle 和其他三个不是同一类工具，容易被误当作"再挑一个镜像扫描器"：它检查的是
> 镜像本身的加固程度（是否以 root 运行、是否有多余的 setuid 二进制等 CIS 基准项），
> 不查 CVE。和 trivy/grype 是互补关系，不是可替代关系。Clair 则是需要独立部署的
> 服务化架构，适合"镜像仓库集成一个中心化扫描服务"的场景，运维成本明显高于
> CLI 类工具。

### 商业选项

- **JFrog Xray**——和 Artifactory 制品库深度绑定。
- **Chainguard**——角度不同：卖的是预加固的最小化基础镜像（+ 签名 + SBOM 随镜像分发），从源头减少可扫的攻击面，而不是"再扫一遍"。
- **Aqua / Sysdig**——同六节，镜像扫描是其云原生安全平台的一部分。

### 我们当前选了什么，为什么

**Trivy。** 同三、六节，一个二进制覆盖三个类别的运维面收益在这里同样成立。

### 什么时候该换

- 需要 base image 到部署环节的**持续准入控制**（admission controller 挡镜像上线），
  而不是"CI 里跑一下报告，看不看是另一回事"——这是运行时集成能力，纯 CLI 扫描器
  没有。
- 需要扫描结果和运行时联动（这个有漏洞的镜像，现在真的有 Pod 在跑吗）——静态扫描器
  看不到这层，是 Aqua/Sysdig 这类平台的核心卖点。

---

## 八、SBOM 生成与管理

### 开源选项

| 工具 | 许可证 | Stars | 最后推送 | 定位 / 适合什么 |
|---|---|---|---|---|
| [anchore/syft](https://github.com/anchore/syft) | Apache-2.0 | 9.5k | 2026-08-29 | CycloneDX/SPDX 双格式生成，和 grype 联动 |
| [cdxgen/cdxgen](https://github.com/cdxgen/cdxgen) | Apache-2.0 | 1.1k | 2026-08-28 | 见下方组织迁移说明 |
| [spdx/tools-golang](https://github.com/spdx/tools-golang) | Apache-2.0 **或** GPL-2.0-or-later（双许可，核实文本） | 170 | 2026-08-24 | SPDX 文档的 Go 处理库，非生成器 |
| [spdx/tools-python](https://github.com/spdx/tools-python) | Apache-2.0 | 254 | 2026-03-13 | SPDX 文档的 Python 处理库，同上 |

> ⚠️ **`CycloneDX/cdxgen` 这个候选路径已经不是权威地址。** 项目组织从 `CycloneDX`
> 迁到了独立的 **`cdxgen`** 组织（GitHub API 返回的 `full_name` 已核实为
> `cdxgen/cdxgen`），旧路径会跳转，但记录事实的地址应该用新的。
>
> ⚠️ **`spdx/tools` 已归档**（已核实，2025-10-07 归档，145★）。SPDX 3.0 发布后，
> 原来的 Java 单体工具被拆成按语言分开的库：`spdx/tools-golang`（Go，活跃）和
> `spdx/tools-python`（Python，活跃）。这两个是**处理/校验 SPDX 文档的库**，不是
> "一键生成 SBOM"的命令行工具——真要生成 SPDX 格式 SBOM，syft 和 cdxgen 都能直接
> 输出 SPDX，比自己接这两个库现实。

### 商业选项

- **Anchore Enterprise**——syft/grype 背后公司的商业版，加存档、比对、策略引擎。
- **JFrog Xray**——SBOM 能力并入制品库生态。
- **Chainguard**——镜像自带 SBOM + 签名，见七节。

### 我们当前选了什么，为什么

**没有专门工具。** Trivy 本身能以 CycloneDX 格式输出 SBOM（`trivy sbom` /
`--format cyclonedx`），作为 SCA 扫描的副产品免费拿到。**SBOM 本身不是安全措施，
是库存台账**——它的价值在于将来出事时能快速回答"我受影响吗"。log4j 事件里，
有 SBOM 的公司几小时内知道范围，没有的花了几周。目前这个副产品级别的输出还没有
被证明不够用，所以没有为了"有 SBOM"这件事本身单独引入 syft。

### 什么时候该换

- 需要给客户/监管方出具**可核验、有版本追溯**的 SBOM——Trivy 侧输出没有存档、
  没有历史版本比对、没有"这次构建和上次比多了哪些组件"的差异追踪，这些是
  Syft + 存档系统（或 Dependency-Track，见十节）才有的能力。
- 真的复盘过一次"这个新披露的漏洞，我们哪些系统受影响"，如果答案要花几天翻
  各个仓库的 lockfile 而不是几小时查一个中心化台账，说明该上专门的 SBOM 管理了。

---

## 九、供应链签名与来源证明

### 开源选项

| 工具 | 许可证 | Stars | 最后推送 | 定位 / 适合什么 |
|---|---|---|---|---|
| [sigstore/cosign](https://github.com/sigstore/cosign) | Apache-2.0 | 6.3k | 2026-08-24 | 签名/验签工具本体，keyless 签名的实现 |
| [in-toto/in-toto](https://github.com/in-toto/in-toto) | Apache-2.0（核实文本） | 1.0k | 2026-08-27 | 构建链每一步的来源证明框架 |
| [slsa-framework/slsa-github-generator](https://github.com/slsa-framework/slsa-github-generator) | Apache-2.0 | 595 | 2026-08-07 | SLSA 在 GitHub Actions 上的具体实现，注意见下 |

> SLSA 本身是**分级框架**（L1–L3 的成熟度标准），不是一个能安装的工具——
> `slsa-github-generator` 只是它在 GitHub Actions 场景下的一个具体实现，别把两者
> 当成同一层次的东西来选型。
>
> 签名的价值全在**验证**那一步。没有任何环节强制校验签名，签名就只是给 CI
> 加时间的仪式；keyless 签名还意味着构建身份会进 Sigstore 的公开透明日志
> （Rekor），内部项目要先想清楚能否接受这条。

### 商业选项

- **Chainguard**——镜像原生带签名+SBOM+来源证明，见七、八节，思路是"发布时就带上"而不是"事后补签"。

### 我们当前选了什么，为什么

**没有。** 当前没有外部消费方需要校验我们制品的来源，签名基础设施建了也没人验，
就是仪式。

### 什么时候该换（这里"换"其实是"从无到有"）

- 出现第一个会真的去校验签名的外部消费方（客户、下游团队、供应链审计方）——
  没有校验方的签名是仪式，见上。
- 采购方或合规要求把 SLSA L2/L3 写成硬性条款。

---

## 十、漏洞管理 / findings 聚合平台

### 开源选项

| 工具 | 许可证 | Stars | 最后推送 | 定位 / 适合什么 |
|---|---|---|---|---|
| [DefectDojo/django-DefectDojo](https://github.com/DefectDojo/django-DefectDojo) | BSD-3-Clause | 4.9k | 2026-08-29 | 面向研发流程的多扫描器结果聚合/去重/分诊 |
| [DependencyTrack/dependency-track](https://github.com/DependencyTrack/dependency-track) | Apache-2.0 | 4.2k | 2026-08-29 | 以 SBOM 为中心的持续监控（见三、八节），偏 SCA 一类 |
| [infobyte/faraday](https://github.com/infobyte/faraday) | GPL-3.0 | 6.7k | 2026-08-20 | 偏渗透测试团队协作/报告，和 DefectDojo 的"研发管线里去重分诊"定位不同 |

> DefectDojo 用的是 BSD-3-Clause——这份清单里少见的宽松许可证，没有 AGPL/LGPL
> 那类需要关注的条款，值得在选型时正面记一笔（不是所有条目都是坑，这个是加分项）。
> Faraday 的核心定位和 DefectDojo 不是同一件事：DefectDojo 面向"CI 里一堆扫描器
> 吐出来的结果怎么去重分诊"，Faraday 更贴近渗透测试团队的协作和交付报告流程——
> 两个都叫"漏洞管理"，但解决的是不同团队的不同问题，选型前先确认自己要解决哪个。

### 商业选项

多数一体化平台自带聚合能力（见十一节），单独的商业聚合层不多，值得一提的是各家
云安全/AppSec 平台把"聚合"当作卖点之一而非独立产品。

### 我们当前选了什么，为什么

**没有。** 当前扫描器数量少（四个），结果各自独立看还没有产生明显的重复告警负担。

### 什么时候该换（同样是"从无到有"）

- 扫描器数量过了 2–3 个，同一个底层问题在不同工具的报告里反复出现，没人做去重——
  **分诊耗时明显超过修复耗时**是最直接的信号，和三节 SCA 的触发条件呼应但这里
  是聚合层面的问题，不是单个扫描器噪音大的问题。
- 需要给管理层或审计方一份跨扫描器的态势报表，如果这份报表现在是靠人工拼 CSV
  拼出来的、并且已经变成某个人的固定工作量，说明该上聚合平台了。

---

## 十一、一体化商业平台

把多个类别打包卖的产品。**这类产品买的不是某个扫描引擎本身，买的是"少维护几个
工具"和"给审计方一份单一叙事"**——评估时应该按这两条价值判断，而不是逐项对比
功能清单（功能清单会变，采购前务必自己核实）。

- **GitHub Advanced Security**——CodeQL(SAST) + secret scanning + SCA，深度绑定 GitHub 工作流，不额外引入新平台。
- **GitLab Ultimate**——同上思路但绑定 GitLab，SAST/SCA/secret/IaC/容器打包进同一套 CI。
- **Snyk**——SCA 起家，扩展到 SAST(Code)/容器/IaC，IDE 集成和开发者体验是卖点。
- **Checkmarx One**——SAST 起家扩展到 SCA/IaC/容器，企业合规报告成熟。
- **Veracode**——SaaS 化 SAST/SCA/DAST 打包，偏合规报告驱动。
- **Aqua / Sysdig**——云原生安全平台，镜像/IaC 扫描 + 运行时防护 + 合规打包，运行时联动是差异点。
- **Mend（原 WhiteSource）**——SCA + 许可证合规为核心，向 SAST 扩展。
- **Sonatype Nexus Lifecycle**——制品库层拦截思路，和 Nexus Repository 联动。

---

## 十二、如果只能选一套：最小组合

按已验证的事实给出的组合——**不是理论最优，是"每个位置都有一个具体、可验证的理由"**。

| 位置 | 选择 | 为什么选它 |
|---|---|---|
| SAST | Semgrep（LGPL-2.1 已核实；权衡 Opengrep） | 多语言覆盖，规则生态最大；Opengrep 是"不想被移进付费墙"时的同许可证平替 |
| DAST | ZAP | Apache-2.0 无陷阱，三种脚本模式覆盖被动/主动/API 三种场景，成熟度和生态最好 |
| SCA + IaC 配置扫描 + 容器镜像扫描 | Trivy | 一个 Apache-2.0 二进制覆盖三个类别，运维面最小；37.7k★ 持续活跃（已核实） |
| 依赖更新自动化 | Renovate | 多生态支持强于 Dependabot，AGPL-3.0 作为独立 CI 机器人跑不触发传染 |
| Secret Scanning | Gitleaks | MIT + `--redact`；Semgrep 没有脱敏能力，密钥检测必须是独立工具 |
| SBOM | 不单独引入 | Trivy 已经能输出 CycloneDX 作为 SCA 扫描的副产品，够用到出现存档/比对需求为止 |
| 供应链签名 | 不引入 | 没有外部校验方，签名是仪式；出现校验方或 SLSA 合规要求时上 cosign |
| 漏洞管理聚合 | 不引入 | 四个扫描器的规模还没有产生明显的重复告警负担 |

三个"不引入"不是遗漏，是**触发条件还没出现**——建早了是白维护一套没人用的基础设施，
和为了合规而合规没有区别。

---

## 十三、迁移触发条件：从开源换到商业的信号

这些信号要能被直接观察到，不能是"感觉误报有点多"这种没法验证的话。

| 信号 | 说明 |
|---|---|
| 误报多到有人开始无视告警 | 不是"误报率百分之多少"，是有人已经养成了"扫描器报的东西先不看"的习惯——这一刻工具已经在倒扣安全性 |
| 分诊耗时超过修复耗时 | 团队花在"这条告警是不是真的"上的时间，比花在修复真问题上的时间还多 |
| 同一个问题在多个扫描器报告里重复出现，没人去重 | 说明已经到了需要聚合层（十节）的规模，纯靠人工核对撑不住了 |
| 扫描器数量过了 2–3 个 | 维护多套配置、多套升级节奏本身开始占用明显的工程时间，这是"该上聚合平台或一体化平台"的容量信号 |
| 需要向审计方（SOC2/ISO 27001/等保）交付单一叙事 | 七个工具拼出来的证据链，审计方看着费劲，团队解释起来也费劲 |
| 出现外部消费方要校验你的签名/SBOM | 之前没人验，签名和 SBOM 都是仪式；一旦有人真的会验，价值才成立（见八、九节） |
| 需要供应商 SLA 兜底漏洞库时效 | 开源工具的漏洞数据源更新时效没有人为你担保，合规或客户合同要求这一条时，自建工具给不出承诺 |
| 需要可达性分析而工具没有 | Trivy/Grype/OSV-Scanner 都不做"这个 CVE 你到底调没调用到"的判断，量大到人工判断不过来时是明确的商业信号 |
| 服务/仓库数量过了自己团队能手工维护配置的量级 | 没有放之四海皆准的具体数字，但如果连"我们现在到底在多少个仓库里跑着哪个版本的扫描器"这个问题都答不上来，就已经过线了 |

---

## 报告：候选清单之外的补充

- **Opengrep**（`opengrep/opengrep`）——直接回应候选清单里"Semgrep 是 LGPL-2.1"
  这条本身没错、但会让人误判风险边界的问题，见一节。
- **Checkmarx/kics**——候选清单的 IaC 类没有它，但多格式覆盖是这类工具里公认较广的，加进六节。
- **dependency-check/DependencyCheck**、**spdx/tools-golang**、
  **spdx/tools-python**——三个候选清单里对应项目已归档后的权威接替地址，不加这几个，
  对应类别的表格会显得项目已死。
