import os
import json
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.utils import secure_filename

from models import db, Account, Article
from note_api import NoteClient
from scheduler import init_scheduler

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", os.urandom(32).hex())
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///note_manager.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

db.init_app(app)
scheduler = None

with app.app_context():
    db.create_all()
    scheduler = init_scheduler(app)


# ─── Dashboard ───────────────────────────────────────────────────────
@app.route("/")
def dashboard():
    accounts = Account.query.all()
    articles = Article.query.order_by(Article.created_at.desc()).limit(20).all()
    stats = {
        "total_accounts": Account.query.count(),
        "total_articles": Article.query.count(),
        "published": Article.query.filter_by(status="published").count(),
        "scheduled": Article.query.filter_by(status="scheduled").count(),
        "draft": Article.query.filter_by(status="draft").count(),
    }
    return render_template("dashboard.html", accounts=accounts, articles=articles, stats=stats)


# ─── Account Management ─────────────────────────────────────────────
@app.route("/accounts")
def accounts():
    accounts = Account.query.all()
    return render_template("accounts.html", accounts=accounts)


@app.route("/accounts/add", methods=["POST"])
def add_account():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not all([name, email, password]):
        flash("すべてのフィールドを入力してください。", "error")
        return redirect(url_for("accounts"))

    if Account.query.filter_by(email=email).first():
        flash("このメールアドレスは既に登録されています。", "error")
        return redirect(url_for("accounts"))

    account = Account(name=name, email=email)
    account.set_password(password)

    # note.com へのログイン検証
    client = NoteClient(email, password)
    login_ok, msg = client.login()
    if login_ok:
        account.is_active = True
        account.note_user_id = client.user_id
        flash(f"アカウント「{name}」を追加し、note.comへのログインに成功しました。", "success")
    else:
        account.is_active = False
        flash(f"アカウント「{name}」を追加しましたが、ログイン検証に失敗しました: {msg}", "warning")

    db.session.add(account)
    db.session.commit()
    return redirect(url_for("accounts"))


@app.route("/accounts/<int:account_id>/delete", methods=["POST"])
def delete_account(account_id):
    account = Account.query.get_or_404(account_id)
    db.session.delete(account)
    db.session.commit()
    flash(f"アカウント「{account.name}」を削除しました。", "success")
    return redirect(url_for("accounts"))


@app.route("/accounts/<int:account_id>/verify", methods=["POST"])
def verify_account(account_id):
    account = Account.query.get_or_404(account_id)
    client = NoteClient(account.email, account.get_password())
    login_ok, msg = client.login()
    account.is_active = login_ok
    db.session.commit()

    if login_ok:
        flash(f"アカウント「{account.name}」の接続を確認しました。", "success")
    else:
        flash(f"接続に失敗: {msg}", "error")
    return redirect(url_for("accounts"))


@app.route("/accounts/<int:account_id>/settings")
def account_settings(account_id):
    account = Account.query.get_or_404(account_id)
    return render_template("account_settings.html", account=account)


@app.route("/accounts/<int:account_id>/settings/save", methods=["POST"])
def save_account_settings(account_id):
    account = Account.query.get_or_404(account_id)
    account.theme = request.form.get("theme", "").strip()
    account.default_tags = request.form.get("default_tags", "").strip()
    account.min_chars = int(request.form.get("min_chars", 1000))
    account.max_chars = int(request.form.get("max_chars", 5000))
    account.default_price = int(request.form.get("default_price", 0))
    account.min_price = int(request.form.get("min_price", 100))
    account.max_price = int(request.form.get("max_price", 1000))
    account.auto_cover_image = request.form.get("auto_cover_image") == "on"
    account.post_frequency = request.form.get("post_frequency", "daily")
    account.tone = request.form.get("tone", "").strip()
    account.target_audience = request.form.get("target_audience", "").strip()
    account.info_sources = request.form.get("info_sources", "google,youtube")
    db.session.commit()
    flash(f"アカウント「{account.name}」の設定を保存しました。", "success")
    return redirect(url_for("account_settings", account_id=account_id))


# ─── Image Upload ────────────────────────────────────────────────────
@app.route("/upload/image", methods=["POST"])
def upload_image():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "ファイルが選択されていません"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "ファイルが選択されていません"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}")
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)
        return jsonify({
            "success": True,
            "url": url_for("static", filename=f"uploads/{filename}"),
            "path": filepath,
        })

    return jsonify({"success": False, "error": "許可されていないファイル形式です"}), 400


# ─── Article Management ──────────────────────────────────────────────
@app.route("/articles")
def articles():
    status_filter = request.args.get("status", "all")
    account_filter = request.args.get("account_id", "all")

    query = Article.query
    if status_filter != "all":
        query = query.filter_by(status=status_filter)
    if account_filter != "all":
        query = query.filter_by(account_id=int(account_filter))

    articles = query.order_by(Article.created_at.desc()).all()
    accounts = Account.query.all()
    return render_template(
        "articles.html",
        articles=articles,
        accounts=accounts,
        status_filter=status_filter,
        account_filter=account_filter,
    )


@app.route("/articles/new")
def new_article():
    accounts = Account.query.filter_by(is_active=True).all()
    return render_template("editor.html", article=None, accounts=accounts)


@app.route("/articles/<int:article_id>/edit")
def edit_article(article_id):
    article = Article.query.get_or_404(article_id)
    accounts = Account.query.filter_by(is_active=True).all()
    return render_template("editor.html", article=article, accounts=accounts)


@app.route("/articles/save", methods=["POST"])
def save_article():
    article_id = request.form.get("article_id")
    if article_id:
        article = Article.query.get_or_404(int(article_id))
    else:
        article = Article()

    article.account_id = int(request.form["account_id"])
    article.title = request.form.get("title", "").strip()
    article.body = request.form.get("body", "")
    article.tags = request.form.get("tags", "")
    article.is_paid = request.form.get("is_paid") == "on"
    price_str = request.form.get("price", "0")
    article.price = int(price_str) if price_str.isdigit() else 0
    article.free_part = request.form.get("free_part", "")

    # 画像処理
    if "cover_image" in request.files:
        file = request.files["cover_image"]
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(f"cover_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}")
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)
            article.cover_image = filepath

    article_images_list = []
    if "article_images" in request.files:
        for file in request.files.getlist("article_images"):
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"img_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}")
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(filepath)
                article_images_list.append(filepath)
    if article_images_list:
        article.article_images = json.dumps(article_images_list)

    action = request.form.get("action", "draft")

    if action == "draft":
        article.status = "draft"
        db.session.add(article)
        db.session.commit()
        flash("下書きを保存しました。", "success")

    elif action == "schedule":
        scheduled_str = request.form.get("scheduled_at", "")
        if not scheduled_str:
            flash("予約投稿日時を指定してください。", "error")
            return redirect(url_for("edit_article", article_id=article.id) if article.id else url_for("new_article"))
        article.scheduled_at = datetime.fromisoformat(scheduled_str)
        article.status = "scheduled"
        db.session.add(article)
        db.session.commit()
        flash(f"投稿を {article.scheduled_at.strftime('%Y-%m-%d %H:%M')} に予約しました。", "success")

    elif action == "publish":
        article.status = "publishing"
        db.session.add(article)
        db.session.commit()
        # 即時投稿
        success, msg = publish_article(article)
        if success:
            flash("記事を投稿しました！", "success")
        else:
            flash(f"投稿に失敗しました: {msg}", "error")

    return redirect(url_for("articles"))


@app.route("/articles/<int:article_id>/delete", methods=["POST"])
def delete_article(article_id):
    article = Article.query.get_or_404(article_id)
    db.session.delete(article)
    db.session.commit()
    flash("記事を削除しました。", "success")
    return redirect(url_for("articles"))


# ─── Publishing Logic ────────────────────────────────────────────────
def publish_article(article):
    """記事をnote.comに投稿する"""
    account = Account.query.get(article.account_id)
    if not account:
        article.status = "error"
        article.error_message = "アカウントが見つかりません"
        db.session.commit()
        return False, article.error_message

    client = NoteClient(account.email, account.get_password())
    login_ok, login_msg = client.login()
    if not login_ok:
        article.status = "error"
        article.error_message = f"ログイン失敗: {login_msg}"
        db.session.commit()
        return False, article.error_message

    body = article.body
    if article.is_paid and article.free_part:
        body = article.free_part + "\n===paid===\n" + article.body

    tags = [t.strip() for t in article.tags.split(",") if t.strip()] if article.tags else []

    # 記事内画像
    article_imgs = []
    if article.article_images:
        try:
            article_imgs = json.loads(article.article_images)
        except (json.JSONDecodeError, TypeError):
            pass

    success, msg = client.post_article(
        title=article.title,
        body=body,
        tags=tags,
        is_paid=article.is_paid,
        price=article.price,
        cover_image_path=article.cover_image if article.cover_image else None,
        article_images=article_imgs if article_imgs else None,
    )

    if success:
        article.status = "published"
        article.published_at = datetime.utcnow()
        article.note_url = msg
        article.error_message = None
    else:
        article.status = "error"
        article.error_message = msg

    db.session.commit()
    return success, msg


# ─── API Endpoints ───────────────────────────────────────────────────
@app.route("/api/stats")
def api_stats():
    return jsonify({
        "total_accounts": Account.query.count(),
        "total_articles": Article.query.count(),
        "published": Article.query.filter_by(status="published").count(),
        "scheduled": Article.query.filter_by(status="scheduled").count(),
        "draft": Article.query.filter_by(status="draft").count(),
    })


@app.route("/api/articles/<int:article_id>/publish", methods=["POST"])
def api_publish_article(article_id):
    article = Article.query.get_or_404(article_id)
    success, msg = publish_article(article)
    return jsonify({"success": success, "message": msg})


# ─── Mobile Simple View ──────────────────────────────────────────────
@app.route("/mobile")
def mobile_view():
    accounts = Account.query.all()
    articles = Article.query.order_by(Article.created_at.desc()).all()
    stats = {
        "total_accounts": Account.query.count(),
        "total_articles": Article.query.count(),
        "published": Article.query.filter_by(status="published").count(),
        "scheduled": Article.query.filter_by(status="scheduled").count(),
        "draft": Article.query.filter_by(status="draft").count(),
    }
    return render_template("mobile.html", accounts=accounts, articles=articles, stats=stats)


# ─── Make publish_article accessible to scheduler ────────────────────
app.config["PUBLISH_FUNC"] = publish_article


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
