"""Document processors: find images, upload them, rewrite the document.

Two processors share the same upload / compress / cache pipeline:

- ``MarkdownProcessor`` handles ``.md`` and ``.mdx``. Recognised image
  references:
    1. Markdown syntax:    ![alt](url)  or  ![alt](url "title")
    2. HTML syntax:        <img src="url" ...>   (also covers JSX in MDX)
    3. Reference style:    [id]: url   (with  ![alt][id]  used elsewhere)
    4. Obsidian wikilink:  ![[image.png]] / ![[image.png|alt|400x200]]
       (only when ``obsidian=True``; skipped for non-image extensions)
  Fenced code blocks (``` and ~~~) and inline `code` are left untouched.

- ``HtmlProcessor`` handles ``.html`` / ``.htm``. Only ``<img src="...">``
  tags are rewritten; ``<script>``, ``<style>``, ``<pre>``, ``<code>`` and
  HTML comments are left untouched.
"""

from __future__ import annotations

import html
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

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

# <img ...>   — matches both HTML (<img src="x">) and JSX (<img src="x" />)
_HTML_IMG_RE = re.compile(r"<img\b([^>]*)>", re.IGNORECASE)
# Only quoted string values; JSX expressions like src={foo} are left alone.
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

# Obsidian wikilink image embed:
#   ![[image.png]]
#   ![[image.png|alt]]            (or  ![[image.png|400]] / 400x200)
#   ![[image.png|alt|400x200]]    (pipe segments in either order)
_OBSIDIAN_IMAGE_RE = re.compile(r"!\[\[(?P<target>[^\]|]+?)(?:\|(?P<params>[^\]]*))?\]\]")

# Size token inside an Obsidian wikilink pipe segment: "400" or "400x200".
_OBSIDIAN_SIZE_RE = re.compile(r"^\d+(?:x\d+)?$")

# Extensions we treat as images. Non-image wikilinks (e.g. ![[some-note]])
# are left untouched so note-transclusions don't get uploaded by accident.
_IMAGE_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".avif", ".bmp", ".tif", ".tiff", ".ico",
})

# Fenced code blocks and inline code in Markdown.
_MD_CODE_RE = re.compile(
    r"```.*?```|~~~.*?~~~|`[^`\n]+`",
    re.DOTALL,
)

# Regions in HTML where we must not rewrite anything.
_HTML_SKIP_RE = re.compile(
    r"""
      <script\b[^>]*>.*?</script\s*>
    | <style\b[^>]*>.*?</style\s*>
    | <pre\b[^>]*>.*?</pre\s*>
    | <code\b[^>]*>.*?</code\s*>
    | <!--.*?-->
    """,
    re.DOTALL | re.IGNORECASE | re.VERBOSE,
)


class _BaseProcessor:
    """Shared upload / compress / cache / stats pipeline."""

    def __init__(
        self,
        uploader: OSSUploader,
        compress: bool = True,
        quality: int = 85,
        process_remote: bool = False,
        verbose: bool = True,
        obsidian: bool = True,
        obsidian_vault: Optional[Path] = None,
    ):
        self.uploader = uploader
        self.compress = compress
        self.quality = quality
        self.process_remote = process_remote
        self.verbose = verbose
        self.obsidian = obsidian
        self._cache: dict[str, str] = {}
        self.stats = {"found": 0, "uploaded": 0, "skipped": 0, "failed": 0}

        # Obsidian vault resolution state (lazy).
        # If the user gave us a path explicitly, use it and skip auto-detection.
        self._obsidian_vault_root: Optional[Path] = (
            obsidian_vault.resolve() if obsidian_vault else None
        )
        self._obsidian_vault_searched: bool = obsidian_vault is not None
        self._obsidian_index: Optional[dict[str, list[Path]]] = None

    # ------------------------------------------------------------------ public

    def process(self, content: str, base_dir: Path) -> str:  # pragma: no cover
        raise NotImplementedError

    # ----------------------------------------------------------------- helpers

    def _split_and_rewrite(
        self,
        content: str,
        base_dir: Path,
        skip_re: re.Pattern[str],
    ) -> str:
        """Run ``self._rewrite`` on the prose, leaving ``skip_re`` regions intact."""
        out_parts: list[str] = []
        cursor = 0
        for m in skip_re.finditer(content):
            if m.start() > cursor:
                out_parts.append(self._rewrite(content[cursor:m.start()], base_dir))
            out_parts.append(m.group(0))
            cursor = m.end()
        if cursor < len(content):
            out_parts.append(self._rewrite(content[cursor:], base_dir))
        return "".join(out_parts)

    def _rewrite(self, text: str, base_dir: Path) -> str:  # pragma: no cover
        raise NotImplementedError

    def _html_replace(self, match: re.Match, base_dir: Path) -> str:
        attrs = match.group(1)

        def src_sub(m: re.Match) -> str:
            new_url = self._maybe_upload(m.group(1), base_dir)
            return f'src="{new_url}"'

        new_attrs = _HTML_SRC_RE.sub(src_sub, attrs)
        return f"<img{new_attrs}>"

    # ----------------------------------------------------------- Obsidian wikilinks

    def _obsidian_replace(self, match: re.Match, base_dir: Path) -> str:
        original = match.group(0)
        target = (match.group("target") or "").strip()
        if not target:
            return original

        # Only treat known image extensions as images; ![[some-note]] etc. are left alone.
        if Path(target).suffix.lower() not in _IMAGE_EXTS:
            return original

        # Split pipe params into size + alt. Size = a segment matching \d+(x\d+)?.
        # The last such segment wins (handles both "alt|400" and "400|alt").
        alt_parts: list[str] = []
        size: Optional[str] = None
        params = match.group("params")
        if params is not None:
            for segment in params.split("|"):
                seg = segment.strip()
                if seg and _OBSIDIAN_SIZE_RE.match(seg):
                    size = seg
                elif seg:
                    alt_parts.append(seg)
        alt = " ".join(alt_parts)

        resolved = self._resolve_obsidian_target(target, base_dir)
        if resolved is None:
            self._log(f"  ⚠  obsidian wikilink not found: {original}")
            self.stats["failed"] += 1
            return original

        new_url = self._maybe_upload(str(resolved), base_dir)
        # If upload itself failed, _maybe_upload returns the input path. Don't
        # write an ugly absolute local path into the document — keep the original
        # wikilink so the user can re-run.
        if new_url == str(resolved):
            return original

        if size:
            if "x" in size:
                w, h = size.split("x", 1)
                dims = f' width="{w}" height="{h}"'
            else:
                dims = f' width="{size}"'
            return f'<img src="{new_url}" alt="{html.escape(alt, quote=True)}"{dims} />'
        return f"![{alt}]({new_url})"

    def _resolve_obsidian_target(self, target: str, base_dir: Path) -> Optional[Path]:
        """Resolve an Obsidian wikilink target to an absolute Path, or None."""
        decoded = urllib.parse.unquote(target)
        rel = Path(decoded)

        # Path-like target (contains a slash): try base_dir, then vault root.
        if rel.parent != Path("."):
            candidate = (base_dir / rel)
            if candidate.is_file():
                return candidate.resolve()
            vault = self._obsidian_vault(base_dir)
            if vault is not None:
                candidate = vault / rel
                if candidate.is_file():
                    return candidate.resolve()
            return None

        # Plain filename: first the common "attachments next to note" case…
        candidate = base_dir / rel
        if candidate.is_file():
            return candidate.resolve()

        # …then a vault-wide filename lookup.
        index = self._obsidian_lookup(base_dir)
        matches = index.get(rel.name.lower(), [])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            joined = ", ".join(str(p) for p in matches)
            self._log(
                f"  ⚠  obsidian wikilink '{target}' is ambiguous "
                f"({len(matches)} matches in vault): {joined}"
            )
            return None
        return None

    def _obsidian_vault(self, base_dir: Path) -> Optional[Path]:
        """Find the Obsidian vault root (auto-detect on first use)."""
        if self._obsidian_vault_searched:
            return self._obsidian_vault_root
        self._obsidian_vault_searched = True
        cur = base_dir.resolve()
        for ancestor in (cur, *cur.parents):
            if (ancestor / ".obsidian").is_dir():
                self._obsidian_vault_root = ancestor
                break
        return self._obsidian_vault_root

    def _obsidian_lookup(self, base_dir: Path) -> dict[str, list[Path]]:
        """Lazy filename → [absolute paths] index of the vault's image files."""
        if self._obsidian_index is not None:
            return self._obsidian_index
        index: dict[str, list[Path]] = {}
        vault = self._obsidian_vault(base_dir)
        if vault is None:
            self._obsidian_index = index
            return index
        for root, dirs, files in os.walk(vault):
            # Skip the .obsidian config directory entirely.
            dirs[:] = [d for d in dirs if d != ".obsidian"]
            for name in files:
                suffix = Path(name).suffix.lower()
                if suffix in _IMAGE_EXTS:
                    index.setdefault(name.lower(), []).append(Path(root, name).resolve())
        self._obsidian_index = index
        return index

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


class MarkdownProcessor(_BaseProcessor):
    """Handles ``.md`` and ``.mdx`` (MDX is a Markdown superset)."""

    def process(self, content: str, base_dir: Path) -> str:
        return self._split_and_rewrite(content, base_dir, _MD_CODE_RE)

    def _rewrite(self, text: str, base_dir: Path) -> str:
        text = _MD_IMAGE_RE.sub(lambda m: self._md_replace(m, base_dir), text)
        text = _HTML_IMG_RE.sub(lambda m: self._html_replace(m, base_dir), text)
        text = self._rewrite_references(text, base_dir)
        # Run Obsidian wikilinks last: their output is standard ![](...) or
        # <img>, which we don't want re-scanned by the earlier passes (it would
        # only inflate the "skipped" stat via the is_own_url check).
        if self.obsidian:
            text = _OBSIDIAN_IMAGE_RE.sub(lambda m: self._obsidian_replace(m, base_dir), text)
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

    def _rewrite_references(self, text: str, base_dir: Path) -> str:
        out_lines = []
        for line in text.splitlines(keepends=True):
            stripped = line.rstrip("\n").rstrip("\r")
            m = _REF_DEF_RE.match(stripped)
            if not m:
                out_lines.append(line)
                continue
            url = m.group("url_a") or m.group("url_b") or ""
            new_url = self._maybe_upload(url, base_dir)
            rebuilt = f"{m.group('indent')}[{m.group('label')}]: {new_url}{m.group('rest')}"
            ending = line[len(stripped):]
            out_lines.append(rebuilt + ending)
        return "".join(out_lines)


class HtmlProcessor(_BaseProcessor):
    """Handles ``.html`` / ``.htm``. Only ``<img>`` tags are rewritten."""

    def process(self, content: str, base_dir: Path) -> str:
        return self._split_and_rewrite(content, base_dir, _HTML_SKIP_RE)

    def _rewrite(self, text: str, base_dir: Path) -> str:
        return _HTML_IMG_RE.sub(lambda m: self._html_replace(m, base_dir), text)


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
