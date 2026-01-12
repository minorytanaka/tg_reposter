import asyncio
import logging
import random
import time

from rich.console import Console
from rich.table import Table

from history_manager import HistoryManager
from log_setup import setup_logging
from settings import Settings
from telegram_handler import TelegramHandler, get_client

logger = logging.getLogger(__name__)
console = Console()


async def main():
    start_time = time.time()

    try:
        # Инициализация
        config = Settings("config.ini")
        config.validate()

        # Health-check API
        logger.info("[cyan]🔍 Проверка API ключа...[/cyan]")
        client = get_client(config)
        tg_handler = TelegramHandler()

        # Проверка моделей
        await tg_handler.health_check(config)
        logger.info("[green]✅ Все проверки пройдены успешно![/green]")

        # Инициализация истории
        history_manager = HistoryManager()

        stats = {
            "total_processed": 0,
            "sent_posts": 0,
            "skipped_posts": 0,
            "failed_paraphrase": 0,
            "tokens_used": 0,
            "models_used": {},
        }

        async with client:
            logger.info(
                f"[cyan]📡 Начинаю работу с {len(config.source_channels)} источниками...[/cyan]"
            )

            for source_channel in config.source_channels:
                logger.info(f"[blue]🔎 Сканирую канал: {source_channel}[/blue]")

                posts = await tg_handler.fetch_posts(client, source_channel, config)
                logger.info(
                    f"[cyan]📊 Найдено {len(posts)} постов за последние {config.period_hours} часов[/cyan]"
                )

                for post in posts:
                    stats["total_processed"] += 1

                    # Проверка на дубликат
                    post_signature = tg_handler.generate_post_signature(post)
                    if history_manager.is_post_sent(post_signature):
                        logger.info(
                            f"[yellow]⏭️  Пост уже отправлен ранее, пропускаю...[/yellow]"
                        )
                        stats["skipped_posts"] += 1
                        continue

                    try:
                        # Отправка поста
                        result = await tg_handler.send_post(
                            client, config.target_channel, post, config
                        )

                        if result["success"]:
                            stats["sent_posts"] += 1
                            stats["tokens_used"] += result.get("tokens_used", 0)

                            # Сохраняем модель в статистику
                            model_name = result.get("model_name", "unknown")
                            stats["models_used"][model_name] = (
                                stats["models_used"].get(model_name, 0) + 1
                            )

                            # Сохраняем в историю
                            history_manager.mark_post_sent(post_signature)

                            logger.info(
                                f"[green]✅ Пост успешно отправлен! (модель: {model_name})[/green]"
                            )
                        else:
                            stats["failed_paraphrase"] += 1
                            logger.warning(
                                f"[yellow]⚠️  Отправлен оригинальный текст[/yellow]"
                            )

                    except Exception as e:
                        logger.error(f"[red]❌ Ошибка при отправке поста: {e}[/red]")
                        continue

                    # Случайная задержка между постами
                    delay = random.uniform(config.min_delay, config.max_delay)
                    logger.info(f"[cyan]⏳ Пауза {delay:.1f} сек...[/cyan]")
                    await asyncio.sleep(delay)

        # Вывод статистики
        elapsed_time = time.time() - start_time
        await print_statistics(stats, elapsed_time, history_manager)

    except Exception as e:
        logger.error(f"[red]🔥 Критическая ошибка: {e}[/red]")
        raise


async def print_statistics(stats, elapsed_time, history_manager):
    """Вывод статистики"""

    console.print("\n" + "=" * 60)
    console.print("[bold cyan]📊 СТАТИСТИКА ВЫПОЛНЕНИЯ[/bold cyan]")
    console.print("=" * 60)

    # Таблица статистики
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Метрика", style="cyan")
    table.add_column("Значение", style="green", justify="right")

    table.add_row("Общее время", f"{elapsed_time:.2f} сек")
    table.add_row("Обработано постов", str(stats["total_processed"]))
    table.add_row("Успешно отправлено", f"{stats['sent_posts']} ✅")
    table.add_row("Пропущено (дубли)", f"{stats['skipped_posts']} ⏭️")
    table.add_row("Ошибок перефразирования", f"{stats['failed_paraphrase']} ⚠️")
    table.add_row("Потрачено токенов", f"{stats['tokens_used']} 🪙")
    table.add_row("В истории постов", f"{history_manager.get_total_sent()} 📝")

    console.print(table)

    # Статистика по моделям
    if stats["models_used"]:
        console.print("\n[bold cyan]🤖 Использованные модели:[/bold cyan]")
        model_table = Table(show_header=True, header_style="bold blue")
        model_table.add_column("Модель", style="yellow")
        model_table.add_column("Использований", style="green", justify="right")

        for model, count in stats["models_used"].items():
            short_name = model.split("/")[-1][:30] + "..." if len(model) > 30 else model
            model_table.add_row(short_name, str(count))

        console.print(model_table)

    console.print("\n[bold green]🎯 Работа завершена успешно![/bold green]")


if __name__ == "__main__":
    setup_logging(level=logging.INFO)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Программа остановлена пользователем[/yellow]")
