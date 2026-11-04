from langgraph.prebuilt import create_react_agent
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
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
    ToolMessage,
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


@tool(return_direct=True)
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


@tool(return_direct=True)
async def power_switch(device_id: str, on: bool):
    """
    Turn a light, plug (TV, coffee machine, towel rail...) or speaker ON or OFF.
    """
    device = await update_state(device_id, {"light", "plug", "speaker"}, {"on": on})
    if isinstance(device, str):
        return device
    return f"{device.name} turned {'ON' if on else 'OFF'}."


@tool(return_direct=True)
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


@tool(return_direct=True)
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


@tool(return_direct=True)
async def door_lock(device_id: str, locked: bool):
    """
    Lock (locked=true) or unlock (locked=false) a door lock.
    """
    device = await update_state(device_id, {"lock"}, {"locked": locked})
    if isinstance(device, str):
        return device
    return f"{device.name} {'locked' if locked else 'unlocked'}."


@tool(return_direct=True)
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



LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")

if LLM_PROVIDER == "gemini":
    
    llm = ChatGoogleGenerativeAI(
        model=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        google_api_key=os.environ["GOOGLE_API_KEY"],
        temperature=0,
        timeout=60,
        # Fail fast on quota errors instead of silently retrying for a minute.
        max_retries=1,
    )
else:
    llm = ChatOllama(
        model="qwen2.5:7b",
        base_url="http://ollama:11434",
        timeout=300,
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

            turn_input = [SystemMessage(content=state_str), *history, user_message]
            result = await agent.ainvoke({"messages": turn_input})

            new_messages = result["messages"][len(turn_input):]
            last = new_messages[-1] if new_messages else None

            # Device tools return directly, so a turn ends either with the model's
            # text or with tool results. Gemini may also end with an empty message.
            if isinstance(last, AIMessage) and last.text.strip():
                reply_text = last.text.strip()
            else:
                tool_results = [m.text for m in new_messages if isinstance(m, ToolMessage)]
                reply_text = " ".join(tool_results) or "Done."

            # Keep the real tool calls in the history; with only text replies the
            # model learns to say "turned ON" without calling a tool.
            if isinstance(last, AIMessage) and not last.tool_calls:
                new_messages = new_messages[:-1]
            history.extend([user_message, *new_messages, AIMessage(content=reply_text)])

            # Trim whole turns so a tool call is never separated from its result.
            while len(history) > MAX_HISTORY_MESSAGES:
                next_turn = next(
                    (i for i, m in enumerate(history) if i > 0 and isinstance(m, HumanMessage)),
                    None,
                )
                if next_turn is None:
                    break
                del history[:next_turn]

            await websocket.send_json({
                "messages": reply_text,
                "devices": await get_devices()
            })

        except WebSocketDisconnect:
            print("WebSocket closed by client.")
            break
        except Exception as e:
            print(f"WebSocket Error: {e}")
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                error_text = ("The Gemini API quota is used up. Wait a bit (or until tomorrow "
                              "for the daily limit), or switch GEMINI_MODEL / enable billing.")
            else:
                error_text = ("The model didn't return an answer. Send the command again; "
                              "if it keeps failing, check the smarthome_api logs.")
            try:
                await websocket.send_json({
                    "messages": error_text,
                    "error": True
                })
            except Exception:
                break  