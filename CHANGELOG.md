# Changelog

本项目版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。
变更记录格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

版本号的唯一来源是 [`md_image_oss/__init__.py`](md_image_oss/__init__.py) 里的 `__version__`，

## [0.2.0] - 2026-05-06

### Added

- 支持 `.mdx` 文件：MDX 是 Markdown 的超集，原有三种图片语法（`![]()` / `<img>` / `[ref]: url`）直接复用。
- 支持 `.html` / `.htm` 文件，新增 `HtmlProcessor`，跳过 `<script>` / `<style>` / `<pre>` / `<code>` / `<!-- -->` 五类区域。
- CLI 按文件后缀自动分派 processor；不支持的后缀返回 exit code 2。

### Changed

- `processor.py` 重构：抽出 `_BaseProcessor` 共享上传 / 压缩 / 缓存 / 统计逻辑，`MarkdownProcessor` 与 `HtmlProcessor` 各自实现 `process()`。
- README、CLI 帮助文本、`pyproject.toml` 描述与 keywords 同步从 "Markdown article" 改为 "Markdown / MDX / HTML document"。

### Notes

- MDX 中 JSX 表达式形式的 `src={变量}` 不会被改写（只重写带引号的字符串字面量），这是有意为之。
- HTML 中的 `srcset`、`<picture><source>`、CSS `background-image: url(...)` 暂不处理。

## [0.1.0] - 2026-05-06

### Added

- 初始版本：把 Markdown 文章里的图片上传到阿里云 OSS，本地压缩后重写文档链接。
- 支持 `![alt](url)` / `![alt](url "title")` / `<img src="...">` / 引用式 `[label]: url` 四种写法。
- Markdown 围栏代码块（` ``` `、`~~~`）与行内代码内的内容不被改写。
- JPEG progressive + quality 85、PNG 无损优化、WebP method=6；GIF / SVG 不压缩但仍上传。
- 内容哈希作为 OSS 对象名，重复内容不重复上传。
- CLI：`-i/--in-place`、`-o/--output`、`-q/--quality`、`--no-compress`、`--process-remote`、`--env-file`、`--dry-run`、`--quiet`。
- 全部凭据从环境变量读取（`OSS_ACCESS_KEY_ID` 等），支持 `.env` 文件。
