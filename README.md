# DevSecOps 指南

自建研发基础设施的实践记录。**每一条都来自实际做过并验证过的事**——没验证的不写，
验证方式不可靠的会注明。

赶时间就只读 [`00-principles.md`](00-principles.md)：那四条是具体技术之外真正反复救你的东西。
每节同一个模板：**怎么做 / 为什么这么选 / 踩过什么坑 / 怎么验证**。

## 索引

| 节 | 内容 |
|---|---|
| [00-principles](00-principles.md) | 验证的四条铁律 |
| [01-glossary](01-glossary.md) | 名词详解：SAST/DAST/SCA/SBOM…以及**常被误用成什么** |
| [02-tool-landscape](02-tool-landscape.md) | 十一类工具的开源与商业全景，许可证陷阱逐条实查 |
| [05-architecture](05-architecture.md) | 准入标准、四条闭环、分层、分阶段实施 |
| [10-self-hosted-git](10-self-hosted-git/) | 形态选择、存储陷阱、两处实测缺陷、SSH 取舍、备份恢复演练 |
| [20-ci-cd](20-ci-cd/) | Runner 隔离、分支保护实测、管理员绕过为何静默、「接受 ≠ 生效」三例 |
| ├ [gate-qa-checklist](20-ci-cd/gate-qa-checklist.md) | 门禁自查清单：按绕过路径组织，**三条通行做法在 Forgejo 上不成立** |
| [30-security-scanning](30-security-scanning/) | gitleaks / trivy / semgrep / ZAP 分工与许可证 |
| ├ [zap-dast](30-security-scanning/zap-dast.md) | ZAP：三个脚本、触发矩阵、Automation Framework |
| ├ [sast-engine-comparison](30-security-scanning/sast-engine-comparison.md) | SAST 引擎选型实测：CodeQL 许可证、Semgrep vs Opengrep |
| ├ [false-positives](30-security-scanning/false-positives.md) | **误报怎么处置**：实测 83% 误报率、成因分类、处置成本原则 |
| └ [tool-selection](30-security-scanning/tool-selection.md) | 商业/进阶工具选型 |
| [40-dependency-updates](40-dependency-updates/) | Renovate：权限模型与踩坑 |
| [templates](templates/) | 仓库模板：service / docs 两种，以及为什么只能复制不能用可复用 workflow |

**规范文档**（不是实施记录，是给别的团队照着做的参考架构）：

| 文档 | 内容 |
|---|---|
| [DevSecOps 方案](2026-08-27-forgejo-devsecops.md) | S/L 两档强度 × N/P 两种入口、门禁矩阵、Runner 信任分区、验收红线、风险登记 |

**附录（不属于 DevSecOps，可跳过）**——界面定制是本仓早期的另一条线，留着是因为
[`00-principles.md`](00-principles.md) 有两条铁律出自那段工作。

| 节 | 内容 |
|---|---|
| [50-ui-theming](50-ui-theming/) | 设计令牌、10 条 CSS 踩坑、覆盖判定法、主题成品与设计稿 |
| [tools/audit-css-vars.py](tools/audit-css-vars.py) | CSS 变量覆盖率审计脚本 |
| [tools/screenshot-pipeline](tools/screenshot-pipeline/) | 无头浏览器截图验证的方法与三条固有限制（只有方法，不放脚本） |
| [artifacts/shots](artifacts/shots/) | 截图证据，每张标注能证明什么、不能证明什么 |

## 事实出处表

每条实测事实**只写在一处**，别处引用不复述。改结论就改这一处。
本仓已经因为"只改了想起来的那处"翻车三次，这张表是补丁。

| 事实 | 唯一出处 |
|---|---|
| 作者自批 422 · `force_merge` 绕过 · 删规则 204 · `apply_to_admins` 挡不住 | [20-ci-cd](20-ci-cd/README.md) §三 |
| 管理员绕过为何"静默"（删规则无痕 / `force_merge` 与正常合并同形） | 同上 §三 |
| CODEOWNERS 硬门 405→200 · 根目录唯一一份 · Go 正则非 glob | 同上 §三 |
| 必检 context 真实命名 · `paths-ignore` 锁死 · `["*"]` fail-closed | 同上 §三 |
| `protected_file_patterns` 是冻结不是加严 · 标签保护 422 | 同上 §三 |
| `permissions:` 被忽略 · webhook 静默丢事件 · `ALLOWED_HOST_LIST` 拒私网 | 同上 §七 |
| ephemeral 是 one-job 注册循环，不是开关 | 同上 §二 |
| `workflow_run` 不触发 · ZAP 触发方式 | [zap-dast](30-security-scanning/zap-dast.md) |
| Opengrep vs Semgrep 实测 · CodeQL 许可证 | [sast-engine-comparison](30-security-scanning/sast-engine-comparison.md) |
| 开源项目 star / 许可证 / 归档状态 | [02-tool-landscape](02-tool-landscape.md) |
| Forgejo 部署缺陷 · 备份恢复 | [10-self-hosted-git](10-self-hosted-git/README.md) |
| CSS 覆盖判定 · 主题机制 | [50-ui-theming](50-ui-theming/)（附录） |

以上平台行为均在 **Forgejo 16.0.3 + Runner 13.0.0** 上测得，**升大版本要重测**。

## 边界：指南 ≠ 规范

本仓是**一个实例、两个仓库**的实施记录；规范是同目录的
[DevSecOps 方案](2026-08-27-forgejo-devsecops.md)（分 S/L 两档 × N/P 两种入口，面向别的团队照着做）。
冲突时听谁的，**看冲突在哪一层**：

| 层 | 以谁为准 | 为什么 |
|---|---|---|
| **平台事实**——状态码、事件是否触发、配置是否真生效 | **实测** | 方案里 CODEOWNERS「不可用」和 `permissions:`「未验证」两条就是被本仓实测改掉的。**一份文档压不过一次测量** |
| **规定**——哪道闸阻断、什么先做、拆仓还是 CODEOWNERS | **方案** | 本仓只有一个实例、一个成熟度，没有 S/L 那个轴，没资格立规矩 |
| **落到你那里**——选哪一档、"视情况"的参数 | **你的业务实际** | 方案给的是默认值，不是替你做决定 |

两边都别越界：不能拿"我们情况特殊"推翻**实测的平台行为**（那是否认证据），
也不能拿"方案上写着"推翻你自己实例上量出来的东西（那是
[`00-principles.md`](00-principles.md) 第 1、4 条讲的自欺）。

**所以本仓的祈使句（"绝不能…""必须…"）读作"我们当时这么选、以及为什么"，不是公司规定。**

同理，**可迁移的是方法**（判断 CSS 被谁覆盖、用已知坏样本验证扫描器、区分"错误消失"和
"真的修好"），**不可迁移的是平台事实**——`20-ci-cd/` 里那些状态码换成 GitLab 请重测。

> 本仓的 Forgejo 实例是**测试环境**。`50-ui-theming/theme/` 下是**参考快照**，
> 不是部署源——真实部署在实例自己的 `custom/` 目录里。
