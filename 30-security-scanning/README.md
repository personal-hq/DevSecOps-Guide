# 安全扫描

gitleaks / trivy / semgrep / ZAP 四个扫描工具的分工、许可证和配置踩坑。

## 本节内容

| 文件 | 内容 |
|---|---|
| [zap-dast.md](zap-dast.md) | ZAP 的三个打包脚本、触发矩阵、Automation Framework |
| [tool-selection.md](tool-selection.md) | 商业/进阶工具怎么选、什么时候值得买 |
| [sast-engine-comparison.md](sast-engine-comparison.md) | SAST 引擎选型实测：CodeQL 许可证、Semgrep vs Opengrep |

## 四工具分工

| 工具 | 类型 | 覆盖 |
|---|---|---|
| gitleaks | 密钥检测 | git 历史全量扫描密钥 |
| trivy | 依赖漏洞 | 依赖 CVE + 配置 + SBOM |
| semgrep | SAST | 静态代码缺陷 |
| ZAP | DAST | **需要一个跑起来的服务**——和前三个只读文件的性质根本不同，见 [zap-dast.md](zap-dast.md) |

许可证：trivy Apache-2.0、gitleaks MIT、**semgrep LGPL-2.1**、ZAP Apache-2.0、Renovate **AGPL-3.0**。

## 为什么不用第三方 action

本实例的 action 只从 `data.forgejo.org` 解析，GitHub 上的 `trivy-action` 之类拿不到。直接装二进制/包，版本钉死。

## semgrep 排除 secrets 规则

它**没有脱敏选项**（实测 `--help` 只有 `--quiet`），命中密钥会明文进 CI 日志——保留 14 天，有仓库权限的人都能看。密钥检测交给有 `--redact` 的 gitleaks，而且 gitleaks 扫 git 历史覆盖更全，semgrep 只看工作区当前内容。

## 验证扫描器有效性

一个从未报过问题的扫描器，和一个坏掉的扫描器，外观完全一致——必须用已知坏样本验证（见 [00-principles.md](../00-principles.md) 第一条）。我们在 Forgejo 实例上单开了一个 `security-scan` 仓当 canary（**不在本指南仓里**，clone 这份指南不会带上它）：故意植入问题样本，CI 应该永远是红的，变绿说明扫描器链路坏了。
