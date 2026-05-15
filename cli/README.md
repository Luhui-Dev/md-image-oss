# md-image-oss (CLI)

把 Markdown / MDX / HTML 文档里的图片上传到阿里云 OSS，并自动重写文档里的图片链接。

完整使用文档（含 Obsidian 插件、配置项、退出码、安全建议）见仓库根 README：
<https://github.com/Luhui-Dev/md-image-oss/blob/main/README.md>

## 安装

```bash
pip install -e .          # 从本目录安装（开发）
# 或
pip install md-image-oss  # 后续发布到 PyPI 后
```

## 快速上手

```bash
cp .env.example .env && $EDITOR .env
md-oss article.md --env-file .env -i
```

## 项目布局

```
cli/                  # 本目录 = Python 项目根 + 包源码
├── pyproject.toml
├── requirements.txt
├── .env / .env.example
├── __init__.py       # __version__
├── __main__.py       # python -m cli
├── cli.py            # md-oss 入口
├── compressor.py
├── config.py
├── processor.py
└── uploader.py
```
