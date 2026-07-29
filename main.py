import asyncio

from app.service import NewsFlowService


async def main() -> None:
    service = NewsFlowService()
    published = await service.run()
    print(f"NewsFlow2: опубликовано статей: {published}")


if __name__ == "__main__":
    asyncio.run(main())
