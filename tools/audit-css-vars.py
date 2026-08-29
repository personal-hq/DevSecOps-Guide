#!/usr/bin/env python3
"""审计自定义主题相对上游主题缺失的 CSS 自定义属性（变量）。

背景：像 Forgejo 这类应用选中自定义主题后是整体替换上游主题文件，不是叠加。
上游定义过、自定义主题没有重新定义的变量全部变成未定义 —— 而 CSS 里一个无法
解析的 var() 会让整条声明作废（不是回退到默认值）。缺失变量本身不一定要紧：
只有被"裸引用"（var(--x) 不带 fallback）的那些会真的断；带 fallback 的
var(--x, y) 是安全的。这个脚本把"缺了多少"和"缺了会不会炸"分开回答。

用法：
    audit-css-vars.py <上游主题.css> <自己的主题.css> <index.css>

三个参数都是本地文件路径：
    上游主题.css   上游原版主题文件，定义完整的变量集合
    自己的主题.css  替换上游的自定义主题文件，可能遗漏变量
    index.css      实例正在服务的编译产物，用来统计每个变量被怎样引用

输出三个数：
    缺失总数         上游定义了、自己的主题没重新定义的变量个数
    会真的断         其中在 index.css 里存在裸引用（无 fallback）的
    无人引用因而无害   其中在 index.css 里没有裸引用的（未被引用，或只被
                     带 fallback 的形式引用）

退出码：0 = 正常跑完（即使发现"会真的断"的变量，那是审计结果不是脚本错误）；
       2 = 参数或文件错误。
"""
import argparse
import re
import sys
from pathlib import Path

# 变量定义：--name 后面跟着（可选空白 +）冒号 + 至少一个非分号字符。
# 不能限定在行首 —— 压缩风格的 CSS 会把多个定义堆在同一行
# （例如 :root{--a:1;--b:2}），限定行首会漏掉绝大部分，得出一个偏大的假"缺失数"。
VAR_DEF_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*[^;]")

# 变量引用：var(--name 后面第一个非空白字符是 ')' 就是裸引用，是 ',' 就带 fallback。
# 只看这一层就够了——CSS 语法规定 var() 里 name 之后要么直接闭合、要么跟一个逗号
# 引出 fallback，fallback 内部即使还嵌套 var() 也不影响这一层的判断。
VAR_USE_RE = re.compile(r"var\(\s*(--[a-z0-9-]+)\s*([,)])")


def read_css(path_str: str, label: str) -> str:
    path = Path(path_str)
    if not path.exists():
        print(f"错误：{label} 不存在：{path_str}", file=sys.stderr)
        sys.exit(2)
    if not path.is_file():
        print(f"错误：{label} 不是一个文件：{path_str}", file=sys.stderr)
        sys.exit(2)
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"错误：读取 {label} 失败（{path_str}）：{e}", file=sys.stderr)
        sys.exit(2)


def extract_defined_vars(css_text: str) -> set[str]:
    return {m.group(1) for m in VAR_DEF_RE.finditer(css_text)}


def count_bare_refs(css_text: str) -> dict[str, int]:
    """返回 {变量名: 裸引用次数}，只统计不带 fallback 的 var(--x) 用法。"""
    counts: dict[str, int] = {}
    for m in VAR_USE_RE.finditer(css_text):
        name, sep = m.group(1), m.group(2)
        if sep == ")":
            counts[name] = counts.get(name, 0) + 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="audit-css-vars.py",
        description=(
            "对比上游主题与自定义主题的 CSS 变量定义，找出缺失的变量，"
            "再按 index.css 里的裸引用情况判断哪些缺失会真的导致规则失效。"
        ),
        epilog="示例：audit-css-vars.py theme-forgejo-light.css theme-acme.css index.css",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("upstream", help="上游原主题 CSS 文件路径（定义完整变量集）")
    parser.add_argument("own", help="自己的主题 CSS 文件路径（替换上游，可能遗漏变量）")
    parser.add_argument("index_css", help="实例正在服务的编译产物 CSS 路径，用于统计引用")
    args = parser.parse_args()

    upstream_text = read_css(args.upstream, "上游主题文件")
    own_text = read_css(args.own, "自己的主题文件")
    index_text = read_css(args.index_css, "index.css")

    upstream_vars = extract_defined_vars(upstream_text)
    own_vars = extract_defined_vars(own_text)

    if not upstream_vars:
        print(f"警告：{args.upstream} 里一个变量定义都没提取到，检查文件内容或正则是否需要调整。",
              file=sys.stderr)

    missing = sorted(upstream_vars - own_vars)
    bare_refs = count_bare_refs(index_text)

    breaking = [(name, bare_refs.get(name, 0)) for name in missing if bare_refs.get(name, 0) > 0]
    harmless = [name for name in missing if bare_refs.get(name, 0) == 0]
    breaking.sort(key=lambda pair: (-pair[1], pair[0]))

    print(f"上游变量定义数：{len(upstream_vars)}")
    print(f"自己的变量定义数：{len(own_vars)}")
    print(f"缺失总数：{len(missing)}")
    print(f"会真的断：{len(breaking)}")
    print(f"无人引用因而无害：{len(harmless)}")

    if breaking:
        print()
        print("会断的变量（按裸引用次数降序）：")
        name_width = max(len(name) for name, _ in breaking)
        for name, count in breaking:
            print(f"  {name:<{name_width}}  {count} 处裸引用")


if __name__ == "__main__":
    main()
