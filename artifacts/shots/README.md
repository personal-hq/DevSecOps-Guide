# 截图证据

这些不是插图，是**证据**。每张图下面写清它能证明什么、不能证明什么——
拿一张图去证明它证明不了的事，就是 [`00-principles.md`](../../00-principles.md)
第二条说的那种自欺。

| 文件 | 能证明 | 不能证明 |
|---|---|---|
| `登录页.png` | 未登录直达登录页（`LANDING_PAGE=login`）、登录页整体版式 | — |
| `final_login.png` | 登录页定版：logo、字体、圆角、发丝线 | — |
| `仓库页.png` | 仓库列表的密度与信息层级 | — |
| `代码视图.png` | 代码视图配色与行高 | 语法高亮的完整色板（样本代码覆盖不全） |
| `表单页-新建组织.png` | 表单控件尺寸、标签对齐、帮助文字位置 | — |
| `final_profile.png` | 个人页定版（含被 `.page-content.user` 泄漏修好后的搜索框宽度） | — |
| `profile_ours.png` / `profile_upstream.png` | 密度、页脚、侧栏的前后差异 | **⚠️ 证明不了配色**：`profile_upstream.png` 拍摄时主题已生效（图里 logo 和标签下划线已是靛蓝），不是上游橙 `#c2410c` |
| `icons_inline.png` | 设置侧栏用 Octicons 内联渲染成功 | 「全站」覆盖率——只拍到了侧栏一处 |
| `admin_octicons.png` | 管理后台页面的排版 | **图上是纯文字，没有图标**——不能用来证明管理侧栏已图标化 |
| `logos.png` | logo 候选方案并排对照 | — |

## 已知拍摄局限

截图由 [`tools/screenshot-pipeline`](../../tools/screenshot-pipeline/) 生成，
走 `file://` 加载本地 HTML，因此：**头像等跨域资源显示为破图**、
**`mask-image` 图标可能空白**、**客户端渲染的页面拍不到**。
这些是管线限制，**不是主题 bug**——详见该目录的 README。
