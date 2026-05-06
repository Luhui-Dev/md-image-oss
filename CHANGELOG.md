# Changelog

本项目版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。
变更记录格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

版本号的唯一来源是 [`md_image_oss/__init__.py`](md_image_oss/__init__.py) 里的 `__version__`，

## [0.3.0] - 2026-05-06

### Added

- **桌面 GUI 客户端**（PySide6），跨平台支持 Windows 与 macOS：
  - 拖拽 / 选择多文件，文件夹自动递归扫描 `.md / .mdx / .html / .htm`
  - 「覆盖原文件」复选（默认未选），覆盖时自动备份为 `<file>.bak`
  - 「Dry-run」复选，可在不写入磁盘的情况下预演整个流程
  - 实时日志面板，行级状态（找到 / 上传 / 失败）
  - 处理中可取消，当前文件完成后停止
- **配置引导对话框**：三个标签页（Credentials / Bucket / Advanced），首次启动自动弹出；提供「测试连接」按钮、`.env` 导入 / 导出。
- **审计日志**（JSONL，append-only）：记录 app_start / config_changed / connection_test / batch_start / file_processed / batch_end / app_end 等事件；不记录 AccessKey 与文件内容。
  - 内置审计查看器，支持「打开日志文件夹」「导出 CSV」。
  - 存储位置（`platformdirs`）：macOS `~/Library/Logs/md-image-oss/`、Windows `%LOCALAPPDATA%/md-image-oss/Logs/`。
- **凭据存储**：AccessKey ID / Secret 通过 `keyring` 写入系统凭据管理器（macOS Keychain / Windows Credential Manager），永不落明文磁盘；其余配置走 QSettings。
- 新增可选依赖组 `pip install md-image-oss[gui]` 与入口命令 `md-oss-gui`。

### Changed

- `MarkdownProcessor` / `HtmlProcessor` 新增可选构造参数 `log_callback: Callable[[str], None]`，向 GUI 实时转发日志；CLI 行为完全不变。

### Notes

- 打包：随仓库提供 `build/md-oss-gui.spec`，可使用 PyInstaller 生成 macOS `.app` 与 Windows `.exe`；签名 / 公证留待后续迭代。
- GUI 与 CLI 共享同一份 OSS 配置：可通过 GUI 设置中的「Export .env」导出，再用 CLI `--env-file` 加载。

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
