"""納品物（ZIP / txt / EPUB）の生成サービス。

`src/cli/main.py` の `autonovel export` が参照するモジュール。
以前は ``src.services.export_service`` が存在せず、CLI の export サブコマンドが
``ImportError`` で必ず失敗していた（HTTP の ``/easy_mode/export/{book_id}``
は別の経路で ZIP を組み立てているため、CLI だけが壊れていた）。

ここでは同期セッション（``BookRepository``）だけで完結する実装にする。
HTTP 経路のようにイベントループや UnitOfWork を要求しないので、
CLI / スクリプト / 運用>from コマンドのどこからでも呼べる。
"""

from __future__ import annotations

import html
import json
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from src.backend.config import ROOT_DIR

__all__ = ["ExportService", "ExportError", "SUPPORTED_FORMATS"]

#: 出力先デフォルト（リポジトリ直下の ``output/``）
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"

SUPPORTED_FORMATS = ("zip", "txt", "epub")


class ExportError(RuntimeError):
    """エクスポートに失敗したことを示すエラー。"""


def _win_txt(text: str) -> bytes:
    """Windows のメモ帳でも文字化けしない UTF-8(BOM) + CRLF へ変換する。"""
    crlf = text.replace("\r\n", "\n").replace("\n", "\r\n")
    return b"\xef\xbb\xbf" + crlf.encode("utf-8")


class ExportService:
    """作品データを読み、納品用ファイルを組み立て、ディスクへ保存する。"""

    def __init__(self, repo: Any = None, output_dir: Path | str | None = None) -> None:
        """
        Args:
            repo: ``BookRepository`` 互換オブジェクト。未指定なら同期セッションで生成する。
            output_dir: 保存先ディレクトリ。既定は ``<repo root>/output``。
        """
        self._repo = repo
        self._output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR

    # ------------------------------------------------------------------ 公開 API

    def export(
        self,
        book_id: int,
        fmt: str = "zip",
        output_dir: Path | str | None = None,
        out_path: Path | str | None = None,
    ) -> dict[str, Any]:
        """作品をエクスポートしてファイルとして保存する。

        Args:
            book_id: 対象作品 ID。
            fmt: ``zip`` / ``txt`` / ``epub``。
            output_dir: 保存先ディレクトリ（上書き）。
            out_path: 保存先ファイルパス。指定時は拡張子を format に合わせる。
                親ディレクトリが無い場合は作る。

        Returns:
            ``{"status": "done", "book_id": ..., "format": ..., "path": ..., "bytes": ...}``

        Raises:
            ExportError: 形式が非対応、作品が見つからない、保存に失敗した場合。
        """
        if fmt not in SUPPORTED_FORMATS:
            raise ExportError(f"未対応の形式です: {fmt!r}（対応: {', '.join(SUPPORTED_FORMATS)}）")

        data = self._load(book_id)

        suffix = {"zip": ".zip", "txt": ".txt", "epub": ".epub"}[fmt]
        if out_path:
            path = Path(out_path)
            # 明示された拡張子が format と食い違う場合は format を優先する。
            if path.suffix.lower() != suffix:
                path = path.with_suffix(suffix)
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            target_dir = Path(output_dir) if output_dir else self._output_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            path = target_dir / f"export_{book_id}{suffix}"

        if fmt == "zip":
            payload = self._build_zip(data)
        elif fmt == "txt":
            payload = _win_txt(self._build_plain_text(data))
        else:
            payload = self._build_epub(data, book_id)

        path.write_bytes(payload)
        return {
            "status": "done",
            "book_id": book_id,
            "format": fmt,
            "path": str(path),
            "bytes": len(payload),
            "episodes": len(data["chapters"]),
        }

    # ------------------------------------------------------------------ 読み込み

    def _open_repo(self) -> Any:
        if self._repo is not None:
            return self._repo
        from src.backend import database
        from src.backend.database.repository import BookRepository

        return BookRepository(database.SessionLocal())

    def _load(self, book_id: int) -> dict[str, Any]:
        repo = self._open_repo()
        book = repo.get_book(book_id)
        if book is None:
            raise ExportError(f"作品が見つかりません: book_id={book_id}")

        chapters = repo.get_all_non_anchor_chapters(book_id)
        characters = repo.get_all_characters(book_id)
        bible = repo.get_latest_bible(book_id)
        plots = repo.get_all_plots(book_id)

        return {
            "book": book,
            "chapters": sorted(chapters, key=lambda c: c.ep_num),
            "characters": characters,
            "bible": bible,
            "plots": sorted(plots, key=lambda p: p.ep_num),
        }

    # ------------------------------------------------------------------ 本文

    def _body_text(self, data: dict[str, Any]) -> str:
        book = data["book"]
        header = f"■ 作品タイトル: {book.title}\n■ ジャンル・区分: {book.genre}\n\n"
        return header + "".join(f"第{c.ep_num}話 {c.title or ''}\n\n{c.content or ''}\n\n" for c in data["chapters"])

    def _build_plain_text(self, data: dict[str, Any]) -> str:
        book = data["book"]
        lines = [
            f"■ 作品タイトル: {book.title}",
            f"■ ジャンル・区分: {book.genre}",
            f"■ 総話数: {len(data['chapters'])}",
            "",
            "─" * 40,
            "",
        ]
        for c in data["chapters"]:
            lines.append(f"第{c.ep_num}話 {c.title or ''}")
            lines.append("")
            lines.append(c.content or "")
            lines.append("")
            lines.append("─" * 40)
            lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------ ZIP

    def _build_zip(self, data: dict[str, Any]) -> bytes:
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("01_本文.txt", _win_txt(self._body_text(data)))
            z.writestr(
                "02_キャラクター・世界観設定集.txt",
                _win_txt(self._build_settings_text(data)),
            )
            z.writestr("03_プロット概要.txt", _win_txt(self._build_plot_text(data)))
            z.writestr(
                "04_データダンプ.json",
                json.dumps(self._build_dump(data), ensure_ascii=False, indent=2),
            )
        return buf.getvalue()

    def _build_settings_text(self, data: dict[str, Any]) -> str:
        bible = data["bible"]
        settings_text = ""
        if bible is not None and bible.settings:
            raw = bible.settings
            if isinstance(raw, (dict, list)):
                settings_text = json.dumps(raw, ensure_ascii=False, indent=2)
            else:
                try:
                    settings_text = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
                except (json.JSONDecodeError, TypeError, ValueError):
                    settings_text = str(raw)

        out = f"【世界観設定】\n{settings_text}\n\n【キャラクター設定】\n"
        for c in data["characters"]:
            out += f"■ {c.name} ({c.role or ''})\n性格: {c.personality or ''}\n能力: {c.ability or ''}\n\n"
        return out

    def _build_plot_text(self, data: dict[str, Any]) -> str:
        out = "【プロット概要】\n"
        for p in data["plots"]:
            out += f"第{p.ep_num}話: {p.title or ''}\n{p.one_line_summary or p.summary or ''}\n\n"
        if not data["plots"]:
            out += "（プロットが登録されていません）\n"
        return out

    def _build_dump(self, data: dict[str, Any]) -> dict[str, Any]:
        book = data["book"]
        return {
            "book_id": book.id,
            "title": book.title,
            "genre": book.genre,
            "target_eps": book.target_eps,
            "chapters": [{"ep_num": c.ep_num, "title": c.title, "content": c.content} for c in data["chapters"]],
            "characters": [
                {
                    "name": c.name,
                    "role": c.role,
                    "personality": c.personality,
                    "ability": c.ability,
                }
                for c in data["characters"]
            ],
            "plots": [
                {"ep_num": p.ep_num, "title": p.title, "one_line_summary": p.one_line_summary} for p in data["plots"]
            ],
        }

    # ------------------------------------------------------------------ EPUB

    def _build_epub(self, data: dict[str, Any], book_id: int) -> bytes:
        """EPUB 3（EPUB 2 compatible）を最小構成で組み立てる。

        ``mimetype`` は非圧縮で先頭に置く必要がある（OCF 仕様）。
        """
        book = data["book"]
        chapters = data["chapters"]
        book_uuid = f"autonovel-book-{book_id}"
        modified = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        title = book.title or f"作品 {book_id}"

        items, spine_refs, nav_lis = [], [], []
        for idx, c in enumerate(chapters, start=1):
            ch_id = f"chapter{idx:04d}"
            items.append(f'<item id="{ch_id}" href="{ch_id}.xhtml" media-type="application/xhtml+xml"/>')
            spine_refs.append(f'<itemref idref="{ch_id}"/>')
            nav_lis.append(f'<li><a href="{ch_id}.xhtml">第{c.ep_num}話 {html.escape(c.title or "")}</a></li>')

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<container version="1.0" '
                'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                "  <rootfiles>\n"
                '    <rootfile full-path="OEBPS/content.opf" '
                'media-type="application/oebps-package+xml"/>\n'
                "  </rootfiles>\n"
                "</container>\n",
            )
            z.writestr(
                "OEBPS/nav.xhtml",
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<html xmlns="http://www.w3.org/1999/xhtml" '
                'xmlns:epub="http://www.idpf.org/2007/ops">\n'
                "<head><title>目次</title></head>\n<body>\n"
                '<nav epub:type="toc"><h1>目次</h1><ol>\n' + "\n".join(nav_lis) + "\n</ol></nav>\n</body>\n</html>\n",
            )
            z.writestr(
                "OEBPS/content.opf",
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
                'unique-identifier="bookid">\n'
                '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
                f'    <dc:identifier id="bookid">urn:uuid:{book_uuid}</dc:identifier>\n'
                f"    <dc:title>{html.escape(title)}</dc:title>\n"
                f"    <dc:language>ja</dc:language>\n"
                f'    <meta property="dcterms:modified">{modified}</meta>\n'
                "  </metadata>\n"
                "  <manifest>\n"
                '    <item id="nav" href="nav.xhtml" '
                'media-type="application/xhtml+xml" properties="nav"/>\n' + "\n".join(items) + "\n  </manifest>\n"
                "  <spine>\n" + "\n".join(spine_refs) + "\n  </spine>\n"
                "</package>\n",
            )
            for idx, c in enumerate(chapters, start=1):
                paragraphs = "".join(
                    f"<p>{html.escape(line)}</p>" for line in (c.content or "").split("\n") if line.strip()
                )
                z.writestr(
                    f"OEBPS/chapter{idx:04d}.xhtml",
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<html xmlns="http://www.w3.org/1999/xhtml">\n'
                    f"<head><title>第{c.ep_num}話</title></head>\n<body>\n"
                    f"<h1>第{c.ep_num}話 {html.escape(c.title or '')}</h1>\n"
                    f"{paragraphs}\n</body>\n</html>\n",
                )
        return buf.getvalue()
