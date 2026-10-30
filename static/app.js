const POPULAR = ["SVO", "DME", "LED", "LHR", "CDG", "FRA", "AMS", "IST", "DXB", "DOH", "SIN", "HND", "ICN", "JFK", "LAX", "MAD"];

const state = {
  airports: [],
  airport: "SVO",
  direction: "departure",
  date: moscowToday(),
  query: "",
  chip: "all",
  board: null,
  timer: null,
  controller: null,
};

const chips = [
  ["all", "Все"],
  ["plan", "По расписанию"],
  ["active", "Сейчас"],
  ["delay", "Задержки"],
  ["cancel", "Отмены"],
  ["done", "Завершённые"],
];

const airportQueryEl = document.querySelector("#airport-query");
const airportResultsEl = document.querySelector("#airport-results");
const airportCountEl = document.querySelector("#airport-count");
const popularEl = document.querySelector("#popular");
const rowsEl = document.querySelector("#rows");
const queryEl = document.querySelector("#query");
const dateEl = document.querySelector("#date");
const noticeEl = document.querySelector("#notice");
const errorEl = document.querySelector("#error");
const statsEl = document.querySelector("#stats");
const chipsEl = document.querySelector("#chips");
const metaEl = document.querySelector("#meta");
const emptyEl = document.querySelector("#empty");
const boardEl = document.querySelector("#board");
const datesEl = document.querySelector("#dates");

readUrl();
renderChips();
bind();
boot();

function bind() {
  document.querySelectorAll("[data-direction]").forEach((button) => {
    button.addEventListener("click", () => {
      state.direction = button.dataset.direction;
      syncDirection();
      load();
    });
  });
  datesEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-shift]");
    if (!button) return;
    state.date = addDays(moscowToday(), Number(button.dataset.shift));
    dateEl.value = state.date;
    syncDates();
    load();
  });
  dateEl.addEventListener("change", () => {
    state.date = dateEl.value || moscowToday();
    syncDates();
    load();
  });
  queryEl.addEventListener("input", () => {
    state.query = queryEl.value.trim();
    renderBoard();
  });
  airportQueryEl.addEventListener("input", renderAirportResults);
  airportQueryEl.addEventListener("focus", renderAirportResults);
  airportResultsEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-code]");
    if (!button) return;
    chooseAirport(button.dataset.code);
  });
  popularEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-code]");
    if (!button) return;
    chooseAirport(button.dataset.code);
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".picker")) airportResultsEl.hidden = true;
  });
  document.querySelector("#refresh").addEventListener("click", () => load(true));
  document.querySelector("#csv").addEventListener("click", downloadCsv);
  document.querySelector("#auto").addEventListener("change", (event) => {
    if (event.target.checked) scheduleRefresh();
    else clearInterval(state.timer);
  });
}

async function boot() {
  dateEl.value = state.date;
  syncDirection();
  syncDates();
  try {
    const response = await fetch("/api/airports");
    const payload = await response.json();
    state.airports = payload.airports || [];
    if (!state.airports.some((item) => item.code === state.airport) && state.airports[0]) {
      state.airport = state.airports[0].code;
    }
  } catch (error) {
    showError("Не удалось загрузить список аэропортов.");
  }
  renderPicker();
  load();
  scheduleRefresh();
}

function renderPicker() {
  const selected = currentAirport();
  airportCountEl.textContent = selected
    ? `${selected.name} · ${selected.city}${selected.country ? ", " + selected.country : ""} · ${state.airports.length} крупных аэропортов`
    : `${state.airports.length} крупных аэропортов`;
  popularEl.innerHTML = POPULAR.filter((code) => state.airports.some((item) => item.code === code))
    .map(
      (code) =>
        `<button type="button" data-code="${code}" class="${code === state.airport ? "is-on" : ""}">${code}</button>`
    )
    .join("");
}

function renderAirportResults() {
  const query = airportQueryEl.value.trim().toLowerCase();
  if (!query) {
    airportResultsEl.hidden = true;
    airportResultsEl.innerHTML = "";
    return;
  }
  const matches = state.airports
    .filter((item) =>
      [item.code, item.name, item.city, item.country, item.keywords].join(" ").toLowerCase().includes(query)
    )
    .slice(0, 12);
  airportResultsEl.hidden = matches.length === 0;
  airportResultsEl.innerHTML = matches
    .map(
      (item) => `<button type="button" data-code="${item.code}">
        <span class="code">${escapeHtml(item.code)}</span>
        <span>${escapeHtml(item.name)}</span>
        <span class="city">${escapeHtml([item.city, item.country].filter(Boolean).join(", "))}</span>
      </button>`
    )
    .join("");
}

function chooseAirport(code) {
  state.airport = code;
  airportQueryEl.value = "";
  airportResultsEl.hidden = true;
  renderPicker();
  load();
}

function renderChips() {
  chipsEl.innerHTML = chips
    .map(
      ([id, label]) =>
        `<button type="button" data-chip="${id}" class="${id === state.chip ? "is-on" : ""}">${label}</button>`
    )
    .join("");
  chipsEl.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      state.chip = button.dataset.chip;
      renderChips();
      renderBoard();
    });
  });
}

async function load(refresh = false) {
  const airport = currentAirport();
  datesEl.hidden = airport ? !airport.supports_date : false;
  writeUrl();
  if (state.controller) state.controller.abort();
  state.controller = new AbortController();
  boardEl.classList.add("is-loading");
  errorEl.hidden = true;
  metaEl.textContent = "Загружаем табло…";
  const params = new URLSearchParams({
    airport: state.airport,
    direction: state.direction,
    date: state.date,
  });
  if (refresh) params.set("refresh", "true");
  try {
    const response = await fetch(`/api/schedule?${params}`, { signal: state.controller.signal });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Источник табло не ответил");
    }
    state.board = payload;
    renderBoard();
  } catch (error) {
    if (error.name === "AbortError") return;
    showError(error.message || "Не удалось получить расписание");
    metaEl.textContent = "";
  } finally {
    boardEl.classList.remove("is-loading");
  }
}

function renderBoard() {
  const board = state.board;
  if (!board) return;
  document.querySelector("#city-head").textContent = board.direction === "arrival" ? "Откуда" : "Куда";
  document.querySelector("#gate-head").textContent = board.direction === "arrival" ? "Лента" : "Выход";
  const visible = filtered(board.flights || []);
  renderStats(board.flights || [], visible);
  noticeEl.hidden = !board.notice && !board.warning;
  noticeEl.textContent = [board.warning, board.notice].filter(Boolean).join(" ");
  const when = board.fetched_at ? formatClock(board.fetched_at) : "";
  metaEl.innerHTML = `${visible.length} из ${(board.flights || []).length} · обновлено в ${when} · <a href="${escapeAttr(board.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(board.source_name)}</a>`;
  rowsEl.innerHTML = visible.map(renderRow).join("");
  emptyEl.textContent = board.airport && board.airport.kind === "live"
    ? "Сейчас рядом с аэропортом таких рейсов не видно."
    : "На эту дату рейсов нет.";
  const nothing = visible.length === 0;
  emptyEl.hidden = !nothing;
  boardEl.hidden = nothing;
}

function renderRow(flight) {
  const gate = state.direction === "arrival" ? flight.belt : flight.gate;
  const shares = (flight.codeshare || []).length
    ? `<span class="sub">${escapeHtml(flight.codeshare.join(", "))}</span>`
    : "";
  const estimate = flight.estimated
    ? `<span class="sub">ожид. ${formatClock(flight.estimated)}${delayLabel(flight)}</span>`
    : delayLabel(flight)
      ? `<span class="sub">${delayLabel(flight)}</span>`
      : "";
  const actual = flight.actual ? `<span class="sub">факт ${formatClock(flight.actual)}</span>` : "";
  const clock = flight.scheduled ? formatClock(flight.scheduled) : escapeHtml(flight.when_label || "—");
  const day = flight.scheduled ? `<small>${formatDay(flight.scheduled)}</small>` : "";
  return `<tr>
    <td><div class="when">${clock}${day}</div>${estimate}${actual}</td>
    <td><div class="flight-no">${escapeHtml(flight.flight || "—")}</div>${shares}</td>
    <td>${escapeHtml(titleCase(flight.city) || "—")}<span class="sub city-code">${escapeHtml(flight.city_code || "")}</span></td>
    <td>${escapeHtml(flight.airline || flight.airline_code || "—")}</td>
    <td>${escapeHtml(flight.terminal || "—")}</td>
    <td>${escapeHtml(gate || "—")}</td>
    <td><span class="pill ${tone(flight.status)}">${escapeHtml(flight.status || "По расписанию")}</span></td>
    <td>${escapeHtml(flight.aircraft || "—")}</td>
  </tr>`;
}

function renderStats(all, visible) {
  const count = (list, name) => list.filter((flight) => kind(flight.status) === name).length;
  statsEl.innerHTML = [
    ["На экране", visible.length],
    ["По расписанию", count(all, "plan")],
    ["Сейчас", count(all, "active")],
    ["Задержки", count(all, "delay")],
    ["Отмены", count(all, "cancel")],
  ]
    .map(([label, value]) => `<span>${label}: <strong>${value}</strong></span>`)
    .join("");
}

function filtered(flights) {
  const query = state.query.toLowerCase();
  return flights.filter((flight) => {
    if (state.chip !== "all" && kind(flight.status) !== state.chip) return false;
    if (!query) return true;
    const haystack = [flight.flight, flight.airline, flight.airline_code, flight.city, flight.city_code, flight.status, ...(flight.codeshare || [])]
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });
}

function kind(status) {
  const text = (status || "").toLowerCase();
  if (text.includes("отмен")) return "cancel";
  if (text.includes("задерж")) return "delay";
  if (/вылет|отправ|призем|прибыл|закончен|выдача|багаж/.test(text)) return "done";
  if (/сниж|набир|земле|рядом|посад|регист|ожид|пути/.test(text)) return "active";
  return "plan";
}

function tone(status) {
  const name = kind(status);
  if (name === "cancel") return "bad";
  if (name === "delay") return "delay";
  if (name === "active") return "info";
  if (name === "done") return "done";
  return "";
}

function delayLabel(flight) {
  if (!flight.scheduled || !flight.estimated) return "";
  const minutes = Math.round((new Date(flight.estimated) - new Date(flight.scheduled)) / 60000);
  if (!Number.isFinite(minutes) || Math.abs(minutes) < 1) return "";
  const sign = minutes > 0 ? "+" : "−";
  return `<span class="late">${sign}${Math.abs(minutes)} мин</span>`;
}

function downloadCsv() {
  const flights = state.board ? filtered(state.board.flights || []) : [];
  const header = ["Время", "Рейс", "Город", "Код", "Авиакомпания", "Терминал", "Выход", "Лента", "Статус", "Борт", "Ожидаемое", "Фактическое"];
  const lines = [header, ...flights.map((flight) => [
    flight.scheduled || "",
    flight.flight,
    flight.city,
    flight.city_code,
    flight.airline,
    flight.terminal,
    flight.gate,
    flight.belt,
    flight.status,
    flight.aircraft,
    flight.estimated || "",
    flight.actual || "",
  ])];
  const csv = lines.map((line) => line.map(csvCell).join(";")).join("\r\n");
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${state.airport}-${state.direction}-${state.date}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

function csvCell(value) {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

function scheduleRefresh() {
  clearInterval(state.timer);
  state.timer = setInterval(() => {
    if (document.querySelector("#auto").checked) load(true);
  }, 60000);
}

function currentAirport() {
  return state.airports.find((item) => item.code === state.airport);
}

function syncDates() {
  const today = moscowToday();
  datesEl.querySelectorAll("[data-shift]").forEach((button) => {
    button.classList.toggle("is-on", addDays(today, Number(button.dataset.shift)) === state.date);
  });
}

function syncDirection() {
  document.querySelectorAll("[data-direction]").forEach((button) => {
    button.classList.toggle("is-on", button.dataset.direction === state.direction);
  });
}

function readUrl() {
  const params = new URLSearchParams(location.search);
  const airport = (params.get("airport") || "").toUpperCase();
  if (/^[A-Z]{3}$/.test(airport)) state.airport = airport;
  const direction = params.get("direction");
  if (direction === "arrival" || direction === "departure") state.direction = direction;
  const day = params.get("date");
  if (/^\d{4}-\d{2}-\d{2}$/.test(day || "")) state.date = day;
}

function writeUrl() {
  const params = new URLSearchParams({
    airport: state.airport,
    direction: state.direction,
    date: state.date,
  });
  history.replaceState(null, "", `/?${params}`);
}

function showError(message) {
  errorEl.hidden = false;
  errorEl.textContent = message;
}

function moscowToday() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Moscow",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function addDays(iso, days) {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function formatClock(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Moscow",
  }).format(date);
}

function formatDay(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    timeZone: "Europe/Moscow",
  }).format(date);
}

function titleCase(value) {
  const text = (value || "").trim();
  if (!text || text !== text.toUpperCase()) return text;
  return text.toLowerCase().replace(/(^|[\s-])([a-zа-яё])/gi, (_, sep, char) => sep + char.toUpperCase());
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("'", "&#39;");
}
