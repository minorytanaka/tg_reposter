import hashlib
import logging
import random
from datetime import datetime, timedelta

from openai import AsyncOpenAI
from pyrogram import Client
from pyrogram.types import (InputMediaDocument, InputMediaPhoto,
                            InputMediaVideo, Message)

from settings import Settings

logger = logging.getLogger(__name__)


def get_client(config):
    if not config.api_id or not config.api_hash:
        raise ValueError("API_ID и API_HASH должны быть в config.ini")
    return Client("reposter_account", api_id=config.api_id, api_hash=config.api_hash)


class TelegramHandler:
    def __init__(self):
        self._linked_chat_cache: dict[int, int | None] = {}
        self._openai_client = None

    def _get_openai_client(self, config: Settings) -> AsyncOpenAI:
        if self._openai_client is None:
            self._openai_client = AsyncOpenAI(
                api_key=config.paraphrase_api_key,
                base_url="https://api.intelligence.io.solutions/api/v1",
                timeout=120.0,
                max_retries=2,
            )
        return self._openai_client

    async def health_check(self, config: Settings):
        """Проверяем доступность API и моделей"""
        logger.info("[cyan]🔧 Выполняю health-check...[/cyan]")

        client = self._get_openai_client(config)

        # Проверяем API ключ
        try:
            logger.info("[blue]🔑 Проверяю API ключ...[/blue]")
            await client.models.list()
            logger.info("[green]✅ API ключ валиден[/green]")
        except Exception as e:
            logger.error(f"[red]❌ Ошибка API ключа: {e}[/red]")
            raise

    def generate_post_signature(self, message: Message) -> str:
        """Генерируем уникальную сигнатуру поста для проверки дубликатов"""
        # Используем комбинацию: channel_id + message_id + date + текст
        content = message.caption or message.text or ""
        signature_data = (
            f"{message.chat.id}_{message.id}_{message.date}_{content[:100]}"
        )

        # Хэшируем для компактности
        return hashlib.md5(signature_data.encode()).hexdigest()

    async def fetch_posts(
        self, client: Client, channel: int, config: Settings
    ) -> list[Message]:
        posts = []
        from_date = datetime.now() - timedelta(hours=config.period_hours)

        logger.info(f"[blue]📥 Получаю историю канала {channel}...[/blue]")

        try:
            async for message in client.get_chat_history(channel, limit=200):
                if message.date < from_date:
                    break

                if await self._filter_post(message, config, client):
                    posts.append(message)

            logger.info(f"[green]✅ Найдено {len(posts)} подходящих постов[/green]")
        except Exception as e:
            logger.error(f"[red]❌ Ошибка получения постов из {channel}: {e}[/red]")

        return posts

    async def _filter_post(self, message: Message, config, client: Client) -> bool:
        # Базовые фильтры
        if message.service is not None:
            return False

        if not (message.text or message.caption):
            return False

        # Фильтр по просмотрам
        views = message.views or 0
        if config.min_views > 0 and views < config.min_views:
            logger.debug(
                f"[yellow]👁️  Пропущен пост {message.id}: {views} просмотров < {config.min_views}[/yellow]"
            )
            return False

        # Фильтр по реакциям
        if config.min_reactions > 0:
            reactions = self.count_reactions(message)
            if reactions < config.min_reactions:
                logger.debug(
                    f"[yellow]👍 Пропущен пост {message.id}: {reactions} реакций < {config.min_reactions}[/yellow]"
                )
                return False

        # Фильтр по комментариям
        if config.min_comments > 0:
            comments = await self.count_comments(message, client)
            if comments < config.min_comments:
                logger.debug(
                    f"[yellow]💬 Пропущен пост {message.id}: {comments} комментариев < {config.min_comments}[/yellow]"
                )
                return False

        return True

    async def count_comments(self, message: Message, client: Client) -> int:
        channel_id = message.chat.id
        if channel_id not in self._linked_chat_cache:
            chat = await client.get_chat(channel_id)
            self._linked_chat_cache[channel_id] = (
                chat.linked_chat.id if chat.linked_chat else None
            )

        if self._linked_chat_cache[channel_id] is None:
            return 0

        try:
            return await client.get_discussion_replies_count(channel_id, message.id)
        except:
            return 0

    def count_reactions(self, message: Message) -> int:
        if not message.reactions or not message.reactions.reactions:
            return 0

        total = 0
        for reaction in message.reactions.reactions:
            total += reaction.count
        return total

    async def send_post(
        self, client: Client, target_channel: int, message: Message, config: Settings
    ) -> dict:
        """Отправляет пост с перефразированием, возвращает результат"""
        original_text = message.caption or message.text or ""

        # Пытаемся перефразировать
        paraphrase_result = await self._paraphrase_text(original_text, config)

        if paraphrase_result["success"]:
            new_text = paraphrase_result["text"]
            model_name = paraphrase_result["model_name"]
            tokens_used = paraphrase_result["tokens_used"]

            logger.info(
                f"[green]✨ Перефразировано успешно (модель: {model_name}, токенов: {tokens_used})[/green]"
            )
        else:
            # Отправляем оригинал с уведомлением
            error_msg = paraphrase_result.get("error", "Неизвестная ошибка")
            new_text = f"{original_text}\n\n⚠️ *Не удалось перефразировать*: {error_msg}"
            model_name = "original"
            tokens_used = 0

            logger.warning(f"[yellow]⚠️  Отправляю оригинал: {error_msg}[/yellow]")

        # Отправка медиа группы
        if message.media_group_id:
            await self._send_media_group(client, target_channel, message, new_text)
        else:
            await self._send_single_post(client, target_channel, message, new_text)

        return {
            "success": True,
            "model_name": model_name,
            "tokens_used": tokens_used,
            "paraphrase_success": paraphrase_result["success"],
        }

    async def _send_media_group(
        self, client: Client, target_channel: int, message: Message, new_text: str
    ):
        group = await message.get_media_group()
        media_group = []

        for msg in group:
            caption_for_this = new_text if msg.caption else None
            if msg.photo:
                media_group.append(
                    InputMediaPhoto(media=msg.photo.file_id, caption=caption_for_this)
                )
            elif msg.video:
                media_group.append(
                    InputMediaVideo(media=msg.video.file_id, caption=caption_for_this)
                )
            elif msg.document:
                media_group.append(
                    InputMediaDocument(
                        media=msg.document.file_id, caption=caption_for_this
                    )
                )

        await client.send_media_group(target_channel, media=media_group)
        logger.info(
            f"[green]📸 Отправлена медиа-группа из {len(group)} элементов[/green]"
        )

    async def _send_single_post(
        self, client: Client, target: int, message: Message, new_text: str
    ):
        if message.photo:
            await client.send_photo(
                target,
                photo=message.photo.file_id,
                caption=new_text,
            )
            logger.info("[green]🖼️  Отправлено фото[/green]")
        elif message.video:
            await client.send_video(
                target,
                video=message.video.file_id,
                caption=new_text,
            )
            logger.info("[green]🎬 Отправлено видео[/green]")
        elif message.document:
            await client.send_document(
                target,
                document=message.document.file_id,
                caption=new_text,
            )
            logger.info("[green]📄 Отправлен документ[/green]")
        elif message.animation:
            await client.send_animation(
                target,
                animation=message.animation.file_id,
                caption=new_text,
            )
            logger.info("[green]🎞️  Отправлена анимация[/green]")
        else:
            # Просто текст
            await client.send_message(
                target,
                text=new_text,
            )
            logger.info("[green]📝 Отправлен текстовый пост[/green]")

    async def _paraphrase_text(self, original_text: str, config: Settings) -> dict:
        """Перефразирует текст, возвращает словарь с результатом"""
        if not original_text.strip():
            return {
                "success": True,
                "text": original_text,
                "model_name": "no_text",
                "tokens_used": 0,
            }

        client = self._get_openai_client(config)
        models = config.paraphrase_models

        # Перемешиваем модели для распределения нагрузки
        shuffled_models = random.sample(models, len(models))

        for model_name in shuffled_models:
            try:
                logger.info(
                    f"[cyan]🔄 Пробую модель: {model_name.split('/')[-1]}[/cyan]"
                )

                response = await client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": config.paraphrase_system_prompt},
                        {
                            "role": "user",
                            "content": f"{config.paraphrase_user_prompt_template}\n\n{original_text}",
                        },
                    ],
                    temperature=config.paraphrase_temperature,
                    top_p=config.paraphrase_top_p,
                    max_tokens=config.paraphrase_max_tokens,
                    frequency_penalty=config.paraphrase_frequency_penalty,
                    presence_penalty=config.paraphrase_presence_penalty,
                )

                content = response.choices[0].message.content.strip()

                if content:
                    tokens = response.usage.total_tokens if response.usage else 0

                    return {
                        "success": True,
                        "text": content,
                        "model_name": model_name,
                        "tokens_used": tokens,
                    }

            except Exception as e:
                error_msg = str(e)
                logger.warning(
                    f"[yellow]⚠️  Ошибка на модели {model_name}: {error_msg[:80]}...[/yellow]"
                )
                continue

        # Если все модели не сработали
        logger.error("[red]❌ Все модели исчерпаны или недоступны[/red]")
        return {
            "success": False,
            "text": original_text,
            "error": "Все модели недоступны или лимиты исчерпаны",
            "model_name": "failed",
            "tokens_used": 0,
        }
