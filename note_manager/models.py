import base64
import os
from datetime import datetime

from cryptography.fernet import Fernet
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# 暗号化キー（環境変数から取得、なければ生成して固定）
_key_file = os.path.join(os.path.dirname(__file__), ".encryption_key")


def _get_encryption_key():
    if os.environ.get("ENCRYPTION_KEY"):
        return os.environ["ENCRYPTION_KEY"].encode()
    if os.path.exists(_key_file):
        with open(_key_file, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(_key_file, "wb") as f:
        f.write(key)
    return key


_fernet = Fernet(_get_encryption_key())


class Account(db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    encrypted_password = db.Column(db.LargeBinary, nullable=False)
    note_user_id = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=False)
    # アカウントごとの設定
    theme = db.Column(db.String(200), default="")          # 記事のテーマ/ジャンル
    default_tags = db.Column(db.String(500), default="")   # デフォルトタグ
    min_chars = db.Column(db.Integer, default=1000)         # 最小文字数
    max_chars = db.Column(db.Integer, default=5000)         # 最大文字数
    default_price = db.Column(db.Integer, default=0)        # デフォルト価格
    min_price = db.Column(db.Integer, default=100)           # 最小価格
    max_price = db.Column(db.Integer, default=1000)          # 最大価格
    auto_cover_image = db.Column(db.Boolean, default=True)  # 表紙画像を自動生成
    post_frequency = db.Column(db.String(50), default="daily")  # 投稿頻度: daily, weekly, custom
    tone = db.Column(db.String(100), default="")            # 文章のトーン/スタイル
    target_audience = db.Column(db.String(200), default="") # ターゲット読者
    info_sources = db.Column(db.String(500), default="google,youtube")  # 情報ソース（カンマ区切り）
    # 利用可能なソース: google, youtube, news, wikipedia, twitter, reddit, academic
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    articles = db.relationship("Article", backref="account", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.encrypted_password = _fernet.encrypt(password.encode())

    def get_password(self):
        return _fernet.decrypt(self.encrypted_password).decode()

    @property
    def article_count(self):
        return len(self.articles)

    @property
    def published_count(self):
        return sum(1 for a in self.articles if a.status == "published")


class Article(db.Model):
    __tablename__ = "articles"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    title = db.Column(db.String(500), nullable=False, default="")
    body = db.Column(db.Text, default="")
    tags = db.Column(db.String(500), default="")
    is_paid = db.Column(db.Boolean, default=False)
    price = db.Column(db.Integer, default=0)
    free_part = db.Column(db.Text, default="")
    cover_image = db.Column(db.String(500), default="")    # 表紙画像パス
    article_images = db.Column(db.Text, default="")        # 記事内画像パス（JSON配列）
    status = db.Column(db.String(20), default="draft")  # draft, scheduled, publishing, published, error
    scheduled_at = db.Column(db.DateTime)
    published_at = db.Column(db.DateTime)
    note_url = db.Column(db.String(500))
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def status_label(self):
        labels = {
            "draft": "下書き",
            "scheduled": "予約済み",
            "publishing": "投稿中",
            "published": "投稿完了",
            "error": "エラー",
        }
        return labels.get(self.status, self.status)

    @property
    def status_color(self):
        colors = {
            "draft": "#6b7280",
            "scheduled": "#f59e0b",
            "publishing": "#3b82f6",
            "published": "#10b981",
            "error": "#ef4444",
        }
        return colors.get(self.status, "#6b7280")

    @property
    def tag_list(self):
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]
