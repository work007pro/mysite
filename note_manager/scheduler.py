"""
自動投稿スケジューラー
APSchedulerを使用して予約投稿を自動実行する
"""
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler


def init_scheduler(app):
    """スケジューラーを初期化して開始する"""
    scheduler = BackgroundScheduler()

    def check_scheduled_posts():
        """予約投稿をチェックして実行する"""
        with app.app_context():
            from models import db, Article

            now = datetime.utcnow()
            scheduled = Article.query.filter(
                Article.status == "scheduled",
                Article.scheduled_at <= now,
            ).all()

            publish_func = app.config.get("PUBLISH_FUNC")
            if not publish_func:
                return

            for article in scheduled:
                article.status = "publishing"
                db.session.commit()
                try:
                    publish_func(article)
                except Exception as e:
                    article.status = "error"
                    article.error_message = f"スケジュール実行エラー: {str(e)}"
                    db.session.commit()

    # 60秒ごとに予約投稿をチェック
    scheduler.add_job(check_scheduled_posts, "interval", seconds=60, id="check_scheduled")
    scheduler.start()

    return scheduler
