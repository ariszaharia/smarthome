import asyncio
from sqlalchemy import delete
from app.database import async_session
from app.models import User, Room, Device, UserRoom

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


async def seed():
    async with async_session() as session:

        # Start from an empty house so the script can be re-run safely
        for table in (Device, UserRoom, Room, User):
            await session.execute(delete(table))

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
                session.add(Device(name=name, type=type_, room_id=rooms[room_name].id, state=state))

        await session.commit()

    count = sum(len(d) for d in HOUSE.values())
    print(f"Seeded {len(HOUSE)} rooms and {count} devices.")


asyncio.run(seed())
