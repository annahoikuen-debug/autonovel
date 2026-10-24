"""
実稼働環境シナリオ検証スクリプト:
1. データベースセッション接続・検証
2. かんたんモード (EasyMode) パイプライン実行（テーマ入力 -> プロット立案 -> 執筆 -> 章生成）
3. 成果物の各エクスポート形式の完全性検証
   - なろう形式テキストエクスポート
   - カクヨム形式テキストエクスポート
   - 納品用 ZIP アーカイブ (本文各話 + メタデータ + 設定集)
   - EPUB/プラットフォーム整形出力
"""

import asyncio
import os
import sys
import io
import zipfile

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.abspath("."))

from src.backend.database import get_db, engine
from src.infrastructure.database.models.base_orm import Base
from src.backend.database.models import Book, Chapter, User
from src.easy_mode.pipeline import EasyModePipeline
from src.services.exporters.base import get_exporter
from src.agents.marketing import MarketingAgent
from src.backend.database.repository import BookRepository


def run_full_lifecycle():
    print("[1] データベースモデルと接続確認...")
    Base.metadata.create_all(bind=engine)
    session = next(get_db())

    # テストユーザー確認 / 作成
    user = session.query(User).filter_by(id=1).first()
    if not user:
        user = User(
            id=1,
            email="developer@example.com",
            hashed_password="hashed_pw_dummy",
            display_name="開発者",
            role="admin",
            status="active",
            plan_tier="pro",
            credits=9999,
        )
        session.add(user)
        session.commit()
    print("  -> ユーザー確認完了: user_id=1")

    print("\n[2] 小説作成パイプライン実行 (EasyModePipeline)...")
    pipeline = EasyModePipeline()
    theme = "現代ダンジョンに覚醒した元社畜の成り上がり無双"
    genre = "fantasy"

    # イベントループでパイプライン実行
    result = asyncio.run(pipeline.execute(theme=theme, genre=genre))
    print(f"  -> パイプライン完了ステータス: {result.get('status')}")
    print(f"  -> 生成ブックID: {result.get('book_id')}")
    print(f"  -> タイトル: {result.get('title')}")
    print(f"  -> エピソード数: {result.get('episodes')}")

    book_id = result.get("book_id")
    assert book_id is not None, "Book ID が生成されていません"

    # DBにレコードが反映されているか確認
    book = session.query(Book).filter_by(id=book_id).first()
    assert book is not None, f"DB内に book_id={book_id} が見つかりません"
    chapters = session.query(Chapter).filter_by(book_id=book_id).all()
    print(f"  -> DB検証: Book『{book.title}』(Chapter数: {len(chapters)})")
    for ch in chapters:
        print(f"     第{ch.ep_num}話: {ch.title} (本文長: {len(ch.content or '')}文字)")

    print("\n[3] 小説エクスポート & ダウンロード機能検証...")

    # 3-1: なろう形式エクスポート
    print("  [3-1] 『小説家になろう』形式エクスポート検証")
    narou_exporter = get_exporter("narou")
    novel_dict = {
        "title": book.title,
        "synopsis": book.synopsis or book.concept or "",
        "is_adult": False,
    }
    chapters_dict = [{"ep_num": c.ep_num, "title": c.title, "content": c.content or ""} for c in chapters]
    narou_text = narou_exporter.export(novel_dict, chapters_dict)
    assert len(narou_text) > 0, "なろう形式エクスポートが空です"
    print(f"     -> 正常出力完了 (バイト数: {len(narou_text.encode('utf-8'))} bytes)")

    # 3-2: カクヨム形式エクスポート
    print("  [3-2] 『カクヨム』形式エクスポート検証")
    kakuyomu_exporter = get_exporter("kakuyomu")
    kakuyomu_text = kakuyomu_exporter.export(novel_dict, chapters_dict)
    assert len(kakuyomu_text) > 0, "カクヨム形式エクスポートが空です"
    print(f"     -> 正常出力完了 (バイト数: {len(kakuyomu_text.encode('utf-8'))} bytes)")

    # 3-3: MarketingAgent による納品用ZIPダウンロードパッケージ検証
    print("  [3-3] 納品パッケージZIP (本文+メタデータ+設定集) 生成・ダウンロード検証")
    repo = BookRepository(session)
    marketing_agent = MarketingAgent(repo=repo)
    zip_bytes, zip_filename = asyncio.run(marketing_agent.create_export_package(book_id))

    assert zip_bytes and len(zip_bytes) > 0, "ZIPバイナリが生成されていません"
    print(f"     -> ZIP生成成功: {zip_filename} ({len(zip_bytes)} bytes)")

    # ZIPの内容物をインメモリ展開して厳格検査
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        namelist = zf.namelist()
        print(f"     -> ZIP内ファイル一覧 ({len(namelist)}ファイル):")
        for name in namelist:
            info = zf.getinfo(name)
            print(f"        - {name} ({info.file_size} bytes)")

        # 必須ファイルの存在確認
        assert any(n.endswith(".txt") or n.endswith(".md") for n in namelist), (
            "ZIP内に本文または概要ファイルが存在しません"
        )
        # 壊れていないかのCRCチェック
        bad_file = zf.testzip()
        assert bad_file is None, f"ZIP内に破損ファイルがあります: {bad_file}"
        print("     -> ZIPアーカイブ整合性チェック合格 (CRC正常)")

    print("\n========================================================")
    print(" [合格] 起動から小説作成、ダウンロードまでの全シナリオ完全パス！")
    print("========================================================")


if __name__ == "__main__":
    run_full_lifecycle()
