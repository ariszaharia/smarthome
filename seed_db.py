import asyncio
from app.database import async_session
from app.models import User, Room, Device, UserRoom

async def seed():
    async with async_session() as session:

        sef = User(username="sef")
        guest = User(username="guest")

        session.add_all([sef, guest])
        await session.flush()

        living = Room(name="Living Room")
        bedroom = Room(name="Bedroom")

        session.add_all([living, bedroom])
        await session.flush()

        session.add_all([
            UserRoom(user_id=sef.id, room_id=living.id, role="sef"),
            UserRoom(user_id=sef.id, room_id=bedroom.id, role="sef"),
            UserRoom(user_id=guest.id, room_id=living.id, role="controller"),
        ])

        session.add_all([
            Device(
                name="Living Room Light",
                type="light",
                room_id=living.id,
                state={"on": False, "brightness": 70}
            ),
            Device(
                name="Living Room Thermostat",
                type="thermostat",
                room_id=living.id,
                state={"temperature": 21}
            ),
            Device(
                name="Bedroom Light",
                type="light",
                room_id=bedroom.id,
                state={"on": True, "brightness": 40}
            ),
        ])

        await session.commit()

asyncio.run(seed())
