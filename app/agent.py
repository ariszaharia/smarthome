from langgraph.prebuilt import create_react_agent
from langchain_ollama import ChatOllama
from langchain_core.tools import tool

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sqlalchemy.orm import joinedload
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from app.database import async_session
from app.models import Device, Room
from app.seed import prepare_database
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    BaseMessage,
)

import os
from contextlib import asynccontextmanager


@tool
async def find_devices(query: str):
    """
    Search devices by room name, device name, or type.
    Returns a list of {device_id, name, type, room_name, state}.
    """
    async with async_session() as session:
        stmt = (
            select(Device, Room)
            .join(Room)
            .where(
                (Device.name.ilike(f"%{query}%")) |
                (Device.type.ilike(f"%{query}%")) |
                (Room.name.ilike(f"%{query}%"))
            )
            .limit(10)
        )

        result = await session.execute(stmt)

        return [
            {
                "device_id": str(d.id),
                "name": d.name,
                "type": d.type,
                "room_name": r.name,
                "state": d.state
            }
            for d, r in result.all()
        ]

async def update_state(device_id: str, types: set[str], changes: dict, requires_on: bool = False):
    """
    Load a device, check it is one of `types`, merge `changes` into its state
    and commit. Returns the device, or an error string for the model.
    """
    async with async_session() as session:
        device = await session.get(Device, int(device_id))

        if not device:
            return f"Device with ID {device_id} not found."
        if device.type not in types:
            return f"Device with ID {device_id} is a {device.type}, not a {' or '.join(sorted(types))}."
        if requires_on and not device.state.get("on", False):
            return f"{device.name} is off. Turn it on first."

        device.state.update(changes)
        flag_modified(device, "state")
        await session.commit()
        return device


@tool
async def set_temp(device_id: str, target_temp: int):
    """
    Set the temperature of a thermostat device (15–28°C).
    """
    if not 15 <= target_temp <= 28:
        return "Temperature outside safe range (15–28)."

    device = await update_state(device_id, {"thermostat"}, {"temperature": target_temp})
    if isinstance(device, str):
        return device
    return f"Success! {device.name} set to {target_temp}°C."


@tool
async def power_switch(device_id: str, on: bool):
    """
    Turn a light, plug (TV, coffee machine, towel rail...) or speaker ON or OFF.
    """
    device = await update_state(device_id, {"light", "plug", "speaker"}, {"on": on})
    if isinstance(device, str):
        return device
    return f"{device.name} turned {'ON' if on else 'OFF'}."


@tool
async def light_brightness(device_id: str, brightness: int):
    """
    Adjust the brightness of a light device (0–100).
    Light must be ON.
    """
    if not 0 <= brightness <= 100:
        return "Brightness should be between 0 and 100."

    device = await update_state(device_id, {"light"}, {"brightness": brightness}, requires_on=True)
    if isinstance(device, str):
        return device
    return f"{device.name} brightness set to {brightness}%."


@tool
async def set_blinds(device_id: str, position: int):
    """
    Open or close blinds. position is how far open they are:
    0 = fully closed, 100 = fully open, 50 = half open.
    """
    if not 0 <= position <= 100:
        return "Blinds position should be between 0 (closed) and 100 (open)."

    device = await update_state(device_id, {"blinds"}, {"position": position})
    if isinstance(device, str):
        return device
    return f"{device.name} set to {position}% open."


@tool
async def door_lock(device_id: str, locked: bool):
    """
    Lock (locked=true) or unlock (locked=false) a door lock.
    """
    device = await update_state(device_id, {"lock"}, {"locked": locked})
    if isinstance(device, str):
        return device
    return f"{device.name} {'locked' if locked else 'unlocked'}."


@tool
async def speaker_volume(device_id: str, volume: int):
    """
    Set the volume of a speaker (0–100). Speaker must be ON.
    """
    if not 0 <= volume <= 100:
        return "Volume should be between 0 and 100."

    device = await update_state(device_id, {"speaker"}, {"volume": volume}, requires_on=True)
    if isinstance(device, str):
        return device
    return f"{device.name} volume set to {volume}%."


tools = [set_temp, power_switch, light_brightness, set_blinds, door_lock, speaker_volume, find_devices]



llm = ChatOllama(
    model="qwen2.5:7b",
    base_url="http://ollama:11434",
    timeout=300
)


agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt = """
You are a Smart Home AI assistant connected to a real PostgreSQL-backed system.

The system provides you with a list of devices on every turn.
This device list is authoritative and always correct.

Each device has:
- id (string or integer, primary key)
- name (string)
- type ("light", "thermostat", "blinds", "lock", "speaker", "plug")
- room_name (string)
- state (object, e.g. {on, brightness}, {temperature}, {position}, {locked}, {on, volume})

--------------------------------------------------
CORE RULES (MUST FOLLOW)
--------------------------------------------------

1. You MUST NEVER invent a device_id.
2. You MAY use a device_id if it is explicitly provided by the system
   (for example, in the device list or in a tool result).
3. If exactly ONE device matches the user’s intent, you MUST act immediately.
4. If MULTIPLE devices match the intent, ask a short clarification question.
5. Ask for clarification ONLY when necessary.
6. DO NOT ask the user for a device_id if it is already known.
7. DO NOT ask follow-up questions after an action is successfully performed.

--------------------------------------------------
INTENT → ACTION MAPPING
--------------------------------------------------

- Turn on/off a light, plug or speaker → power_switch(device_id, on)
  (plugs power things like the TV, coffee machine and towel rail)
- Change light brightness → light_brightness(device_id, brightness)
- Set temperature → set_temp(device_id, target_temp)
- Open/close blinds → set_blinds(device_id, position)
  (open = 100, closed = 0, "half open" = 50)
- Lock/unlock a door → door_lock(device_id, locked)
- Change speaker volume → speaker_volume(device_id, volume)
- "All" requests (e.g. "turn off all lights") → call the tool once
  for EVERY matching device, without asking which one.
- Questions about the house ("is the front door locked?") → answer
  from the device list in one short sentence. Do not call a tool.

--------------------------------------------------
HOW TO SELECT A DEVICE
--------------------------------------------------

When a request is received:

1. Identify the intent (power, brightness, temperature, blinds, lock, volume).
2. Filter devices by:
   - device type
   - room_name (if mentioned)
   - device name (if mentioned)
3. If exactly one device matches → use it.
4. If more than one device matches → ask which one.
5. If no device matches → explain briefly and ask for clarification.

--------------------------------------------------
TOOL USAGE RULES
--------------------------------------------------

- Tools perform real actions on real devices.
- When calling a tool, respond ONLY with the tool call.
- Do NOT include explanations, confirmations, or extra text
  when a tool call is made.
- Use the tool arguments exactly as defined.

--------------------------------------------------
CLARIFICATION RULES
--------------------------------------------------

Ask a clarification question ONLY if:
- More than one device matches
- OR required information is missing (e.g., temperature value)

Clarification questions must be:
- Short
- Specific
- One question at a time

--------------------------------------------------
EXAMPLES
--------------------------------------------------

User: "Turn on the living room light"

(Exactly one matching device exists)

Assistant:
→ call power_switch(device_id=1, on=true)

---

User: "Set the temperature to 20"

(Exactly one thermostat exists)

Assistant:
→ call set_temp(device_id=2, target_temp=20)

---

User: "Turn on the light"

(Multiple lights exist)

Assistant:
"Which room?"

---

User: "Hello"

Assistant:
"Hello! How can I help you?"

--------------------------------------------------
OBJECTIVE
--------------------------------------------------

Your objective is to reliably control real smart home devices
with minimal conversation and maximum correctness.

Prefer action over conversation.
Never guess.
Never repeat questions unnecessarily.

"""




)
#agent.py location
current_dir = os.path.dirname(os.path.abspath(__file__))

#complete static dir path
static_dir = os.path.join(current_dir, "static")

if not os.path.exists(static_dir):
    raise RuntimeError(f"Static directory not found: {static_dir}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create the tables and seed the demo house on first start
    await prepare_database()
    yield


app = FastAPI(title = "Smart Home Assisant", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get('/')
def dashboard():
    return FileResponse(os.path.join(static_dir, "dashboard.html"))

MAX_HISTORY_MESSAGES = 20


async def get_devices() -> list[dict]:
    """Return every device with its room, in room creation order then by name.
    The dashboard lays out its floor plan in this order."""
    async with async_session() as session:
        res = await session.execute(select(Device).options(joinedload(Device.room)))
        devices = [
            {
                "id": d.id,
                "name": d.name,
                "type": d.type,
                "room": d.room.name if d.room else None,
                "room_id": d.room.id if d.room else None,
                "state": d.state,
            }
            for d in res.scalars().all()
        ]
    return sorted(devices, key=lambda d: (d["room_id"] or 0, d["name"]))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    history: list[BaseMessage] = []

    # Send the current state right away so the dashboard isn't empty
    await websocket.send_json({"devices": await get_devices()})

    while True:
        try:
            message = await websocket.receive_text()

            devices = await get_devices()
            state_str = "CURRENT STATE:\n" + "\n".join(
                f"- ID {d['id']}: {d['name']} ({d['type']}) in {d['room']}. State: {d['state']}"
                for d in devices
            )

            user_message = HumanMessage(content=message)

            result = await agent.ainvoke({
                "messages": [SystemMessage(content=state_str), *history, user_message]
            })

            reply = result["messages"][-1]

            history.append(user_message)
            history.append(AIMessage(content=reply.content))
            del history[:-MAX_HISTORY_MESSAGES]

            await websocket.send_json({
                "messages": reply.content,
                "devices": await get_devices()
            })

        except WebSocketDisconnect:
            print("WebSocket closed by client.")
            break
        except Exception as e:
            print(f"WebSocket Error: {e}")
            try:
                await websocket.send_json({
                    "messages": "The model didn't return an answer. Send the command again; "
                                "if it keeps failing, check the smarthome_api logs.",
                    "error": True
                })
            except Exception:
                break  # connection is gone