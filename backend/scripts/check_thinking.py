import asyncio
from app.core.database import SessionLocal
from app.models.personal import PersonalData

async def check():
    async with SessionLocal() as db:
        for prefix in ["c5f1d85b", "9ce7b14c", "aa48a33d", "28d1a956"]:
            # PersonalData IDs are UUIDs, so we cast to text for LIKE
            from sqlalchemy import text
            stmt = text(f"SELECT id, metadata->'vision_description'->>'_thinking' as thinking FROM mindscape_personal WHERE id::text LIKE '{prefix}%'")
            result = await db.execute(stmt)
            rows = result.fetchall()
            if not rows:
                print(f"{prefix}: Not Found")
            for row in rows:
                print(f"{row.id}: {'(Has Thinking)' if row.thinking else '(NO Thinking)'}")

if __name__ == "__main__":
    asyncio.run(check())
