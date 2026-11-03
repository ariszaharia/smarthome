"""Creates the tables and fills them with the demo house.

The API calls prepare_database() on startup, so a fresh `docker compose up`
works without any manual steps. Run seed_db.py to reset the house later.
"""
import asyncio

from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError

from app.database import async_session, engine
from app.models import Base, Device, Room, User, UserRoom

# Rooms are created in floor-plan order: the dashboard puts the first half
# along the back of the house and the rest (with the front door) along the front.
HOUSE = {
    "Bedroom": [
        ("Bedroom Light", "light", {"on": True, "brightness": 40}),
        ("Bedside Lamp", "light", {"on": False, "brightness": 25}),
        ("Bedroom Blinds", "blinds", {"position": 0}),
        ("Bedroom Thermostat", "thermostat", {"temperature": 19}),
    ],
    "Bathroom": [
        ("Bathroom Light", "light", {"on": False, "brightness": 100}),
        ("Towel Rail", "plug", {"on": False}),
    ],
    "Kitchen": [
        ("Kitchen Light", "light", {"on": True, "brightness": 80}),
        ("Coffee Machine", "plug", {"on": False}),
        ("Kitchen Blinds", "blinds", {"position": 100}),
    ],
    "Living Room": [
        ("Living Room Light", "light", {"on": False, "brightness": 70}),
        ("Floor Lamp", "light", {"on": True, "brightness": 35}),
        ("Living Room Thermostat", "thermostat", {"temperature": 21}),
        ("Living Room Blinds", "blinds", {"position": 50}),
        ("Living Room Speaker", "speaker", {"on": False, "volume": 30}),
        ("TV", "plug", {"on": False}),
    ],
    "Hallway": [
        ("Hallway Light", "light", {"on": False, "brightness": 60}),
        ("Front Door", "lock", {"locked": True}),
    ],
}


async def seed_house(session):
    """Add the demo users, rooms and devices. Expects empty tables."""
    sef = User(username="sef")
    guest = User(username="guest")
    session.add_all([sef, guest])
    await session.flush()

    rooms = {}
    for name in HOUSE:
        rooms[name] = Room(name=name)
        session.add(rooms[name])
        await session.flush()  # one at a time so ids follow plan order

    for room in rooms.values():
        session.add(UserRoom(user_id=sef.id, room_id=room.id, role="sef"))
    for name in ("Living Room", "Kitchen"):
        session.add(UserRoom(user_id=guest.id, room_id=rooms[name].id, role="controller"))

    for room_name, devices in HOUSE.items():
        for name, type_, state in devices:
            session.add(Device(name=name, type=type_, room_id=rooms[room_name].id, state=dict(state)))

    await session.commit()


async def reset_house():
    """Delete everything and seed the demo house again."""
    async with async_session() as session:
        for table in (Device, UserRoom, Room, User):
            await session.execute(delete(table))
        await seed_house(session)


async def prepare_database(attempts: int = 10):
    """Create missing tables, then seed the demo house if there are no rooms yet.
    Existing data is never touched."""
    for attempt in range(1, attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            break
        except (DBAPIError, OSError) as e:
            # Postgres may still be starting up
            if attempt == attempts:
                raise
            print(f"Database not ready ({e.__class__.__name__}), retrying in 2 s…")
            await asyncio.sleep(2)

    async with async_session() as session:
        if await session.scalar(select(Room.id).limit(1)) is None:
            await seed_house(session)
            print(f"Seeded the demo house: {len(HOUSE)} rooms, "
                  f"{sum(len(d) for d in HOUSE.values())} devices.")
        else:
            print("Database already has data, skipping seed.")
