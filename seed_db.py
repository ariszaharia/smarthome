"""Reset the house: delete every room and device and seed the demo house again.

You don't need this to get started (the API seeds an empty database on
startup). Use it to put the devices back to their starting state.
"""
import asyncio

from app.seed import HOUSE, prepare_database, reset_house


async def main():
    await prepare_database()  # makes sure the tables exist
    await reset_house()
    print(f"Reset the demo house: {len(HOUSE)} rooms, {sum(len(d) for d in HOUSE.values())} devices.")


asyncio.run(main())
