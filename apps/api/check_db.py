import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT 1"))
        print("DB connected:", result.scalar_one())

asyncio.run(main())
