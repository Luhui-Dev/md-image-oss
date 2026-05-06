"""Markdown processor: find images, upload them, rewrite the article.

Handles three kinds of image references:
1. Markdown syntax:  ![alt](url)  or  ![alt](url "title")
2. HTML syntax:      <img src="url" ...>
3. Reference style:  [id]: url   (with  ![alt][id]  used elsewhere)

Code blocks (fenced ``` and inline `code`) are left untouched so that
example markdown in tutorials isn't accidentally rewritten.
"""

from __future__ import annotations

import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Tuple

from .compressor import compress_image
from .uploader import OSSUploader


# ![alt](url)  or  ![alt](url "title")  or  ![alt](<url with spaces>)
_MD_IMAGE_RE = re.compile(
    r"""
    !\[(?P<alt>[^\]]*)\]      # ![alt]
    \(\s*                      # opening (
    (?:
      <(?P<url_a>[^>]+)>       # <url with spaces>
      |
      (?P<url_b>[^\s)]+)       # plain url
    )
    (?:\s+(?P<quote>["'])(?P<title>.*?)(?P=quote))?
    \s*\)
    """,
    re.VERBOSE,
)

# <img ...>
_HTML_IMG_RE = re.compile(r"<img\b([^>]*)>", re.IGNORECASE)
_HTML_SRC_RE = re.compile(r"""src\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

# [label]: url   or   [label]: <url>   ...optional "title"
_REF_DEF_RE = re.compile(
    r"""
    ^(?P<indent>\ {0,3})            # up to 3 leading spaces
    \[(?P<label>[^\]]+)\]:\s*       # [label]:
    (?:
      <(?P<url_a>[^>]+)>
      |
      (?P<url_b>\S+)
    )
    (?P<rest>.*)$                    # title etc.
    """,
    re.VERBOSE,
)

# Strip out fenced code blocks and inline code so we don't touch their content.
_CODE_BLOCK_RE = re.compile(
    r"```.*?```|~~~.*?~~~|`[^`\n]+`",
    re.DOTALL,
)


class MarkdownProcessor:
    def __init__(
        self,
        uploader: OSSUploader,
        compress: bool = True,
        quality: int = 85,
        process_remote: bool = False,
        verbose: bool = True,
    ):
        self.uploader = uploader
        self.compress = compress
        self.quality = quality
        self.process_remote = process_remote
        self.verbose = verbose
        self._cache: dict[str, str] = {}
        self.stats = {"found": 0, "uploaded": 0, "skipped": 0, "failed": 0}

    # ------------------------------------------------------------------ public

    def process(self, content: str, base_dir: Path) -> str:
        """Rewrite the markdown so every image points to OSS."""
        # Split out code blocks; only process the prose between them.
        out_parts: list[str] = []
        cursor = 0
        for m in _CODE_BLOCK_RE.finditer(content):
            if m.start() > cursor:
                out_parts.append(self._rewrite(content[cursor:m.start()], base_dir))
            out_parts.append(m.group(0))
            cursor = m.end()
        if cursor < len(content):
            out_parts.append(self._rewrite(content[cursor:], base_dir))
        return "".join(out_parts)

    # ----------------------------------------------------------------- private

    def _rewrite(self, text: str, base_dir: Path) -> str:
        text = _MD_IMAGE_RE.sub(lambda m: self._md_replace(m, base_dir), text)
        text = _HTML_IMG_RE.sub(lambda m: self._html_replace(m, base_dir), text)
        text = self._rewrite_references(text, base_dir)
        return text

    def _md_replace(self, match: re.Match, base_dir: Path) -> str:
        alt = match.group("alt")
        url = match.group("url_a") or match.group("url_b") or ""
        title = match.group("title")
        new_url = self._maybe_upload(url, base_dir)
        if title is not None:
            quote = match.group("quote") or '"'
            return f"![{alt}]({new_url} {quote}{title}{quote})"
        return f"![{alt}]({new_url})"

    def _html_replace(self, match: re.Match, base_dir: Path) -> str:
        attrs = match.group(1)

        def src_sub(m: re.Match) -> str:
            new_url = self._maybe_upload(m.group(1), base_dir)
            return f'src="{new_url}"'

        new_attrs = _HTML_SRC_RE.sub(src_sub, attrs)
        return f"<img{new_attrs}>"

    def _rewrite_references(self, text: str, base_dir: Path) -> str:
        out_lines = []
        for line in text.splitlines(keepends=True):
            stripped = line.rstrip("\n").rstrip("\r")
            m = _REF_DEF_RE.match(stripped)
            if not m:
                out_lines.append(line)
                continue
            url = m.group("url_a") or m.group("url_b") or ""
            # Reference definitions can point to non-images; we still try to
            # upload, and if reading fails we leave the URL alone.
            new_url = self._maybe_upload(url, base_dir)
            rebuilt = f"{m.group('indent')}[{m.group('label')}]: {new_url}{m.group('rest')}"
            ending = line[len(stripped):]  # preserve original line ending
            out_lines.append(rebuilt + ending)
        return "".join(out_lines)

    def _maybe_upload(self, url: str, base_dir: Path) -> str:
        url = url.strip()
        if not url or url.startswith(("data:", "#", "mailto:")):
            return url

        if url in self._cache:
            return self._cache[url]

        is_remote = url.startswith(("http://", "https://"))

        if is_remote and self.uploader.is_own_url(url):
            self._log(f"  ⏭  already on OSS: {url}")
            self._cache[url] = url
            self.stats["skipped"] += 1
            return url

        if is_remote and not self.process_remote:
            self._log(f"  ⏭  skipping remote: {url}")
            self._cache[url] = url
            self.stats["skipped"] += 1
            return url

        self.stats["found"] += 1

        try:
            data, ext = self._read_image(url, base_dir)
        except Exception as e:
            self._log(f"  ⚠  read failed for {url}: {e}")
            self.stats["failed"] += 1
            return url

        original_size = len(data)
        if self.compress:
            try:
                data, ext = compress_image(data, ext, self.quality)
            except Exception as e:
                self._log(f"  ⚠  compress failed for {url}: {e}")

        try:
            new_url = self.uploader.upload(data, ext)
        except Exception as e:
            self._log(f"  ⚠  upload failed for {url}: {e}")
            self.stats["failed"] += 1
            return url

        saved = original_size - len(data)
        pct = (saved / original_size * 100) if original_size else 0
        self._log(
            f"  ✓ {url}\n"
            f"      → {new_url}\n"
            f"      {_fmt_size(original_size)} → {_fmt_size(len(data))}"
            + (f"  (-{pct:.0f}%)" if saved > 0 else "")
        )
        self._cache[url] = new_url
        self.stats["uploaded"] += 1
        return new_url

    def _read_image(self, url: str, base_dir: Path) -> Tuple[bytes, str]:
        if url.startswith(("http://", "https://")):
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "md-image-oss/0.1 (+https://github.com/)"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            ext = Path(urllib.parse.urlparse(url).path).suffix or ".jpg"
            return data, ext

        decoded = urllib.parse.unquote(url)
        # Strip any in-page fragment / query string from local paths.
        decoded = decoded.split("#", 1)[0].split("?", 1)[0]
        path = Path(decoded)
        if not path.is_absolute():
            path = base_dir / path
        with open(path, "rb") as f:
            data = f.read()
        return data, path.suffix or ".jpg"

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, file=sys.stderr)


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
