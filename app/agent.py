from langchain.agents import create_agent
from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from fastapi import FastAPI
from utils import LightBulb, Thermostat
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

t = Thermostat()
l = LightBulb()



@tool
def set_temp(target_temp: int):
    """Set the thermostat to the given temperature (°C)."""
    if target_temp < 15 or target_temp > 28:
        return f"Temperature {target_temp}°C is outside the safe range (15–28)."
    t.temp = target_temp
    return f"Success! Thermostat set to {target_temp}°C."


@tool
def light_switch(on: bool):
    """Switch the lights on or off."""
    if on:
        if l.status:
            return "The lights are already on."
        l.status = True
        return "Lights turned on!"
    else:
        if not l.status:
            return "The lights are already off."
        l.status = False
        return "Lights turned off."
    
@tool
def light_brightness(brightness: int):
    """Adjust the brightness of the lights"""
    if not 0<=brightness<=100:
        return "Brightness should be between 0 and 100"
    if not l.status:
        return "Lights should be turned ON to adjust brightness"

    l.brightness = brightness
    return f"Brightness set to {brightness}"

tools = [set_temp, light_switch, light_brightness]



llm = ChatOllama(
    model="qwen2.5:1.5b",
    base_url="http://ollama:11434",
)


agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt = """
You are a smart-home assistant. 
You can (and SHOULD) call tools:
1. set_temp(target_temp: int)
2. light_switch(on: bool)
3. light_brightness

When the user speaks naturally, you MUST understand their intent and call the right tool.

Examples
User: I'm cold.
Assistant: <tool_call>{"name": "set_temp", "arguments": {"target_temp": 25}}</tool_call>

User: It's too hot in here.
Assistant: <tool_call>{"name": "set_temp", "arguments": {"target_temp": 20}}</tool_call>

User: It's too dark.
Assistant: <tool_call>{"name": "light_switch", "arguments": {"on": true}}</tool_call>

User: Make it dark.
Assistant: <tool_call>{"name": "light_switch", "arguments": {"on": false}}</tool_call>

User: Turn the lights on.
Assistant: <tool_call>{"name": "light_switch", "arguments": {"on": true}}</tool_call>

User : Lower the brightness.
Assistant : <tool_call>{"name" : "light_brightness", "arguments" : {brightness : you put a lower value here}} </tool_call>

User: Brightness higher.
Assistant : <tool_call>{"name" : "light_brightness", "arguments" : {brightness : you put a higher value here}} </tool_call>

User: Hello.
Assistant: Hello! How can I help you?

Always respond using that same <tool_call> format when an action is requested.
"""

)

class Command(BaseModel):
    text: str


app = FastAPI(title = "Smart Home Assisant")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/") 
async def dashboard(): 
    return FileResponse("static/dashboard.html")

@app.post("/ask/")
async def ask_agent(cmd: Command):
    try:
        result = await agent.ainvoke({"messages": [("user", cmd.text)]})

        tool_names = []
        for m in result["messages"]:
            if hasattr(m, "tool_calls"):
                for tc in m.tool_calls:
                    tool_names.append(tc["name"])
                
        if tool_names:
            return ({
                "response" : result["messages"][-1].content,
                "tools_called" : tool_names
            })
        

        return {"response": result["messages"][-1].content}

    except Exception as e:
        return {"error": str(e)}

@app.get("/status/")
async def get_status():
    return {
        "light_on": l.status,
        "temperature": t.temp,
        "brightness" : l.brightness
    }
