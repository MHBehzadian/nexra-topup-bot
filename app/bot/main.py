"""Bot entrypoint: build the dispatcher and run long polling."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from .. import db
from ..config import settings
from .middlewares import ForceJoinMiddleware
from .routers import all_routers
from .warnings import run_warning_scanner

logger = logging.getLogger(__name__)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    force_join = ForceJoinMiddleware()
    dp.message.outer_middleware(force_join)
    dp.callback_query.outer_middleware(force_join)
    for router in all_routers:
        dp.include_router(router)
    return dp


async def run() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not set — configure it in .env")
    if not settings.nexra_panel_api_url or not settings.nexra_panel_bot_api_key:
        raise RuntimeError(
            "NEXRA_PANEL_API_URL / NEXRA_PANEL_BOT_API_KEY are not set — configure them in .env"
        )
    db.init_db()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()
    logger.info("starting bot polling")
    await bot.delete_webhook(drop_pending_updates=True)
    scanner = asyncio.create_task(run_warning_scanner(bot))
    try:
        await dp.start_polling(bot)
    finally:
        scanner.cancel()
        await bot.session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
