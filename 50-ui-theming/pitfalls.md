# 踩过的坑

十条，都在给 Forgejo 做主题化时真实踩过。每条按**症状 → 根因 → 修法**展开，
能给代码的给代码。方法对任何"CSS 变量 + UI 框架 + 允许自定义静态资源"的
Web 应用通用，不止 Forgejo。

## 索引

| # | 症状一句话 | 根因类别 |
|---|---|---|
| [1](#1-主题是整体替换不是叠加) | 没碰过的组件边框/底色凭空消失 | 主题替换机制 |
| [2](#2-tailwind-工具类带-important) | 明明特异度更高，规则还是不生效 | `!important` |
| [3](#3-页面级作用域族的特异度) | 表单标签宽度覆盖只在部分页面生效 | 特异度 |
| [4](#4-page-contentuser-作用域泄漏) | 个人主页按钮被撑成整行、输入框变空盒子 | 作用域泄漏 |
| [5](#5-裸-item-选择器压垮折叠分组) | 展开侧栏分组时文字互相压 | 选择器过宽 |
| [6](#6-按钮类没有-ui-前缀) | 管理后台按钮样式完全不生效 | 类名假设错误 |
| [7](#7-逐行正则批量改-css-会破坏注释) | 配色还在，后半个文件规则全失效 | 工具破坏文件结构 |
| [8](#8-mask-image-受跨源限制) | 图标遮罩渲染成空白 | 跨源限制 |
| [9](#9-default_theme-不覆盖已有账号) | 登出是新主题，一登录变回旧的 | 数据写入时机 |
| [10](#10-静态资源缓存-6h-且-url-不带内容哈希) | 改完主题刷新页面还是旧样式 | 缓存 |

---

<a id="1"></a>
## 1. 主题是整体替换不是叠加

**症状**：某个边框或底色凭空消失，但你根本没碰过那个组件。

**根因**：选中自定义主题后，Forgejo 不再加载它自己的 `theme-forgejo-light.css`。
原主题定义过、你没重新定义的变量全部变成未定义 —— 而 CSS 里一个无法解析的
`var()` 会让**整条声明作废**，不是回退到默认值。首次审计结果：272 个变量里
缺 58 个，其中 24 个因为被裸引用会真的断。

这条是全篇的地基，机制和变量审计方法已经在
[theming-guide.md 第一、三节](theming-guide.md) 写过，这里不重复，只做索引。
审计脚本见 [`../tools/audit-css-vars.py`](../tools/audit-css-vars.py)。

## 2. Tailwind 工具类带 `!important`

**症状**：写了一条看起来特异度足够的规则，Forgejo 的元素宽度/间距纹丝不动。

**根因**：Forgejo 把 Tailwind 的工具类直接编译进了 index.css，且**自带
`!important`**：

```css
.tw-max-w-2xl { max-width: 42rem !important; }
```

级联规则里 `!important` 的优先级在特异度判断之前生效，普通规则不管特异度算得
多高都压不住带 `!important` 的规则。

**修法**：同样用 `!important` 反压，这是这里唯一可行的做法，不是偷懒（见
[css-debugging.md](css-debugging.md) 结尾"`!important` 什么时候正当"）：

```css
.page-content.user.link-account .ui.attached.segment.tw-max-w-2xl {
  max-width: 380px !important;
}
```

## 3. 页面级作用域族的特异度

**症状**：给表单标签写的宽度覆盖，只在登录页生效，注册页、新建组织页不生效。

**根因**：Forgejo 给不同表单页的容器元素挂了**多个类**，例如新建组织页是
`.organization.new.org` —— 这是**三个类挂在同一个元素上**，选择器
`.organization.new.org form .inline.field > label` 的特异度算法：

| 选择器片段 | 类型 | 计入 |
|---|---|---|
| `.organization.new.org` | 3 个类 | class ×3 |
| `form` | 类型选择器 | type ×1 |
| `.inline.field` | 2 个类（同一元素） | class ×2 |
| `label`（经 `>`） | 类型选择器 | type ×1 |

合计特异度 **(0, 5, 2)**。而一条通用规则 `.ui.form .inline.field > label`
只有 `.ui .form` + `.inline .field` + `label` = **(0, 4, 1)**，class 位上
4 < 5，比较到这一位就已经输了，通用选择器压不住。

**这套作用域不是只有一份**：Forgejo 对同一组表单页至少铺了两族"页面作用域 +
`!important`"覆盖，每族覆盖的页面集合并不完全相同（例如标签宽度那族和
`.help`/`.header` 缩进那族，成员就有出入）。下面是两族的并集，**逐条 grep
index.css 得到**，不是猜的：

```
.page-content.install    .user.activate         .user.forgot.password
.user.link-account       .user.reset.password    .user.signin
.user.signup              .repository.new.migrate .repository.new.fork
.repository.new.repo      .organization.new.org   .moderation.new-report
```

**修法**：逐作用域对齐，且只对齐你要覆盖的那条规则实际命中的作用域集合——
不要假设"一族坑"里所有成员对每条属性都成立，每次都从 index.css 里现查：

```bash
grep -o '\.[a-z-]*\.[a-z.-]*\bform\b[^{]*{[^}]*!important[^}]*}' index.css
```

## 4. `.page-content.user` 作用域泄漏

**症状**：给登录页写的按钮样式，把个人主页搜索框旁边的按钮撑成了整行，
输入框被挤成一个 24px 宽的空盒子——看起来像"搜索框左边凭空多出一个空格子"。

**根因**：认证类页面的作用域是 `.page-content.user.signin`（以及
`.signup`/`.activate` 等），但 `.page-content.user` **不是认证页专属**——
个人主页是 `.page-content.user.profile`，用户设置是
`.page-content.user.settings`，都以 `.page-content.user` 开头。只写父类会
把认证页的样式一并泄漏到这两个页面：

```css
/* 错：以为只命中登录/注册页，实际连个人主页、用户设置都命中 */
.page-content.user .ui.form .ui.button { width: 100%; }
```

**修法**：把父类换成完整的认证页作用域列表，一个都不能省：

```css
.page-content.user.signin .ui.form .ui.button,
.page-content.user.signup .ui.form .ui.button,
.page-content.user.activate .ui.form .ui.button,
.page-content.user.forgot.password .ui.form .ui.button,
.page-content.user.reset.password .ui.form .ui.button,
.page-content.user.link-account .ui.form .ui.button { width: 100%; }
```

这条坑和"看起来像空盒子、实际是另一个元素被撑大"的诊断过程，在
[css-debugging.md](css-debugging.md) 里有完整的量测记录。

## 5. 裸 `.item` 选择器压垮折叠分组

**症状**：管理后台侧栏的可折叠分组一展开，`<summary>` 文字和子菜单项挤在
同一行、互相压字。

**根因**：可折叠分组是 `<details class="item toggleable-item">`——**它自己
也带 `.item` 类**。给 `.item` 加 `display:flex` 时，这条规则连 `<details>`
本身也命中了，把它从默认的 `block`（用来纵向堆叠 `<summary>` 和子菜单
`<div class="menu">`）也改成了 `flex`，两个直接子元素被拉成横排。

```css
/* 错：连 details.toggleable-item 一起改成了 flex */
.item { display: flex; align-items: center; gap: 9px; }
```

**修法**：把选择器收窄到 `a.item`，只命中真正的链接项，不动 `<details>`
本身；`<summary>` 需要的横排效果单独用
`details.toggleable-item > summary` 给：

```css
.ui.vertical.menu a.item,
.ui.vertical.menu details.toggleable-item > summary {
  display: flex; align-items: center; gap: 9px;
}
```

## 6. 按钮类没有 `.ui` 前缀

**症状**：给管理后台的维护操作按钮（重建索引、垃圾回收之类）写样式，
`.ui.primary.button` 选择器完全不命中，元素在 DOM 里明明存在。

**根因**：Forgejo 里绝大多数按钮都是 `class="ui primary button"`，但管理
后台的维护操作按钮是 `class="primary button"`——**没有 `.ui`**。这是个类名
假设错误，不是特异度或作用域问题，`querySelectorAll` 一测就知道（见
[css-debugging.md](css-debugging.md) 第一步）。

**修法**：按实际类名写，并用 `.page-content.admin` 限定范围，避免这条更宽的
选择器意外命中其它页面上真正带 `.ui` 的主色按钮：

```css
.page-content.admin .primary.button { /* 不是 .ui.primary.button */
  background: var(--color-box-body);
  border: 1px solid var(--color-input-border);
}
```

## 7. 逐行正则批量改 CSS 会破坏注释

**症状**：用脚本批量替换了文件里某段注释的开头文字后，回去看页面——配色还
在（`:root` 在文件前部，没受影响），但**文件后半段的规则全部失效**，没有
任何报错，肉眼看括号配对也看不出问题。

**根因**：正则替换只换掉了注释的**开头**部分，注释原本的结尾标记 `*/`
被留在了原地，而这段注释的**正文**因为开头的 `/*` 被替换掉，不再处于注释
内部，变成了裸露的 CSS 文本。解析器从这里开始，把这段本该是中文说明的文字
当成选择器/声明去解析，一路混乱到原来那个孤立的 `*/`——**期间它静默吞掉了
所有后续规则**，直到某个地方重新对齐或者文件结束。

括号计数查不出这个问题；简单数 `/*` 和 `*/` 的个数也靠不住——如果注释正文
里本身写了类似 `/admin/actions/*` 这样的路径，字符层面就会让计数失真，
分不清哪个是真正的注释边界。

**修法**：不要用"看起来对不对""数括号"这种目视/计数手段判断改动是否安全。
唯一可靠的判据是**规则有没有真的生效**——挑几个改动点前后的选择器，跑
`getComputedStyle` 看计算值有没有变化（方法见
[css-debugging.md](css-debugging.md)）。批量改动 CSS 注释这类操作，改完
必须过一遍这个检查，不能只凭视觉扫一遍文件。

## 8. `mask-image` 受跨源限制

**症状**：本地用 `file://` 打开页面做验证时，用 `mask-image` 引用的图标
全部渲染成空白，图标该出现的地方什么都没有。

**根因**：实测确认，`file://` 页面里的 `mask-image`/`-webkit-mask-image`
引用跨源的 `http://` 资源（例如实例自己 serve 的 SVG）会被当作跨源资源
拒绝，遮罩直接空白，不报错、不降级。

**修法**：不要引用外部 URL，把 SVG **内联成 data URI**：

```css
a.item::before {
  content: ""; width: 16px; height: 16px;
  background: currentColor;
  mask: url("data:image/svg+xml,%3Csvg...%3E") no-repeat center / 16px;
}
```

内联同时省掉了每个图标一轮网络请求，也不怕上游改资源路径。

## 9. `DEFAULT_THEME` 不覆盖已有账号

**症状**：改了 `app.ini` 里的 `DEFAULT_THEME` 并重启，登出状态看到的是新
主题；一登录进已有账号，界面**变回旧主题**。

**根因**：Forgejo 在账号**创建时**就把当时生效的默认主题写死进了 `user`
表的一个字段。`DEFAULT_THEME` 只对"这个字段为空/新建账号"的场景生效，
已有账号的这个字段不会因为配置变了而跟着变。

**修法**：对已有账号直接改数据库：

```bash
docker compose exec -T db psql -U forgejo -d forgejo \
  -c "UPDATE \"user\" SET theme='<名>';"
```

## 10. 静态资源缓存 6h 且 URL 不带内容哈希

**症状**：改完主题 CSS 或图标文件，强刷也好、等几分钟也好，页面上看到的
还是旧样式。

**根因**：Forgejo 静态资源 URL 后面带的 `?v=` 只跟**应用自身的版本号**
走，不是文件内容哈希——改文件内容，URL 不变，缓存（默认 6 小时）照样命中
旧文件。

**修法**，两条路，二选一：

- 改文件名换一个新 URL（副作用：文件名即主题名，等于顺带改了主题名）；
- 把 `[server] STATIC_CACHE_TIME` 在迭代期间调短（比如 `1m`），定型后再
  改回 `6h`。

**注意**：如果这个配置是通过 docker compose 的环境变量设的，**把环境变量
从 compose 文件里删掉不会把已经写入 `app.ini` 的键删掉**——环境变量只在
首次生成配置时起作用，后续必须直接改 `app.ini` 文件本身。
