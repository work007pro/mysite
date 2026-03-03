"""
note.com API クライアント
note.comの内部APIを利用して記事の投稿・管理を行う
"""
import json
import re
import time

import requests


class NoteClient:
    BASE_URL = "https://note.com"
    API_URL = "https://note.com/api"

    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ja,en;q=0.9",
            "Origin": "https://note.com",
            "Referer": "https://note.com/login",
        })
        self.user_id = None
        self.is_logged_in = False

    def login(self):
        """note.comにログインする"""
        try:
            # CSRFトークン取得のためにログインページにアクセス
            resp = self.session.get(f"{self.BASE_URL}/login", timeout=15)

            # ログインAPIを呼び出し
            login_data = {
                "login": self.email,
                "password": self.password,
            }
            resp = self.session.post(
                f"{self.API_URL}/v1/sessions/sign_in",
                json=login_data,
                timeout=15,
            )

            if resp.status_code == 200:
                data = resp.json()
                self.user_id = data.get("data", {}).get("user_id")
                self.is_logged_in = True
                return True, "ログイン成功"
            elif resp.status_code == 401:
                return False, "メールアドレスまたはパスワードが正しくありません"
            else:
                return False, f"ログインエラー (HTTP {resp.status_code})"

        except requests.exceptions.Timeout:
            return False, "接続がタイムアウトしました"
        except requests.exceptions.ConnectionError:
            return False, "note.comに接続できません"
        except Exception as e:
            return False, f"予期しないエラー: {str(e)}"

    def upload_image(self, image_path, image_type="article"):
        """画像をnote.comにアップロードする

        Args:
            image_path: アップロードする画像ファイルのパス
            image_type: 'cover' (表紙) or 'article' (記事内)

        Returns:
            (success, image_url_or_error_message)
        """
        if not self.is_logged_in:
            return False, "ログインしていません"

        try:
            with open(image_path, "rb") as f:
                file_name = image_path.rsplit("/", 1)[-1] if "/" in image_path else image_path
                files = {"file": (file_name, f, "image/png")}
                data = {"kind": image_type}

                resp = self.session.post(
                    f"{self.API_URL}/v1/image_upload",
                    files=files,
                    data=data,
                    timeout=30,
                )

            if resp.status_code == 200:
                result = resp.json()
                image_url = result.get("data", {}).get("url", "")
                if image_url:
                    return True, image_url
                return False, "画像URLの取得に失敗しました"
            else:
                return False, f"画像アップロードエラー (HTTP {resp.status_code})"

        except FileNotFoundError:
            return False, f"画像ファイルが見つかりません: {image_path}"
        except Exception as e:
            return False, f"画像アップロードエラー: {str(e)}"

    def post_article(self, title, body, tags=None, is_paid=False, price=0,
                     cover_image_path=None, article_images=None):
        """記事をnote.comに投稿する

        Args:
            title: 記事タイトル
            body: 記事本文
            tags: タグリスト
            is_paid: 有料記事かどうか
            price: 有料記事の価格（100〜50000円）
            cover_image_path: 表紙画像のファイルパス
            article_images: 記事内画像のファイルパスリスト

        Returns:
            (success, url_or_error_message)
        """
        if not self.is_logged_in:
            return False, "ログインしていません"

        try:
            # 表紙画像アップロード
            cover_image_url = None
            if cover_image_path:
                ok, result = self.upload_image(cover_image_path, image_type="cover")
                if ok:
                    cover_image_url = result

            # 記事内画像のアップロードと本文内のパス置換
            if article_images:
                for img_path in article_images:
                    ok, result = self.upload_image(img_path, image_type="article")
                    if ok:
                        # 本文内の画像パスをアップロード先URLに置換
                        body = body.replace(img_path, result)

            # 記事データ構築
            article_data = {
                "name": title,
                "body": self._format_body(body),
                "status": "published",
                "type": "TextNote",
            }

            if tags:
                article_data["hashtags"] = [{"hashtag": {"name": tag}} for tag in tags]

            if cover_image_url:
                article_data["eyecatch"] = cover_image_url

            if is_paid:
                price = max(100, min(50000, price))
                article_data["price"] = price
                article_data["is_limited_free"] = True

            # 記事作成
            resp = self.session.post(
                f"{self.API_URL}/v3/notes",
                json=article_data,
                timeout=30,
            )

            if resp.status_code in (200, 201):
                data = resp.json()
                note_key = data.get("data", {}).get("key", "")
                note_url = f"{self.BASE_URL}/n/{note_key}" if note_key else ""
                return True, note_url
            else:
                return False, f"投稿エラー (HTTP {resp.status_code})"

        except Exception as e:
            return False, f"投稿エラー: {str(e)}"

    def _format_body(self, body):
        """本文をnote.com用のJSON形式に変換する

        改行を適切に保持し、画像・見出し・区切り線を正しく挿入する。
        - 空行は改行ブロックとして保持
        - 連続する空行は1つの空行ブロックにまとめる
        - Markdown記法の画像 ![alt](url) を画像ブロックに変換
        - # / ## を見出しブロックに変換
        - --- を区切り線に変換
        """
        lines = body.split("\n")
        blocks = []
        prev_empty = False

        for line in lines:
            stripped = line.rstrip()

            # 空行 → 改行ブロック（連続する空行はまとめる）
            if not stripped:
                if not prev_empty:
                    blocks.append({"type": "p", "text": ""})
                prev_empty = True
                continue

            prev_empty = False

            # 見出し h1
            if stripped.startswith("# "):
                blocks.append({"type": "heading", "text": stripped[2:]})

            # 見出し h2
            elif stripped.startswith("## "):
                blocks.append({"type": "heading", "text": stripped[3:], "level": 2})

            # 見出し h3
            elif stripped.startswith("### "):
                blocks.append({"type": "heading", "text": stripped[4:], "level": 3})

            # 画像記法: ![alt](url)
            elif re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped):
                match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
                blocks.append({
                    "type": "image",
                    "src": match.group(2),
                    "alt": match.group(1),
                })

            # 画像URL直書き（https://...で終わる画像拡張子）
            elif re.match(r"^https?://\S+\.(png|jpg|jpeg|gif|webp)(\?\S*)?$", stripped, re.IGNORECASE):
                blocks.append({"type": "image", "src": stripped, "alt": ""})

            # 区切り線
            elif stripped in ("---", "***", "___", "===paid==="):
                blocks.append({"type": "separator"})

            # 引用
            elif stripped.startswith("> "):
                blocks.append({"type": "quote", "text": stripped[2:]})

            # 箇条書き
            elif stripped.startswith("- ") or stripped.startswith("* "):
                blocks.append({"type": "list", "text": stripped[2:]})

            # 番号付きリスト
            elif re.match(r"^\d+\.\s", stripped):
                text = re.sub(r"^\d+\.\s", "", stripped)
                blocks.append({"type": "ordered_list", "text": text})

            # 太字を含む段落 **text**
            elif "**" in stripped:
                text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", stripped)
                blocks.append({"type": "p", "text": text})

            # 通常の段落
            else:
                blocks.append({"type": "p", "text": stripped})

        return json.dumps(blocks, ensure_ascii=False)

    def get_my_notes(self, page=1, per_page=10):
        """自分の投稿一覧を取得する"""
        if not self.is_logged_in:
            return False, "ログインしていません"

        try:
            resp = self.session.get(
                f"{self.API_URL}/v1/notes/mine",
                params={"page": page, "per": per_page},
                timeout=15,
            )
            if resp.status_code == 200:
                return True, resp.json()
            return False, f"取得エラー (HTTP {resp.status_code})"
        except Exception as e:
            return False, str(e)
