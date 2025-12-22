
A full-stack, autonomous AI agentic system designed to control a simulated smart home environment. This project demonstrates the integration of **Local LLMs (Ollama)** with **Relational Databases (PostgreSQL)** via a real-time **WebSocket** interface.

---

## Evolution & Progress

This project evolved through three distinct architectural stages, each solving a specific limitation found in the previous version:

### 1. `main` (The REST API Baseline)
* **Design**: Standard RESTful endpoints for controlling devices and checking status.
* **The Problem**: Required the frontend to constantly fetch a status endpoint to detect changes. This was inefficient, used unnecessary resources, and lacked real-time responsiveness.

### 2. `websocket` (The Real-Time Shift)
* **Design**: Migrated from REST to **Asynchronous WebSockets**.
* **The Solution**: Enabled uninterrupted communication. The server can now "push" data to the frontend immediately whenever the AI agent performs an action, providing a better user experience.

### 3. `database` (The Agentic State - Current)
* **Design**: Integrated a **PostgreSQL** database with **SQLAlchemy (Async)**.
* **The Solution**: Moved beyond simulation stage to persistent storage. The LLM (Qwen 2.5 7B) now acts as a **Database Controller**, using tools to find devices in specific rooms and executing SQL commits to modify their state.

---

##  Tech Stack

* **LLM**: Qwen 2.5 (7B) running locally via **Ollama**.
* **Orchestration**: **LangGraph** for reasoning and tool-calling loops.
* **Backend**: **FastAPI** with Asynchronous WebSockets.
* **Database**: **PostgreSQL** for persistent state management.
* **Infrastructure**: **Docker Compose** for orchestrating API, Database, and LLM services.

---

## Key Technical Features

* **Persistent Storage**: The PostgreSQL database ensures state persists across container restarts.
* **Efficient Queries**: Uses SQLAlchemy `joinedload` to optimize AI context retrieval, fetching Devices and Rooms in a single SQL operation to minimize latency.
* **State Integrity**: Implements `flag_modified` to ensure JSONB state updates are correctly tracked and committed to the database.

## How to run it
**Make sure to install Docker Desktop and it is open**  

git clone -b database https://github.com/ariszaharia/smarthome.git  

cd smarthome  
First time opening:  
docker compose up -d --build  
If you want to remove the containers after:  
docker compose down  
Reopen the app:  
docker compose up


