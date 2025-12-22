A full-stack, autonomous AI agentic system designed to control a simulated smart home environment. This project integrates a **Local LLM (Qwen 2.5 7B)** with a **PostgreSQL** database via **Asynchronous WebSockets**.
---
* **LLM**: Qwen 2.5 (7B) running locally via **Ollama**.
* **Orchestration**: **LangGraph** for reasoning and tool-calling loops.
* **Backend**: **FastAPI** with Asynchronous WebSockets.
* **Database**: **PostgreSQL** with **SQLAlchemy (Async)**.
* **Infrastructure**: **Docker Compose** for container orchestration.

---

### **1. Database Schema (`models.py`)**
The system uses a relational schema where devices are linked to rooms, and their status is stored in a flexible JSONB `state` column.
* **Room Table**: Stores room names (e.g., "Living Room").
* **Device Table**: Stores device types and a dynamic JSON `state` (e.g., `{"on": true, "brightness": 70}`).
* **Users Tabel**: NOT YET IMPLEMENTED

### **2. Agentic Reasoning (`agent.py`)**
The agent is built using `create_react_agent` and is equipped with the following tools:
* `find_devices`: Searches the database for devices using ILIKE queries (The LLM understands a specific word or a sequence of words and check if any entry in the table contains it).
* `light_switch`: Modifies the `on` state of light bulbs.
* `set_temp`: Adjusts thermostat temperatures.
* `light_brightness`: Changes the brightness of the lightbulbs.

### **3. Real-Time Sync (WebSockets)**
On every user message, the system performs a dual-sync:
1. **Pre-processing**: Fetches the latest DB state using `joinedload` to provide the LLM with context.
2. **Post-processing**: Re-queries the DB after tool execution to send the updated JSON state to the frontend.
