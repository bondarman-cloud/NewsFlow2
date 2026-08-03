import argparse
import asyncio
import os


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one bot from the shared platform")
    parser.add_argument(
        "--bot",
        default=os.getenv("BOT_ID", "hardware_news"),
        help="Bot profile ID from bots/<id>/config.yaml",
    )
    parser.add_argument(
        "--mode",
        choices=("manual", "scheduled"),
        default=os.getenv("RUN_MODE", "scheduled"),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore the scheduled publication interval",
    )
    return parser.parse_args()


async def run() -> None:
    args = parse_args()
    os.environ["BOT_ID"] = args.bot
    os.environ["RUN_MODE"] = args.mode
    if args.force:
        os.environ["FORCE_PUBLISH"] = "true"

    # Import after selecting the profile. Settings are intentionally loaded once.
    from app.config import settings

    if settings.application == "news":
        from app.service import NewsFlowService

        service = NewsFlowService()
    elif settings.application == "worldfood":
        from app.worldfood_guaranteed import GuaranteedWorldFoodService

        service = GuaranteedWorldFoodService()
    else:
        raise ValueError(f"Неизвестный тип приложения: {settings.application!r}")

    published = await service.run()
    print(f"{settings.bot_id}: опубликовано материалов: {published}")


if __name__ == "__main__":
    asyncio.run(run())
