const requestsDiv = document.querySelector(".messages");
const input = document.getElementById("command-input");
const sendBtn = document.getElementById("send-btn");

console.log("Hello");



function addMessage(role, text) {
    const msg = document.createElement("div");
    msg.className = "msg " + role;
    msg.textContent = `${role.toUpperCase()}: ${text}`;

    requestsDiv.appendChild(msg);
    requestsDiv.scrollTop = requestsDiv.scrollHeight;
}


async function sendCommand() {
    const text = input.value.trim();
    if (!text) return;

    addMessage("user", text);
    input.value = "";

    try {
        const response = await fetch("/ask/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text })
        });

        const data = await response.json();

        addMessage("ai", data.response);
        

    } catch (err) {
        addMessage("system", "Error: " + err.message);
    }
}

async function updateStatus() {
    try {
        const response = await fetch("/status/");
        const data = await response.json();

        document.getElementById("light-status").textContent =
            data.light_on ? "ON" : "OFF";

        document.getElementById("temp-status").textContent =
            data.temperature;

    } catch (err) {
        console.error("Status error:", err);
    }
}

sendBtn.addEventListener("click", sendCommand);

input.addEventListener("keydown", e => {
    if (e.key === "Enter") sendCommand();
});

updateStatus();

setInterval(updateStatus, 1000);