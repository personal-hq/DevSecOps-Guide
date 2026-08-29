# 界面定制（以 Forgejo 为例）

> **范围说明：这一节不属于 DevSecOps。** 它是本仓早期的另一条线——给自建 Forgejo
> 做界面定制。放在这里是因为工作发生在同一个实例上，且
> [`00-principles.md`](../00-principles.md) 有两条铁律出自这段工作。
> 按 DevSecOps 读本仓的人可以跳过。

给自建服务做品牌化改造：换配色、换标识、去掉上游产品痕迹、统一排版密度。

载体是 Forgejo，但**方法通用**——任何"用 CSS 变量 + 一套 UI 框架（这里是 Fomantic）
构建、允许放自定义静态资源"的 Web 应用都适用。

## 本节内容

| 文件 | 内容 |
|---|---|
| [theming-guide.md](theming-guide.md) | 怎么做：机制在哪、有哪些 seam、从哪下手 |
| [css-debugging.md](css-debugging.md) | 规则不生效时怎么定位（**最实用的一篇**） |
| [pitfalls.md](pitfalls.md) | 踩过的 10 个坑：症状 / 根因 / 修法 |
| [tokens.md](tokens.md) | 设计令牌与配色，含每个取值的理由 |
| [theme/](theme/) | **成品**：主题 CSS + logo + favicon + 字体 + 安装说明 |
| [design/](design/) | 设计稿（5 张艺术板，可离线打开） |

配套证据在 [`../artifacts/shots/`](../artifacts/shots/)，含前后对照和 logo 候选对照表。

## 成果长什么样

Forgejo 原生是橙色品牌（`--color-primary: #c2410c`）+ 较松的布局。改造后：

- 低饱和深靛蓝 `#454b8c`，语义色只在 CI 状态和 diff 出现
- 全站 Octicons 图标化的设置侧栏（复用 Forgejo 自带的图标集，不自绘）
- 固定 rem 字号阶、8/12 圆角、发丝分隔线，密度显著提高
- 去掉页脚版本号/渲染耗时/"由 Forgejo 提供支持"、去掉所有指向上游官方站的外链
- 匿名访客直达登录页，不看产品营销首页

对照图见 `../artifacts/shots/profile_upstream.png` 与 `profile_ours.png`。

> ⚠️ **这组图证明不了配色改造。** 复核发现 `profile_upstream.png` 拍摄时主题
> **已经生效**（图里的 logo 和标签下划线都是靛蓝，不是上游橙）。它能证明的是
> 密度、页脚、侧栏这些**布局层**差异，**证明不了 `#c2410c` → `#454b8c`**。
> 上游橙色那一版当时没留截图，本仓不补拍也不凭记忆描述——配色一项以
> `theme/theme-acme.css` 里的变量定义为准。
