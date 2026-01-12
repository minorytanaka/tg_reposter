import configparser
import logging

logger = logging.getLogger(__name__)


class Settings:
    def __init__(self, config_path: str = "config.ini"):
        self._config = configparser.ConfigParser()
        if not self._config.read(config_path, encoding="utf-8"):
            raise FileNotFoundError(f"Не удалось прочитать конфигурацию: {config_path}")

    # ── Telegram ────────────────────────────────────────────────────────────────
    @property
    def api_id(self) -> int:
        return int(self._config["Telegram"]["api_id"])

    @property
    def api_hash(self) -> str:
        return self._config["Telegram"]["api_hash"]

    # ── RepostSettings ──────────────────────────────────────────────────────────
    @property
    def period_hours(self) -> int:
        return int(self._config.get("RepostSettings", "period", fallback="24"))

    @property
    def min_views(self) -> int:
        return int(self._config.get("RepostSettings", "min_views", fallback="0"))

    @property
    def min_reactions(self) -> int:
        return int(self._config.get("RepostSettings", "min_reactions", fallback="0"))

    @property
    def min_comments(self) -> int:
        return int(self._config.get("RepostSettings", "min_comments", fallback="0"))

    @property
    def min_delay(self) -> float:
        """Минимальная задержка между постами в секундах"""
        return float(self._config.get("RepostSettings", "min_delay", fallback="5.0"))

    @property
    def max_delay(self) -> float:
        """Максимальная задержка между постами в секундах"""
        return float(self._config.get("RepostSettings", "max_delay", fallback="15.0"))

    @property
    def source_channels(self) -> list[int]:
        raw = self._config.get("RepostSettings", "source_channels", fallback="")
        return [int(ch.strip()) for ch in raw.split(",") if ch.strip()]

    @property
    def target_channel(self) -> int:
        try:
            return str(self._config["RepostSettings"]["target_channel"])
        except:
            return int(self._config["RepostSettings"]["target_channel"])

    # ── Paraphrase ──────────────────────────────────────────────────────────────
    @property
    def paraphrase_api_key(self) -> str:
        """API-ключ от io.net IO Intelligence"""
        return self._config["Paraphrase"]["api_key"].strip()

    @property
    def paraphrase_models(self) -> list[str]:
        """Список моделей через запятую (возвращает список строк)"""
        raw = self._config.get("Paraphrase", "models", fallback="")
        return [m.strip() for m in raw.split(",") if m.strip()]

    @property
    def paraphrase_temperature(self) -> float:
        """Температура (0.0–2.0), оптимально 0.3–0.7 для минимальных изменений"""
        return float(self._config.get("Paraphrase", "temp", fallback="0.65"))

    @property
    def paraphrase_top_p(self) -> float:
        """Nucleus sampling (обычно 0.7–0.95)"""
        return float(self._config.get("Paraphrase", "top_p", fallback="0.9"))

    @property
    def paraphrase_max_tokens(self) -> int:
        """Максимальное количество токенов в ответе модели"""
        return int(self._config.get("Paraphrase", "max_tokens", fallback="512"))

    @property
    def paraphrase_frequency_penalty(self) -> float:
        """Штраф за повторение слов (0.0–1.0, обычно 0.0–0.3)"""
        return float(
            self._config.get("Paraphrase", "frequency_penalty", fallback="0.2")
        )

    @property
    def paraphrase_presence_penalty(self) -> float:
        """Штраф за новые темы/слова (0.0–1.0, обычно 0.0–0.3)"""
        return float(self._config.get("Paraphrase", "presence_penalty", fallback="0.1"))

    @property
    def paraphrase_system_prompt(self) -> str:
        """Системный промпт (инструкция модели)"""
        default = (
            "Ты эксперт по перефразированию текстов. Делай только небольшие изменения: "
            "меняй синонимы, переставляй слова, немного меняй структуру предложений, "
            "но сохраняй точный смысл, стиль и длину оригинала. "
            "Не добавляй и не убирай информацию. "
            "Выдай только 1 вариант. Выдай только результат без лишних комментариев."
        )
        return self._config.get(
            "Paraphrase", "message_for_system_role", fallback=default
        ).strip()

    @property
    def paraphrase_user_prompt_template(self) -> str:
        """Шаблон пользовательского сообщения"""
        default = "Перефразируй этот текст с минимальными изменениями:"
        return self._config.get(
            "Paraphrase", "message_for_user_role", fallback=default
        ).strip()

    def validate(self):
        required = [
            self.api_id,
            self.api_hash,
            self.source_channels,
            self.target_channel,
            self.paraphrase_api_key,
            self.paraphrase_models,
        ]

        if not all(required):
            raise ValueError(
                "Не все обязательные параметры указаны: "
                "api_id, api_hash, source_channels, target_channel, "
                "paraphrase_api_key, paraphrase_models"
            )

        if not self.paraphrase_models:
            raise ValueError("Список paraphrase_models не может быть пустым")

        if self.min_delay < 0 or self.max_delay < 0:
            raise ValueError("Задержки не могут быть отрицательными")

        if self.min_delay > self.max_delay:
            raise ValueError("min_delay не может быть больше max_delay")

        logger.info("[green]✅ Конфигурация валидна[/green]")
        return self
