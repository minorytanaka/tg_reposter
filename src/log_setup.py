import logging

from rich.console import Console
from rich.logging import RichHandler


def setup_logging(level=logging.INFO):
    root = logging.getLogger()
    root.setLevel(level)

    # Убираем все старые хендлеры
    for h in root.handlers[:]:
        root.removeHandler(h)

    console = Console()

    handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        markup=True,
        show_path=False,
    )

    handler.setFormatter(
        logging.Formatter(
            "[bold cyan]{asctime}[/bold cyan] | "
            "[{levelname}] | "
            "[bold green]{name}[/bold green] | {message}",
            style="{",
            datefmt="%H:%M:%S",
        )
    )

    root.addHandler(handler)

    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
