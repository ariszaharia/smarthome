from langgraph.prebuilt import create_react_agent
from langchain_ollama import ChatOllama
from langchain_core.tools import tool

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sqlalchemy import select
from app.database import async_session
from app.models import Device, Room
from langchain_core.messages import SystemMessage, HumanMessage

import os


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
                "state": d.state or {}
            }
            for d, r in result.all()
        ]

@tool
async def set_temp(device_id: str, target_temp: int):
    """
    Set the temperature of a thermostat device (15–28°C).
    """
    async with async_session() as session:
        device = await session.get(Device, int(device_id))

        if not device:
            return f"Device with ID {device_id} not found."
        if device.type != "thermostat":
            return f"Device with ID {device_id} is not a thermostat."
        if not 15 <= target_temp <= 28:
            return "Temperature outside safe range (15–28)."

        device.state["temperature"] = target_temp
        await session.commit()

        return f"Success! Thermostat set to {target_temp}°C."


@tool
async def light_switch(device_id: str, on: bool):
    """
    Turn a light device ON or OFF.
    """
    async with async_session() as session:
        device = await session.get(Device, int(device_id))

        if not device:
            return f"Device with ID {device_id} not found."
        if device.type != "light":
            return f"Device with ID {device_id} is not a light bulb."

        device.state["on"] = on
        await session.commit()

        return f"Light bulb turned {'ON' if on else 'OFF'}."

@tool
async def light_brightness(device_id: str, brightness: int):
    """
    Adjust the brightness of a light device (0–100).
    Light must be ON.
    """
    async with async_session() as session:
        device = await session.get(Device, int(device_id))

        if not device:
            return f"Device with ID {device_id} not found."
        if not 0 <= brightness <= 100:
            return "Brightness should be between 0 and 100."
        if not device.state.get("on", False):
            return "Lights must be ON to adjust brightness."

        device.state["brightness"] = brightness
        await session.commit()

        return f"Brightness set to {brightness}."



tools = [set_temp, light_switch, light_brightness, find_devices]



llm = ChatOllama(
    model="qwen2.5:1.5b",
    base_url="http://localhost:11434",
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
- type ("light", "thermostat", etc.)
- room_name (string)
- state (object, e.g. {on, brightness, temperature})

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

- Turn on/off a light → light_switch(device_id, on)
- Change light brightness → light_brightness(device_id, brightness)
- Set temperature → set_temp(device_id, target_temp)

--------------------------------------------------
HOW TO SELECT A DEVICE
--------------------------------------------------

When a request is received:

1. Identify the intent (light, brightness, temperature).
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
→ call light_switch(device_id=1, on=true)

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


app = FastAPI(title = "Smart Home Assisant")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get('/')
def dashboard():
   return FileResponse(os.path.join(static_dir, "dashboard.html"))

from langchain_core.messages import SystemMessage, HumanMessage

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    while True:
        try:
            message = await websocket.receive_text()

            async with async_session() as session:
                from sqlalchemy.orm import joinedload
                result_db = await session.execute(
                    select(Device).options(joinedload(Device.room))
                )
                db_devices = result_db.scalars().all()
                device_info_for_ai = "CURRENT SYSTEM STATE:\n"
                for d in db_devices:
                    device_info_for_ai += (
                        f"- ID: {d.id}, Name: {d.name}, Type: {d.type}, "
                        f"Room: {d.room.name}, State: {d.state}\n"
                    )

            result = await agent.ainvoke({
                "messages": [
                    SystemMessage(content=device_info_for_ai),
                    HumanMessage(content=message)
                ]
            })

            async with async_session() as session:
                final_result = await session.execute(select(Device))
                updated_devices_json = [
                    {
                        "id": d.id,
                        "name": d.name,
                        "type": d.type,
                        "room_id": d.room_id,
                        "state": d.state
                    }
                    for d in final_result.scalars()
                ]

            await websocket.send_json({
                "text": result["messages"][-1].content,
                "devices": updated_devices_json
            })

        except Exception as e:
            print(f"WebSocket Error: {e}")
            break