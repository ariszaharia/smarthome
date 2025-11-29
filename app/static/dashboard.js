const requestsDiv = document.querySelector(".messages");
const input = document.getElementById("command-input");
const sendBtn = document.getElementById("send-btn");
const websocket = new WebSocket(`ws://${window.location.host}/ws`);

websocket.onopen = () => {
    addMessage("system", "WebSocket connection established.");
}

websocket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    addMessage("ai", data.text);
    updateStatus(data.state);
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

function updateStatus(status){
    document.getElementById("light-status").textContent = status.lights.status;
    document.getElementById("temp-status").textContent = status.thermostat.temperature;
    document.getElementById("brightness-status").textContent = status.lights.brightness;
}



sendBtn.addEventListener("click", sendCommand);

input.addEventListener("keydown", e => {
    if (e.key === "Enter") sendCommand();
});
