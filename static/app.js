const PRIMARY = ["LED", "DME", "SVO", "VKO"];

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

const primaryEl = document.querySelector("#primary");
const hubsEl = document.querySelector("#hubs");
const airportCountEl = document.querySelector("#airport-count");
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
const analyticsEl = document.querySelector("#analytics");
const analyticsNoteEl = document.querySelector("#analytics-note");
const analyticsCardsEl = document.querySelector("#analytics-cards");
const analyticsSplitEl = document.querySelector("#analytics-split");
const analyticsCountriesEl = document.querySelector("#analytics-countries");
const analyticsCitiesEl = document.querySelector("#analytics-cities");

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
  primaryEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-code]");
    if (!button) return;
    chooseAirport(button.dataset.code);
  });
  hubsEl.addEventListener("change", () => {
    if (hubsEl.value) chooseAirport(hubsEl.value);
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
    ? `${selected.name} · ${selected.city}${selected.country ? ", " + selected.country : ""}`
    : "";
  primaryEl.querySelectorAll("[data-code]").forEach((button) => {
    const on = button.dataset.code === state.airport;
    button.classList.toggle("is-on", on);
    button.setAttribute("aria-selected", on ? "true" : "false");
  });
  const groups = new Map();
  for (const airport of state.airports) {
    if (PRIMARY.includes(airport.code)) continue;
    if (!groups.has(airport.group)) groups.set(airport.group, []);
    groups.get(airport.group).push(airport);
  }
  const options = [`<option value="">Другие хабы</option>`];
  for (const [group, items] of groups) {
    options.push(`<optgroup label="${escapeHtml(group)}">`);
    for (const item of items) {
      options.push(
        `<option value="${escapeHtml(item.code)}">${escapeHtml(item.code)} — ${escapeHtml(item.city)}</option>`
      );
    }
    options.push("</optgroup>");
  }
  hubsEl.innerHTML = options.join("");
  hubsEl.value = PRIMARY.includes(state.airport) ? "" : state.airport;
}

function chooseAirport(code) {
  state.airport = code;
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
  renderAnalytics(board);
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

function renderAnalytics(board) {
  const flights = board.flights || [];
  const destinations = new Map();
  const airlines = new Set();
  for (const flight of flights) {
    const code = (flight.city_code || "").trim().toUpperCase();
    const cityName = (flight.city || "").trim();
    const key = code || cityName.toUpperCase();
    if (!key) continue;
    if (!destinations.has(key)) {
      destinations.set(key, {
        city: titleCase(cityName) || code,
        country: flight.country || "",
        flights: 0,
      });
    }
    const item = destinations.get(key);
    item.flights += 1;
    if (!item.country && flight.country) item.country = flight.country;
    const airline = (flight.airline || flight.airline_code || "").trim();
    if (airline) airlines.add(airline);
  }
  const items = [...destinations.values()];
  const russia = items.filter((item) => item.country === "Россия");
  const foreign = items.filter((item) => item.country && item.country !== "Россия");
  const unknown = items.filter((item) => !item.country);
  const flightCount = (list) => list.reduce((sum, item) => sum + item.flights, 0);
  const live = board.airport && (board.airport.kind === "live" || !board.airport.supports_date);
  analyticsEl.hidden = false;
  analyticsNoteEl.textContent = live
    ? "По рейсам, которые сейчас есть на табло. Одно направление — один город."
    : "По рейсам на выбранную дату. Одно направление — один город.";
  const cards = [
    ["Направлений", items.length, flightWord(flights.length), ""],
    ["По России", russia.length, flightWord(flightCount(russia)), "ru"],
    ["За рубеж", foreign.length, flightWord(flightCount(foreign)), "foreign"],
    ["Авиакомпаний", airlines.size, unknown.length ? `${unknown.length} без страны` : "по этому табло", ""],
  ];
  analyticsCardsEl.innerHTML = cards
    .map(
      ([label, value, sub, tone]) => `<article class="card ${tone}">
        <strong>${value}</strong>
        <span>${label}</span>
        <small>${sub}</small>
      </article>`
    )
    .join("");
  const total = items.length || 1;
  const ruWidth = Math.round((russia.length / total) * 100);
  const foreignWidth = Math.round((foreign.length / total) * 100);
  analyticsSplitEl.hidden = items.length === 0;
  analyticsSplitEl.innerHTML = `<span class="split-ru" style="width:${ruWidth}%"></span>
    <span class="split-foreign" style="width:${foreignWidth}%"></span>
    <span class="split-unknown" style="width:${Math.max(0, 100 - ruWidth - foreignWidth)}%"></span>`;
  const countries = new Map();
  for (const item of items) {
    if (!item.country) continue;
    if (!countries.has(item.country)) countries.set(item.country, { destinations: 0, flights: 0 });
    const row = countries.get(item.country);
    row.destinations += 1;
    row.flights += item.flights;
  }
  const countryRows = [...countries.entries()]
    .sort((a, b) => b[1].destinations - a[1].destinations || b[1].flights - a[1].flights)
    .slice(0, 6);
  const cityRows = [...items].sort((a, b) => b.flights - a.flights || a.city.localeCompare(b.city, "ru")).slice(0, 6);
  analyticsCountriesEl.innerHTML = countryRows.length
    ? barList(
        countryRows.map(([name, row]) => ({
          name,
          value: row.destinations,
          hint: flightWord(row.flights),
        })),
        countryRows[0][1].destinations
      )
    : `<p class="quiet">Страны пока не определились.</p>`;
  analyticsCitiesEl.innerHTML = cityRows.length
    ? barList(
        cityRows.map((item) => ({
          name: item.city,
          value: item.flights,
          hint: item.country || "страна не определена",
        })),
        cityRows[0].flights
      )
    : `<p class="quiet">Городов нет.</p>`;
}

function barList(rows, max) {
  return rows
    .map((row) => {
      const width = max ? Math.max(6, Math.round((row.value / max) * 100)) : 0;
      return `<div class="bar-row" title="${escapeAttr(row.hint)}">
        <span class="bar-name">${escapeHtml(row.name)}</span>
        <span class="bar-track"><span class="bar-fill" style="width:${width}%"></span></span>
        <span class="bar-value">${row.value}</span>
      </div>`;
    })
    .join("");
}

function flightWord(count) {
  return `${count} ${plural(count, "рейс", "рейса", "рейсов")}`;
}

function plural(count, one, few, many) {
  const abs = Math.abs(count) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return many;
  if (last === 1) return one;
  if (last >= 2 && last <= 4) return few;
  return many;
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
  const header = ["Время", "Рейс", "Город", "Код", "Страна", "Авиакомпания", "Терминал", "Выход", "Лента", "Статус", "Борт", "Ожидаемое", "Фактическое"];
  const lines = [header, ...flights.map((flight) => [
    flight.scheduled || "",
    flight.flight,
    flight.city,
    flight.city_code,
    flight.country,
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
    if (document.querySelector("#auto").checked) load(false);
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
