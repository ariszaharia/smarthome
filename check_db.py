import asyncio
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from app.database import async_session
from app.models import Device, Room

async def check_database():
    print("--- FETCHING CURRENT DATABASE STATE ---")
    async with async_session() as session:
        try:
            stmt = select(Device).options(joinedload(Device.room))
            result = await session.execute(stmt)
            devices = result.scalars().all()

            if not devices:
                print("Database is empty or tables aren't initialized.")
                return

            for d in devices:
                status = "ON" if d.state.get("on") else "OFF"
                if d.type == "thermostat":
                    status = f"{d.state.get('temperature')}°C"
                
                print(f"[{d.id}] {d.name} ({d.type})")
                print(f"    Room: {d.room.name}")
                print(f"    State: {status}")
                print("-" * 30)

        except Exception as e:
            print(f"Error connecting to database: {e}")

if __name__ == "__main__":
    asyncio.run(check_database())