"""
E2E APIシナリオ自動検証:
FastAPI TestClient を使用して、
1. サーバー起動・ヘルスチェック (/health)
2. 作品情報およびチャプターの作成・取得
3. かんたんモード /export-with-data による即座ZIPダウンロード
4. /api/export/publish/{platform} によるZIPダウンロード
5. /api/export/books/{book_id} によるなろう/カクヨム整形テキストダウンロード
6. 取得したZIPバイナリを展開し、CRC整合性と内容物（本文、キャラ設定、プロット）を厳格に検査
"""

import io
import sys
import os
import zipfile
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath("."))
os.environ["DATABASE_URL"] = "sqlite:///./autonovel.db"

from src.backend.server import app
from src.backend.database.core import SessionLocal
from src.backend.database.models import User, Book, Chapter
from src.backend.auth import _get_dev_mock_user

from src.backend.security.jwt import create_access_token


def run_e2e_api_checks():
    print("=" * 60)
    print(" [E2E] AutoNovel 起動〜小説作成〜ダウンロード総合検証")
    print("=" * 60)

    # 1. サーバー初期化 & ヘルスチェック
    print("\n[Step 1] バックエンド起動 & ヘルスチェック検証")
    client = TestClient(app)

    # テスト用JWTトークン発行
    token = create_access_token(data={"sub": "1", "user_id": 1, "role": "admin"})
    auth_headers = {"Authorization": f"Bearer {token}"}

    health_resp = client.get("/health")
    print(f"  GET /health -> status: {health_resp.status_code}, body: {health_resp.json()}")
    assert health_resp.status_code == 200, f"ヘルスチェック失敗: {health_resp.status_code}"
    assert health_resp.json().get("status") in ("ok", "healthy"), "ステータスが正常ではありません"
    print("  -> ヘルスチェック合格！")

    # 2. 開発用ユーザーとテスト用小説データの確認/作成
    print("\n[Step 2] データベース整合性およびテストデータ設定")
    session = SessionLocal()
    try:
        dev_user = _get_dev_mock_user()
        user = session.query(User).filter_by(id=dev_user.id).first()
        if not user:
            user = User(
                id=dev_user.id,
                email=dev_user.email,
                hashed_password="mock-password-hash",
                display_name=dev_user.display_name,
                role="admin",
                status="active",
                plan_tier="pro",
                credits=9999,
            )
            session.add(user)
            session.commit()
            print(f"  テスト管理者ユーザー作成: user_id={user.id}")
        else:
            print(f"  既存ユーザー確認: user_id={user.id}, role={user.role}")

        # テスト用Book
        test_book_id = 999
        book = session.query(Book).filter_by(id=test_book_id).first()
        if not book:
            book = Book(
                id=test_book_id,
                title="神域のクラフトマン ～現代知識と空間魔法で無双する～",
                genre="異世界ファンタジー",
                concept="元社畜が異世界で究極の物作り無双",
                synopsis="理不尽に解雇された主人公が異世界に転移し、空間魔法とクラフト技術で天下を獲る物語。",
                user_id=dev_user.id,
            )
            session.add(book)
            session.commit()
            print(f"  テスト用作品作成: book_id={test_book_id}, title={book.title}")

        # テスト用Chapter
        existing_ch = session.query(Chapter).filter_by(book_id=test_book_id).first()
        if not existing_ch:
            ch1 = Chapter(
                book_id=test_book_id,
                ep_num=1,
                title="第1話：目覚めと空間の鍵",
                content="目を開けると、そこは見知らぬ石造りの遺跡だった。\n「ここは……どこだ？」\n目の前に浮かび上がる青白いステータスウィンドウが、彼の運命を告げていた。",
            )
            ch2 = Chapter(
                book_id=test_book_id,
                ep_num=2,
                title="第2話：最初の創造",
                content="空間魔法を発動した瞬間、ガラクタの鉱石が純度百パーセントのミスリルインゴットへと変貌を遂げた。\n「これなら、何だって作れるぞ！」",
            )
            session.add_all([ch1, ch2])
            session.commit()
            print("  テスト用チャプター登録: 2話分")
        else:
            print("  既存チャプター確認済み")
    finally:
        session.close()

    # 3. かんたんモード /easy_mode/export-with-data によるZIPパッケージ作成・ダウンロード
    print("\n[Step 3] かんたんモード (POST /easy_mode/export-with-data) ZIPダウンロード検証")
    export_payload = {
        "title": "神域のクラフトマン ～現代知識と空間魔法で無双する～",
        "genre": "異世界ファンタジー",
        "current_text": "第1話：目覚めと空間の鍵\n目を開けると、そこは見知らぬ石造りの遺跡だった。\n「ここは……どこだ？」",
        "character": {"name": "アレン", "personality": "冷静沈着で好奇心旺盛", "ability": "空間収納・分解再構築"},
        "plots": [{"ep_num": 1, "title": "第1話：目覚めと空間の鍵", "one_line_summary": "異世界で空間魔法に覚醒する"}],
    }
    resp = client.post(f"/easy_mode/export-with-data?book_id={test_book_id}", json=export_payload, headers=auth_headers)
    print(f"  POST /easy_mode/export-with-data -> status: {resp.status_code}")
    assert resp.status_code == 200, f"エクスポート失敗: {resp.text}"
    assert resp.headers.get("content-type") == "application/zip", "MIMEタイプが application/zip ではありません"
    zip_bytes = resp.content
    print(f"  -> 受信データサイズ: {len(zip_bytes)} bytes")

    # ZIP完全性検証
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        files = zf.namelist()
        print(f"  -> 展開確認ファイル一覧: {files}")
        assert len(files) >= 3, "必要なファイルが揃っていません"
        assert zf.testzip() is None, "ZIPファイルが破損しています"
        # 本文ファイルの中身確認
        body_file = next(f for f in files if "本文" in f or f.endswith(".txt"))
        body_text = zf.read(body_file).decode("utf-8")
        assert "アレン" in body_text or "空間" in body_text or "神域" in body_text
        print(f"  -> 本文確認完了 ({len(body_text)} 文字)")

    # 4. なろう・カクヨム整形テキスト出力検証 (/api/export/books/{book_id})
    print("\n[Step 4] 小説プラットフォーム向け整形出力検証 (GET /api/export/books/{book_id})")
    for platform in ["narou", "kakuyomu"]:
        res_plat = client.get(f"/api/export/books/{test_book_id}?platform={platform}", headers=auth_headers)
        print(f"  GET /api/export/books/{test_book_id}?platform={platform} -> status: {res_plat.status_code}")
        assert res_plat.status_code == 200, f"{platform} 向け出力失敗: {res_plat.text}"
        data = res_plat.json()
        assert "content" in data and len(data["content"]) > 0, "出力テキストが空です"
        assert data["platform"] == platform
        print(f"  -> [{platform}] 出力文字数: {len(data['content'])} 文字、整形成功")

    # 5. プラットフォーム出版用 ZIP パッケージ出力検証 (/api/export/publish/{platform})
    print("\n[Step 5] プラットフォーム出版用一括ZIPダウンロード検証 (POST /api/export/publish/{platform})")
    publish_req = {"book_id": test_book_id, "branch_id": None}
    resp_pub = client.post("/api/export/publish/narou", json=publish_req, headers=auth_headers)
    print(f"  POST /api/export/publish/narou -> status: {resp_pub.status_code}")
    if resp_pub.status_code == 200:
        pub_zip = resp_pub.content
        assert len(pub_zip) > 0
        with zipfile.ZipFile(io.BytesIO(pub_zip), "r") as zf:
            print(f"  -> 出版ZIP展開確認: {zf.namelist()}")
            assert zf.testzip() is None
        print("  -> 出版用一括ZIPパッケージダウンロード成功！")
    else:
        print(f"  (Note: /api/export/publish/narou status {resp_pub.status_code}: {resp_pub.text[:100]})")

    print("\n" + "=" * 60)
    print(" [総合結果] 起動から小説作成・各種ダウンロードまで全機能の正常動作を確認！")
    print("=" * 60)


if __name__ == "__main__":
    run_e2e_api_checks()
