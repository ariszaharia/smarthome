// Ranges enforced by the tools on the backend
const TEMP_MIN = 15;
const TEMP_MAX = 28;

const $ = (id) => document.getElementById(id);
const planEl = $("plan");
const logEl = $("log");
const form = $("chat-form");
const input = $("command-input");
const sendBtn = $("send-btn");
const connectionEl = $("connection");
const summaryEl = $("summary");
const suggestionsEl = $("suggestions");

let socket = null;
let devices = [];        // latest device list from the server
let layoutKey = "";      // which rooms/devices are currently drawn
let roomOrder = [];      // room names in the order the plan draws them
let pending = null;      // { reply, timer, turn, before } while the model works

// ---------- helpers ----------

const clamp = (n, min, max) => Math.min(max, Math.max(min, n));

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
}

// "Living Room Light" in room "Living Room" -> "Light"
function displayName(name, room) {
    if (room && name.toLowerCase().startsWith(room.toLowerCase() + " ")) {
        const rest = name.slice(room.length + 1);
        return rest.charAt(0).toUpperCase() + rest.slice(1);
    }
    return name;
}

// "Living Room Light" -> "the living room light", "TV" -> "the TV"
function refer(device) {
    return "the " + device.name.replace(/\b([A-Z])([a-z]+)/g, (_, a, b) => a.toLowerCase() + b);
}

function groupByRoom(list) {
    const rooms = new Map();
    for (const d of list) {
        const room = d.room || "Unassigned";
        if (!rooms.has(room)) rooms.set(room, []);
        rooms.get(room).push(d);
    }
    return rooms;
}

const isOn = (d) => Boolean(d.state?.on);
const brightness = (d) => clamp(Number(d.state?.brightness) || 0, 0, 100);
const temperature = (d) => Number(d.state?.temperature);
const position = (d) => clamp(Number(d.state?.position) || 0, 0, 100);
const volume = (d) => clamp(Number(d.state?.volume) || 0, 0, 100);
const isLocked = (d) => Boolean(d.state?.locked);

function blindsText(d) {
    const p = position(d);
    return p === 0 ? "closed" : p === 100 ? "open" : `${p}% open`;
}

function clock(date = new Date()) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// Small plan-style symbols for the devices that sit on the walls
const ICON = {
    blinds: '<path d="M2 3h12M3 6.3h10M3 9.6h10M3 13h10"/>',
    locked: '<rect x="3.5" y="7" width="9" height="7" rx="1"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/>',
    unlocked: '<rect x="3.5" y="7" width="9" height="7" rx="1"/><path d="M5.5 7V5a2.5 2.5 0 0 1 4.8-1"/>',
    plug: '<circle cx="8" cy="8" r="5.75"/><path d="M6.3 6.2v3.6M9.7 6.2v3.6"/>',
    speaker: '<path d="M2.5 6h2.5l3.5-3v10l-3.5-3H2.5z"/>',
    wave1: '<path d="M11 6a2.8 2.8 0 0 1 0 4"/>',
    wave2: '<path d="M12.8 4a5.6 5.6 0 0 1 0 8"/>',
    thermostat: '<circle cx="8" cy="8" r="5.75"/><path d="M5.8 6h4.4M8 6v4.6"/>',
    other: '<rect x="3" y="3" width="10" height="10" rx="1.5"/>',
};

function icon(d) {
    let shape;
    if (d.type === "lock") shape = isLocked(d) ? ICON.locked : ICON.unlocked;
    else if (d.type === "speaker") {
        shape = ICON.speaker
            + (isOn(d) && volume(d) > 0 ? ICON.wave1 : "")
            + (isOn(d) && volume(d) > 50 ? ICON.wave2 : "");
    } else shape = ICON[d.type] ?? ICON.other;
    return `<svg viewBox="0 0 16 16" aria-hidden="true">${shape}</svg>`;
}

// ---------- websocket ----------

const STATUS_TEXT = { connecting: "Connecting", online: "Connected", offline: "Offline, retrying" };

function connect() {
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${location.host}/ws`);
    setConnection("connecting");

    socket.addEventListener("open", () => setConnection("online"));

    socket.addEventListener("message", (event) => handleMessage(JSON.parse(event.data)));

    socket.addEventListener("close", () => {
        setConnection("offline");
        if (pending) {
            finishTurn("Lost the connection to the server before it answered. Reconnecting…", true, null);
        }
        setTimeout(connect, 2000);
    });
}

function handleMessage(data) {
    const next = Array.isArray(data.devices) ? data.devices : null;

    const text = data.messages ?? data.message;
    if (text) finishTurn(text, Boolean(data.error), next);

    if (next) {
        devices = next;
        renderPlan(devices);
        renderSummary(devices);
        renderSuggestions(devices);
    }
}

function setConnection(status) {
    connectionEl.dataset.status = status;
    connectionEl.textContent = STATUS_TEXT[status];
    updateControls();
}

function updateControls() {
    sendBtn.disabled = !(socket && socket.readyState === WebSocket.OPEN && !pending);
}

// ---------- command log ----------

function newTurn() {
    $("empty")?.remove();
    const turn = document.createElement("article");
    turn.className = "turn";
    const time = document.createElement("time");
    time.textContent = clock();
    turn.append(time);
    logEl.append(turn);
    return turn;
}

function startTurn(text) {
    const turn = newTurn();

    const said = document.createElement("p");
    said.className = "said";
    said.textContent = text;

    const reply = document.createElement("p");
    reply.className = "reply pending";
    reply.textContent = "Waiting for the model";

    turn.append(said, reply);
    logEl.scrollTop = logEl.scrollHeight;

    // The model can take a while on CPU, so show how long it has been working
    const started = Date.now();
    const timer = setInterval(() => {
        reply.textContent = `Waiting for the model, ${Math.round((Date.now() - started) / 1000)} s`;
    }, 1000);

    pending = { turn, reply, timer, before: devices };
    updateControls();
}

function finishTurn(text, isError, after) {
    let turn, reply, before = null;

    if (pending) {
        clearInterval(pending.timer);
        ({ turn, reply, before } = pending);
        pending = null;
    } else {
        // A message the server sent on its own
        turn = newTurn();
        reply = document.createElement("p");
        turn.append(reply);
    }

    reply.className = isError ? "reply error" : "reply";
    reply.textContent = text;

    // Show what actually changed in the house, which isn't always what the model says
    if (before && after && !isError) {
        const changes = diffDevices(before, after);
        if (changes.length) {
            const list = document.createElement("ul");
            list.className = "changes";
            for (const c of changes) {
                const li = document.createElement("li");
                li.textContent = c.text;
                if (c.lit) li.className = "up";
                list.append(li);
            }
            turn.append(list);
        } else {
            const none = document.createElement("p");
            none.className = "no-change";
            none.textContent = "No devices changed.";
            turn.append(none);
        }
    }

    logEl.scrollTop = logEl.scrollHeight;
    updateControls();
}

function describeChange(prev, d) {
    switch (d.type) {
        case "light":
            if (isOn(prev) !== isOn(d)) return isOn(d) ? `turned on at ${brightness(d)}%` : "turned off";
            if (brightness(prev) !== brightness(d)) {
                return `${brightness(d) < brightness(prev) ? "dimmed" : "brightened"} from ${brightness(prev)}% to ${brightness(d)}%`;
            }
            break;
        case "thermostat":
            return `set from ${temperature(prev)} °C to ${temperature(d)} °C`;
        case "blinds":
            if (position(d) === 0) return "closed";
            if (position(d) === 100) return "opened";
            return `set from ${blindsText(prev)} to ${position(d)}% open`;
        case "lock":
            return isLocked(d) ? "locked" : "unlocked";
        case "speaker":
            if (isOn(prev) !== isOn(d)) return isOn(d) ? `turned on at volume ${volume(d)}%` : "turned off";
            if (volume(prev) !== volume(d)) return `volume from ${volume(prev)}% to ${volume(d)}%`;
            break;
        case "plug":
            if (isOn(prev) !== isOn(d)) return isOn(d) ? "turned on" : "turned off";
            break;
    }
    return "changed";
}

function diffDevices(before, after) {
    const old = new Map(before.map((d) => [d.id, d]));
    const changes = [];

    for (const d of after) {
        const prev = old.get(d.id);
        if (!prev || JSON.stringify(prev.state) === JSON.stringify(d.state)) continue;
        changes.push({
            text: `${d.name} ${describeChange(prev, d)}`,
            lit: "on" in (d.state || {}) ? isOn(d) : false,
        });
    }

    return changes;
}

function send(text) {
    text = text.trim();
    if (!text || pending || !socket || socket.readyState !== WebSocket.OPEN) return;

    startTurn(text);
    socket.send(text);
    input.value = "";
}

// ---------- floor plan ----------

// Up to three rooms sit in one row. More than that splits the house into a
// back row and a front row; rooms with a door lock go at the front, last.
function planRows(rooms) {
    if (rooms.length <= 3) return [rooms];
    const hasLock = ([, items]) => items.some((d) => d.type === "lock");
    const ordered = [...rooms.filter((r) => !hasLock(r)), ...rooms.filter(hasLock)];
    const back = Math.ceil(ordered.length / 2);
    return [ordered.slice(0, back), ordered.slice(back)];
}

function renderPlan(list) {
    if (list.length === 0) {
        layoutKey = "";
        planEl.className = "plan";
        planEl.innerHTML = `<p class="plan-note">No devices yet. Run <code>seed_db.py</code> to add the demo house.</p>`;
        return;
    }

    const rooms = groupByRoom(list);

    // Only redraw the plan when devices are added, removed or renamed.
    // Otherwise update it in place so changes can fade between states.
    const key = JSON.stringify(list.map((d) => [d.id, d.name, d.type, d.room]));
    if (key !== layoutKey) {
        layoutKey = key;
        const rows = planRows([...rooms]);
        roomOrder = rows.flat().map(([name]) => name);
        planEl.className = rows.length > 1 ? "plan two-rows" : "plan";
        planEl.innerHTML = rows.map((row, r) => `
            <div class="row">
                ${row.map(([name, items]) => roomHtml(name, items, r === rows.length - 1 && rows.length > 1)).join("")}
            </div>`).join("");
    }

    const roomEls = planEl.querySelectorAll(".room");
    roomOrder.forEach((name, i) => updateRoom(roomEls[i], rooms.get(name)));
}

function roomHtml(room, items, front) {
    const lights = items.filter((d) => d.type === "light");
    const thermostat = items.find((d) => d.type === "thermostat");
    const lock = items.find((d) => d.type === "lock");
    const onWalls = items.filter((d) => d.type !== "light" && d !== thermostat);

    // Spread the ceiling lights evenly across the room
    const spot = (i) => `--x:${((i + 0.5) / lights.length) * 100}%;--y:42%`;

    return `
        <div class="room${front ? " front" : ""}${lock ? " has-door" : ""}" style="--grow:${Math.max(items.length, 3)}">
            <span class="window" aria-hidden="true"><span class="shade"></span></span>
            <span class="opening below" aria-hidden="true"></span>
            <span class="opening side" aria-hidden="true"></span>
            ${lock ? `<span class="front-door" aria-hidden="true"><span class="leaf"></span></span>` : ""}
            <div class="floor" aria-hidden="true">
                ${lights.map((d, i) => `<span class="pool" data-pool="${d.id}" style="${spot(i)}"></span>`).join("")}
            </div>
            <h3>${escapeHtml(room)}</h3>
            ${thermostat ? `
                <button type="button" class="fixture thermostat" data-id="${thermostat.id}">
                    <span class="thermostat-value"></span>
                    <span class="t-mark" aria-hidden="true">T</span>
                </button>` : ""}
            ${lights.map((d, i) => `
                <button type="button" class="fixture lamp" data-id="${d.id}" style="${spot(i)}">
                    <span class="lamp-mark" aria-hidden="true"></span>
                    <span class="tag"></span>
                </button>`).join("")}
            ${onWalls.length ? `
                <div class="wall-fixtures">
                    ${onWalls.map((d) => `<button type="button" class="tag wall-tag" data-id="${d.id}"></button>`).join("")}
                </div>` : ""}
        </div>`;
}

function updateRoom(roomEl, items) {
    // The room is lit by its brightest lamp that is switched on
    const lit = items.filter((d) => d.type === "light" && isOn(d));
    roomEl.style.setProperty("--level", lit.length ? Math.max(...lit.map(brightness)) / 100 : 0);

    // Blinds are drawn as slats across the window
    const blinds = items.find((d) => d.type === "blinds");
    roomEl.style.setProperty("--closed", blinds ? (100 - position(blinds)) / 100 : 0);

    const lock = items.find((d) => d.type === "lock");
    roomEl.querySelector(".front-door")?.classList.toggle("is-locked", Boolean(lock && isLocked(lock)));

    for (const d of items) {
        const el = roomEl.querySelector(`[data-id="${d.id}"]`);

        if (el.classList.contains("lamp")) {
            const b = isOn(d) ? Math.max(brightness(d), 8) / 100 : 0;
            roomEl.querySelector(`[data-pool="${d.id}"]`).style.setProperty("--b", b);
            el.classList.toggle("is-on", isOn(d));
            el.querySelector(".tag").innerHTML =
                `${escapeHtml(displayName(d.name, d.room))} <b>${isOn(d) ? brightness(d) + "%" : "off"}</b>`;
            el.setAttribute("aria-label", `${d.name}: ${isOn(d) ? `on, ${brightness(d)}%` : "off"}. Start a command for it.`);
        } else if (el.classList.contains("thermostat")) {
            const t = temperature(d);
            el.querySelector(".thermostat-value").innerHTML = Number.isFinite(t) ? `${t}<small>°C</small>` : "–";
            el.setAttribute("aria-label", `${d.name}: ${Number.isFinite(t) ? `${t} °C` : "no reading"}. Start a command for it.`);
        } else {
            const value = wallValue(d);
            el.innerHTML = `${icon(d)}<span>${escapeHtml(displayName(d.name, d.room))}</span> <b>${escapeHtml(value)}</b>`;
            el.classList.toggle("is-on", isOn(d));
            el.classList.toggle("is-unlocked", d.type === "lock" && !isLocked(d));
            el.setAttribute("aria-label", `${d.name}: ${value}. Start a command for it.`);
        }
    }
}

function wallValue(d) {
    switch (d.type) {
        case "blinds": return blindsText(d);
        case "lock": return isLocked(d) ? "locked" : "unlocked";
        case "speaker": return isOn(d) ? `${volume(d)}%` : "off";
        case "plug": return isOn(d) ? "on" : "off";
        case "thermostat": {
            const t = temperature(d);
            return Number.isFinite(t) ? `${t} °C` : "no reading";
        }
    }
    // Device types the plan doesn't know yet: show their raw state
    const parts = Object.entries(d.state || {}).map(([key, value]) => {
        const shown = typeof value === "boolean" ? (value ? "on" : "off")
            : typeof value === "object" ? JSON.stringify(value) : value;
        return `${key} ${shown}`;
    });
    return parts.join(", ") || "no state";
}

// ---------- summary and suggestions ----------

function listNames(names) {
    return names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
}

function renderSummary(list) {
    const parts = [];
    const ofType = (t) => list.filter((d) => d.type === t);

    const lights = ofType("light");
    const on = lights.filter(isOn).length;
    if (lights.length === 1) {
        parts.push(on ? "The light is on." : "The light is off.");
    } else if (lights.length > 1) {
        parts.push(on === 0 ? "All lights are off."
            : on === lights.length ? `All ${lights.length} lights are on.`
            : `${on} of ${lights.length} lights are on.`);
    }

    for (const lock of ofType("lock")) {
        parts.push(`${lock.name} is ${isLocked(lock) ? "locked" : "unlocked"}.`);
    }

    const running = [...ofType("plug"), ...ofType("speaker")].filter(isOn).map((d) => d.name);
    if (running.length) parts.push(`${listNames(running)} ${running.length > 1 ? "are" : "is"} on.`);

    const temps = ofType("thermostat").filter((t) => Number.isFinite(temperature(t)));
    if (temps.length) {
        parts.push(`Heating is set to ${listNames(temps.map((t) =>
            `${temperature(t)} °C in the ${(t.room ?? t.name).toLowerCase()}`))}.`);
    }

    summaryEl.textContent = parts.join(" ");
}

// Clicking a device writes a command for it; the user still sends it
function draftFor(d) {
    switch (d.type) {
        case "light":
        case "plug":
        case "speaker":
            return `Turn ${isOn(d) ? "off" : "on"} ${refer(d)}`;
        case "thermostat": {
            const t = Math.round(temperature(d) || 21);
            return `Set ${refer(d)} to ${t >= TEMP_MAX ? TEMP_MAX - 1 : clamp(t + 1, TEMP_MIN, TEMP_MAX)} °C`;
        }
        case "blinds":
            return `${position(d) < 50 ? "Open" : "Close"} ${refer(d)}`;
        case "lock":
            return `${isLocked(d) ? "Unlock" : "Lock"} ${refer(d)}`;
    }
    return `What is ${refer(d)} doing?`;
}

// Example commands built from the real devices, one per kind, so they always make sense
function renderSuggestions(list) {
    const commands = [];
    const first = (pred) => list.find(pred);

    const light = first((d) => d.type === "light" && isOn(d)) ?? first((d) => d.type === "light");
    if (light) commands.push(draftFor(light));

    const lock = first((d) => d.type === "lock");
    if (lock) commands.push(draftFor(lock));

    const blinds = first((d) => d.type === "blinds" && position(d) !== 100) ?? first((d) => d.type === "blinds");
    if (blinds) commands.push(draftFor(blinds));

    const speaker = first((d) => d.type === "speaker");
    if (speaker) {
        commands.push(isOn(speaker) ? `Turn ${refer(speaker)} up to ${clamp(volume(speaker) + 20, 0, 100)}%` : draftFor(speaker));
    }

    const thermostat = first((d) => d.type === "thermostat");
    if (thermostat) commands.push(draftFor(thermostat));

    if (list.length) commands.push("Which lights are on?");

    suggestionsEl.innerHTML = commands.slice(0, 5)
        .map((c) => `<button type="button" class="suggestion" data-cmd="${escapeHtml(c)}">${escapeHtml(c)}</button>`)
        .join("");
}

// ---------- events ----------

form.addEventListener("submit", (e) => {
    e.preventDefault();
    send(input.value);
});

suggestionsEl.addEventListener("click", (e) => {
    const button = e.target.closest("button[data-cmd]");
    if (button) send(button.dataset.cmd);
});

planEl.addEventListener("click", (e) => {
    const button = e.target.closest("button[data-id]");
    if (!button) return;
    const device = devices.find((d) => String(d.id) === button.dataset.id);
    if (!device) return;
    input.value = draftFor(device);
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
});

connect();
