import json
import logging
import os
from datetime import datetime
from typing import Set

logger = logging.getLogger(__name__)


class HistoryManager:
    def __init__(self, history_file: str = "sent_posts.json"):
        self.history_file = history_file
        self.sent_posts: Set[str] = set()
        self._load_history()

    def _load_history(self):
        """Загружаем историю отправленных постов из файла"""

        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.sent_posts = set(data.get("sent_posts", []))

                logger.info(
                    f"[green]📚 Загружена история: {len(self.sent_posts)} отправленных постов[/green]"
                )
            else:
                logger.info("[blue]📝 Файл истории не найден, создаю новый...[/blue]")
                self._save_history()
        except Exception as e:
            logger.error(f"[red]❌ Ошибка загрузки истории: {e}[/red]")
            self.sent_posts = set()

    def _save_history(self):
        """Сохраняем историю в файл"""

        try:
            data = {
                "last_updated": datetime.now().isoformat(),
                "sent_posts": list(self.sent_posts),
            }

            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(
                f"[green]💾 История сохранена ({len(self.sent_posts)} постов)[/green]"
            )
        except Exception as e:
            logger.error(f"[red]❌ Ошибка сохранения истории: {e}[/red]")

    def is_post_sent(self, post_signature: str) -> bool:
        """Проверяем, был ли пост уже отправлен"""

        return post_signature in self.sent_posts

    def mark_post_sent(self, post_signature: str):
        """Отмечаем пост как отправленный"""

        self.sent_posts.add(post_signature)
        self._save_history()

    def clear_history(self):
        """Очищаем историю"""

        self.sent_posts.clear()
        self._save_history()
        logger.info("[yellow]🧹 История очищена[/yellow]")

    def get_total_sent(self) -> int:
        """Получаем общее количество отправленных постов"""
        return len(self.sent_posts)
