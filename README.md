# md-image-oss

把 Markdown / MDX / HTML 文档里的所有图片上传到阿里云 OSS，并自动重写文档里的图片链接。上传前先做一次高质量的本地压缩，配置全部从环境变量读取。

## 特性

- **多格式支持**：`.md`、`.mdx`、`.html`、`.htm` 都能直接处理，按后缀自动选择解析模式。
- **批量替换**：支持 `![](...)`、`<img src="...">`（含 JSX 自闭合）、引用式 `[label]: url` 三种语法。
- **代码块安全**：Markdown 的围栏代码块（` ``` `、`~~~`）和行内代码、HTML 的 `<script>` / `<style>` / `<pre>` / `<code>` / 注释都不会被误改。
- **高质量压缩**：JPEG progressive + quality 85，PNG 无损优化，WebP method=6；GIF / SVG 等不动。
- **去重上传**：用内容哈希作为文件名，重复内容不会重复上传。
- **配置藏在系统环境**：所有 AccessKey / Endpoint 都从环境变量读取，不进代码也不进文章。
- **覆盖式或非覆盖式**：默认输出到 `xxx.oss.md`，加 `-i` 直接覆盖原文。
- **桌面 GUI 客户端**（v0.3+）：跨平台 Windows / macOS，多文件拖拽、配置引导、操作审计日志。

## 安装

```bash
git clone <this-repo> md-image-oss
cd md-image-oss
pip install -e .                # 仅 CLI
pip install -e ".[gui]"         # CLI + 桌面客户端 (md-oss-gui)
```

或者直接装依赖在仓库目录里跑：

```bash
pip install -r requirements.txt
python -m md_image_oss <article.md>
```

需要 Python 3.9+。

## 配置

把 `.env.example` 复制成 `.env` 并填上你自己的密钥：

```bash
cp .env.example .env
# 编辑 .env
```

| 变量 | 必填 | 说明 |
|---|---|---|
| `OSS_ACCESS_KEY_ID` | ✓ | 阿里云 AccessKey ID |
| `OSS_ACCESS_KEY_SECRET` | ✓ | 阿里云 AccessKey Secret |
| `OSS_ENDPOINT` | ✓ | 区域 Endpoint，例如 `https://oss-cn-hangzhou.aliyuncs.com` |
| `OSS_BUCKET` | ✓ | Bucket 名称 |
| `OSS_PREFIX` | – | 上传到 Bucket 内的路径前缀，例如 `markdown` |
| `OSS_CUSTOM_DOMAIN` | – | 自定义域名 / CDN，用于生成最终 URL |

> 推荐做法是把 `.env` 放到工程目录但 **不要提交**（`.gitignore` 已经帮你排除了），或者直接 `export` 到 shell session 里。

## 命令行用法

```bash
# 在系统已有环境变量的前提下，最简形式：
md-oss article.md
# → 生成 article.oss.md

# 直接覆盖原文：
md-oss article.md --in-place

# 指定输出路径：
md-oss article.md -o dist/article.md

# 临时从 .env 文件加载配置：
md-oss article.md --env-file .env

# 调整压缩质量（1–100，默认 85）：
md-oss article.md -q 90

# 跳过压缩：
md-oss article.md --no-compress

# 把已经在外网的图也搬运一份到自己 OSS（比如别人博客的盗链图）：
md-oss article.md --process-remote

# 预览结果但不写文件，结果走 stdout：
md-oss article.md --dry-run > preview.md

# 静默模式：
md-oss article.md -i --quiet

# MDX / HTML 同样工作，输出后缀跟随输入：
md-oss post.mdx              # → post.oss.mdx
md-oss page.html -i          # 直接覆盖
```

`--in-place` 和 `-o/--output` 互斥；不指定时默认写到 `<原名>.oss<原后缀>`。

## 桌面 GUI 客户端

```bash
pip install -e ".[gui]"
md-oss-gui
```

GUI 客户端基于 PySide6，跨平台支持 Windows 与 macOS，提供：

- **批量处理**：拖拽多个文件 / 文件夹（自动递归扫描 `.md/.mdx/.html/.htm`）
- **覆盖控制**：「覆盖原文件」复选（默认未选），覆盖时同目录生成 `<file>.bak` 备份
- **预览模式**：「Dry-run」复选，仅模拟运行不写入磁盘
- **可取消**：处理过程中可中断，已开始的当前文件会跑完
- **配置引导**：首次启动弹出三标签页的配置对话框（Credentials / Bucket / Advanced），带「测试连接」按钮，支持从 `.env` 文件导入 / 导出
- **凭据安全**：AccessKey ID / Secret 写入系统凭据管理器（macOS Keychain / Windows Credential Manager），不落明文到磁盘

### 操作审计日志

每次启动、配置变更、连接测试、批处理、单文件处理结果都会写入只追加的 JSONL 审计日志，**不**记录 AccessKey 与文件内容：

| 平台 | 路径 |
|---|---|
| macOS | `~/Library/Logs/md-image-oss/audit-YYYY-MM.log` |
| Windows | `%LOCALAPPDATA%\md-image-oss\Logs\audit-YYYY-MM.log` |

GUI 内菜单 → 「View → Audit log…」可表格化查看，并支持「Open log folder」「Export CSV」。日志按月轮转、人工不可在 GUI 内清空（合规要求），如需清理请直接删文件。

### 打包成可分发应用

仓库提供 `build/md-oss-gui.spec` 作为 PyInstaller 配置：

```bash
pip install pyinstaller
# macOS
pyinstaller --clean build/md-oss-gui.spec    # → dist/md-oss-gui.app
# Windows (在 Windows 主机上跑)
pyinstaller --clean build\md-oss-gui.spec    # → dist\md-oss-gui\md-oss-gui.exe
```

签名 / 公证留待发布时按需补上。

## 它替换什么、不替换什么

会替换：
- `![alt](./img.png)` — 相对路径
- `![alt](/abs/path.png)` — 绝对路径
- `![alt](<some image.png>)` — 带尖括号的路径
- `![alt](url "title")` — 带 title
- `<img src="img.png" />` — HTML 标签
- `[ref]: ./img.png` — 引用式定义
- 远程图片（仅当显式开启 `--process-remote`）

不替换：
- `data:` URI、`#` 锚点、`mailto:` 链接
- 已经在你 OSS / 自定义域上的图片
- Markdown 的围栏代码块和行内代码、HTML 的 `<script>` / `<style>` / `<pre>` / `<code>` / 注释里的内容
- MDX 中 JSX 表达式形式的 `src={变量}`（只重写带引号的字符串字面量）
- GIF 和 SVG 不会被压缩（以保留动画 / 矢量），但仍会被上传

## 运行示例

```text
$ md-oss posts/2024-trip.md -i --env-file .env
📖 Reading posts/2024-trip.md
🔄 Processing images...
  ✓ ./images/cover.png
      → https://cdn.example.com/markdown/8b3f9e6a4c1d2e7f9a0b.jpg
      482.1 KB → 138.4 KB  (-71%)
  ✓ ./images/map.jpg
      → https://cdn.example.com/markdown/3a1c4d5e6f7081929394.jpg
      1.2 MB → 410.5 KB  (-67%)
  ⏭  already on OSS: https://cdn.example.com/markdown/...
💾 Overwriting posts/2024-trip.md
✨ Done. found=2 uploaded=2 skipped=1 failed=0
```

## 项目结构

```
md-image-oss/
├── md_image_oss/
│   ├── __init__.py
│   ├── __main__.py      # python -m md_image_oss
│   ├── cli.py           # 命令行入口与参数解析
│   ├── config.py        # 从环境变量加载配置
│   ├── compressor.py    # 基于 Pillow 的图像压缩
│   ├── uploader.py      # OSS 上传（哈希去重）
│   ├── processor.py     # Markdown / HTML 解析 / 重写
│   └── gui/             # 桌面客户端（PySide6, 可选）
│       ├── app.py            # 入口 md-oss-gui
│       ├── main_window.py    # 主窗口
│       ├── settings_dialog.py# 配置引导
│       ├── settings_store.py # QSettings + keyring
│       ├── audit_log.py      # JSONL 审计日志
│       ├── audit_viewer.py   # 审计日志查看器
│       ├── worker.py         # 后台 QThread
│       └── widgets/          # 文件列表 / 日志面板
├── build/
│   └── md-oss-gui.spec  # PyInstaller 打包配置
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## 退出码

- `0` —— 一切顺利。
- `1` —— 输入文件缺失，或至少有一张图片处理失败。
- `2` —— 命令行参数错误。

## 安全建议

- 给这个工具用 **专属的 RAM 子账号**，权限收窄到目标 Bucket 的 `oss:PutObject` / `oss:GetObject` 即可。
- 千万别把 `.env` 或任何含 AccessKey 的文件提交到 Git。
- CI / 服务器环境直接用平台的 secrets，不要落盘 `.env`。

## License

MIT
