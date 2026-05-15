# Changelog

本项目版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。
变更记录格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

CLI 版本号在 [`md_image_oss/__init__.py`](md_image_oss/__init__.py) 的 `__version__`；
插件版本号在 [`obsidian-plugin/manifest.json`](obsidian-plugin/manifest.json) 的 `version`。

## Plugin 1.1.0 - 2026-05-15

围绕「降低使用门槛」做的一次 UI 重构：把图片管理器从命令面板深处的弹窗拉到工作区常驻面板，并随笔记内容实时刷新。

### Added

- 左侧 Ribbon 新增 `image-up` 图标，一键打开图片管理面板。
- 右侧持久化面板视图（`ItemView`），跟随活动笔记自动切换，不再依赖 Modal。
- 面板每行新增 **Domain** 列：本地图显示 `本地 · 仓库 → <目标域>`（推算自 `customDomain` 或 `bucket.endpoint`，与 `Uploader.buildUrl` 严格一致），远程图显示 host。
- 状态徽标重整为四态：**本地**（绿）/ **云端**（灰）/ **OSS**（紫）/ **缺失**（红）；新配色用低透明度色块 + Obsidian 命名色变量，跨主题保持对比度可读。
- 每行新增「上传」图标按钮，可对单张图直接发起上传，无需先勾选再走底部 CTA。
- 实时刷新：订阅 `metadataCache.changed`，写文档时面板自动同步图片增删，无需手动刷新。
  - 选中状态与上传中 spinner 使用稳定字符串键 `(kind, rawUrl, 出现序号)`，跨刷新保留用户操作。
  - 扫描结果签名短路：在非图片区域打字时跳过 DOM 重建，避免闪烁。

### Changed

- 「打开图片管理面板」命令、编辑器右键菜单的同名条目现在都打开面板而非弹窗。
- 「切换可见项」按钮改名为「全选」，行为不变（全选/全不选当前可见可勾选项）。
- 文件菜单（笔记 tab `⋯` 更多）下的「上传全部图片」与「打开图片管理面板」两项被移除 —— 已被 Ribbon、命令面板、编辑器右键菜单完全覆盖。
- 插件类内部把 `runPipeline` + `runPipelineForFile` 合并为统一的 `runUpload(file, items)` —— 自动判断目标文件是否有打开的编辑器，分别走 `editor.transaction`（保留 undo）或 `vault.process`。

### Removed

- 删除 `ImageListModal`（已由 `ImagePanelView` 取代）。
- 删除现已无人调用的 `runImageManager*` / `runUploadAllForFile` / `openPanelForFile` 方法。
- i18n 中 `modal.*` 命名空间整体迁移为 `panel.*`。

### Notes

- 选中状态键基于 `(kind, rawUrl, 同 rawUrl 的出现序号)`：在图片上方插入/删除文字时该键不变，所以用户手动取消的勾选不会被后续刷新重新勾上；上传中的 spinner 也不会跳变。
- 「云端」（cloud / `is-remote`）特指非自家 OSS 的远程图；自家 OSS 的资源单独走「OSS」状态。
- 已知小问题：`describeDomain` 返回值仍带 `isOss` 字段、i18n 仍保留 `ossBadge` 字符串，皆为现已无消费者的死代码，下次清理迭代再处理。

## Plugin 1.0.0 - 2026-05-14

首个正式发布版本。

### Added

- 新增 Obsidian 插件形态（[`obsidian-plugin/`](obsidian-plugin/)）—— 在编辑器内一键把当前笔记的图片上传到 OSS 并就地重写链接，不需要切到终端。
- 命令：`上传当前笔记中的所有图片到 OSS（覆盖式）` 与 `打开当前笔记的图片管理面板`。
- 图片管理 Modal：缩略图 + 体积 + 状态徽章（本地 / 已在 OSS / 外链 / 缺失）+ 多选 + 全部/仅本地/尚未上传/缺失过滤。
- Settings 面板：OSS 凭据六字段、压缩开关 + 质量滑块、远程图开关、并发数、连接测试探针；必填项以红色 `*` 标注。
- 国际化：界面根据 Obsidian 的 `localStorage.language` 在中文 / 英文之间自动切换。
- 命名约定与 CLI 完全对齐（`<prefix>/<sha256[:24]>.<ext>`），CLI 上传过的图在插件里自动 `headObject` 短路，反之亦然。
- 并发编辑保护：上传期间笔记被修改，受影响的引用跳过并以 `偏移=N` 报告。
- 仅桌面端（`isDesktopOnly=true`），移动端留待后续里程碑。

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
