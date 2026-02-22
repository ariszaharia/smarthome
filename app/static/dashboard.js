const requestsDiv = document.querySelector(".messages");
const input = document.getElementById("command-input");
const sendBtn = document.getElementById("send-btn");
const websocket = new WebSocket(`ws://${window.location.host}/ws`);

websocket.onopen = () => {
    addMessage("system", "WebSocket connection established.");
}

websocket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    const textRaspuns = data.message || data.messages; 
    
    if (textRaspuns) {
        addMessage("ai", textRaspuns);
    }
    
    if (data.devices) {
        updateStatus(data.devices);
    }
}

function addMessage(role, text) {
    const msg = document.createElement("div");
    msg.className = "msg " + role;
    msg.textContent = `${role.toUpperCase()}: ${text}`;

    requestsDiv.appendChild(msg);
    requestsDiv.scrollTop = requestsDiv.scrollHeight;
}

function sendCommand() {
    const text = input.value.trim();
    if (!text) return;

    addMessage("user", text);
    input.value = "";

    websocket.send(text);
}

// Actualizeaza fiecare device in parte bazat pe numele din baza de date
function updateStatus(devices) {
    devices.forEach(device => {
        
        if (device.name === "Living Room Light") {
            const statusEl = document.getElementById("living-light-status");
            const brightEl = document.getElementById("living-brightness-status");
            if (statusEl) statusEl.textContent = device.state.on ? "ON" : "OFF";
            if (brightEl) brightEl.textContent = device.state.brightness || 0;
        } 
        
        else if (device.name === "Bedroom Light") {
            const statusEl = document.getElementById("bedroom-light-status");
            const brightEl = document.getElementById("bedroom-brightness-status");
            if (statusEl) statusEl.textContent = device.state.on ? "ON" : "OFF";
            if (brightEl) brightEl.textContent = device.state.brightness || 0;
        } 
        
        else if (device.name === "Living Room Thermostat") {
            const tempEl = document.getElementById("living-temp-status");
            if (tempEl) tempEl.textContent = device.state.temperature || 0;
        }
    });
}

sendBtn.addEventListener("click", sendCommand);

input.addEventListener("keydown", e => {
    if (e.key === "Enter") sendCommand();
});