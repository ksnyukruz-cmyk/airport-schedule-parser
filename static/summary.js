const waitEl = document.querySelector("#wait");
const errorEl = document.querySelector("#error");
const noteEl = document.querySelector("#note");
const cardsEl = document.querySelector("#cards");
const coverageWrap = document.querySelector("#coverage-wrap");
const coverageEl = document.querySelector("#coverage");
const pivotWrap = document.querySelector("#pivot-wrap");
const headEl = document.querySelector("#head");
const bodyEl = document.querySelector("#body");
const metaEl = document.querySelector("#pivot-meta");
const filtersEl = document.querySelector("#filters");
const queryEl = document.querySelector("#query");

const state = {
  data: null,
  airports: new Set(),
  query: "",
  grouped: [],
};

const numberFormat = new Intl.NumberFormat("ru-RU");
const STATUS = {
  ok: "сезон",
  partial: "не все дни",
  gap: "нет календаря",
  error: "не открылось",
};

queryEl.addEventListener("input", () => {
  state.query = queryEl.value.trim().toLowerCase();
  render();
});

document.querySelector("#csv").addEventListener("click", download);
document.querySelector("#refresh").addEventListener("click", () => load(true));

load(false);

async function load(refresh) {
  waitEl.hidden = false;
  errorEl.hidden = true;
  try {
    const response = await fetch("/api/summary" + (refresh ? "?refresh=true" : ""));
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Сводка не собралась");
    state.data = payload;
    state.airports = new Set();
    waitEl.hidden = true;
    renderCoverage();
    render();
  } catch (error) {
    waitEl.hidden = true;
    errorEl.hidden = false;
    errorEl.textContent = error.message || "Сводка не собралась";
  }
}

function renderCoverage() {
  const data = state.data;
  noteEl.textContent = data.note;
  const flights = data.rows.reduce((sum, row) => sum + row.flights, 0);
  const airlines = new Set(data.rows.map((row) => row.airline_code || row.airline)).size;
  const cities = new Set(data.rows.map((row) => row.city_code || row.city)).size;
  const ready = data.airports.filter((airport) => airport.flights).length;
  cardsEl.hidden = false;
  cardsEl.innerHTML = [
    card("Вылетов", flights),
    card("Авиакомпаний", airlines),
    card("Направлений", cities),
    card("Аэропортов с цифрами", ready + " из 10"),
  ].join("");
  coverageWrap.hidden = false;
  filtersEl.innerHTML = data.airports.map((airport) => {
    const on = state.airports.size === 0 || state.airports.has(airport.code);
    return `<button type="button" data-code="${airport.code}" class="${on ? "is-on" : ""}">${airport.code} ${airport.name}</button>`;
  }).join("");
  coverageEl.innerHTML = data.airports.map((airport) => {
    const period = airport.start ? `${formatDay(airport.start)} – ${formatDay(airport.end)}` : "—";
    const source = airport.source_url
      ? `<a href="${escapeAttr(airport.source_url)}" target="_blank" rel="noreferrer">${escapeText(airport.source)}</a>`
      : escapeText(airport.note || "—");
    const extra = airport.note && airport.source ? `<div class="meta">${escapeText(airport.note)}</div>` : "";
    return `<tr>
      <td><span class="code">${airport.code}</span> ${escapeText(airport.name)}<div class="meta">${STATUS[airport.status] || ""}</div></td>
      <td>${numberFormat.format(airport.passengers)}</td>
      <td>${airport.flights ? numberFormat.format(airport.flights) : "—"}</td>
      <td>${airport.airlines || "—"}</td>
      <td>${airport.cities || "—"}</td>
      <td>${period}</td>
      <td>${source}${extra}</td>
    </tr>`;
  }).join("");
}

filtersEl.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const code = button.dataset.code;
  if (state.airports.has(code) && state.airports.size === 1) {
    state.airports.clear();
  } else if (state.airports.size === 0) {
    state.airports = new Set([code]);
  } else if (state.airports.has(code)) {
    state.airports.delete(code);
  } else {
    state.airports.add(code);
  }
  renderCoverage();
  render();
});

function render() {
  if (!state.data) return;
  const rows = group(filtered(state.data.rows));
  state.grouped = rows;
  const groups = yearGroups(state.data.months);
  pivotWrap.hidden = false;
  const shown = rows.slice(0, 400);
  const weeks = state.data.weeks || [];
  metaEl.textContent = shown.length === rows.length
    ? `${numberFormat.format(rows.length)} строк. Частота — вылеты за год, месяц и неделю.`
    : `Показаны ${numberFormat.format(shown.length)} из ${numberFormat.format(rows.length)}. В CSV попадут все. Частота — вылеты за год, месяц и неделю.`;
  const top = ["АК", "Направление", "АП", "Всего"]
    .map((title) => `<th rowspan="2">${title}</th>`)
    .join("");
  const yearHeads = groups.map((group) => `<th colspan="${group.months.length + 1}">${group.year}</th>`).join("");
  const weekHead = weeks.length ? `<th colspan="${weeks.length}">Недели</th>` : "";
  const monthHeads = groups.map((group) => {
    const yearCell = `<th>год</th>`;
    const months = group.months.map((month) => `<th>${escapeText(month.label.split(" ")[0])}</th>`).join("");
    return yearCell + months;
  }).join("");
  const weekHeads = weeks.map((week) => `<th>${escapeText(week.label)}</th>`).join("");
  headEl.innerHTML = `<tr>${top}${yearHeads}${weekHead}</tr><tr>${monthHeads}${weekHeads}</tr>`;
  const airlineSpan = spans(shown, airlineKey);
  const citySpan = spans(shown, (row) => `${airlineKey(row)}|${cityKey(row)}`);
  bodyEl.innerHTML = shown.map((row, index) => {
    const airlineCell = airlineSpan[index]
      ? `<td class="merge" rowspan="${airlineSpan[index]}">${escapeText(airlineName(row))}</td>`
      : "";
    const cityCell = citySpan[index]
      ? `<td class="merge" rowspan="${citySpan[index]}">${escapeText(cityName(row))}</td>`
      : "";
    const periodCells = groups.map((group) => {
      const year = yearCount(row, group.year);
      const yearCell = `<td class="num">${year ? numberFormat.format(year) : ""}</td>`;
      const months = group.months.map((month) => countCell((row.months || {})[month.key])).join("");
      return yearCell + months;
    }).join("");
    const weekCells = weeks.map((week) => countCell((row.weeks || {})[week.key])).join("");
    const start = airlineSpan[index] ? ` class="group-start"` : "";
    return `<tr${start}>${airlineCell}${cityCell}<td>${escapeText(airportName(row.airport))}</td><td class="num">${numberFormat.format(row.flights)}</td>${periodCells}${weekCells}</tr>`;
  }).join("");
}

function filtered(rows) {
  return rows.filter((row) => {
    if (state.airports.size && !state.airports.has(row.airport)) return false;
    if (!state.query) return true;
    const haystack = `${row.airport} ${row.airline} ${row.airline_code} ${row.city} ${row.city_code}`.toLowerCase();
    return haystack.includes(state.query);
  });
}

function group(rows) {
  const map = new Map();
  for (const row of rows) {
    const key = groupKey(row);
    let item = map.get(key);
    if (!item) {
      item = {
        ...row,
        flights: 0,
        years: {},
        months: {},
        weeks: {},
      };
      map.set(key, item);
    }
    item.flights += row.flights;
    add(item.months, row.months);
    add(item.years, row.years);
    add(item.weeks, row.weeks);
  }
  return [...map.values()].sort((left, right) => {
    const byAirline = airlineName(left).localeCompare(airlineName(right), "ru");
    if (byAirline) return byAirline;
    const byCity = cityName(left).localeCompare(cityName(right), "ru");
    if (byCity) return byCity;
    return airportName(left.airport).localeCompare(airportName(right.airport), "ru");
  });
}

function groupKey(row) {
  return `${row.airline_code || row.airline}|${row.city_code || row.city}|${row.airport}`;
}

function spans(rows, keyFn) {
  const result = new Array(rows.length).fill(0);
  let index = 0;
  while (index < rows.length) {
    const key = keyFn(rows[index]);
    let next = index + 1;
    while (next < rows.length && keyFn(rows[next]) === key) next += 1;
    result[index] = next - index;
    index = next;
  }
  return result;
}

function airlineKey(row) {
  return row.airline_code || row.airline || "";
}

function cityKey(row) {
  return row.city_code || row.city || "";
}

function countCell(value) {
  return `<td class="num">${value ? numberFormat.format(value) : ""}</td>`;
}

function yearGroups(months) {
  const groups = [];
  for (const month of months || []) {
    const year = month.key.slice(0, 4);
    let group = groups[groups.length - 1];
    if (!group || group.year !== year) {
      group = { year, months: [] };
      groups.push(group);
    }
    group.months.push(month);
  }
  return groups;
}

function yearCount(row, year) {
  if (row.years && row.years[year]) return row.years[year];
  let total = 0;
  for (const [key, value] of Object.entries(row.months || {})) {
    if (key.startsWith(year)) total += value;
  }
  return total;
}

function airportName(code) {
  const airport = (state.data.airports || []).find((item) => item.code === code);
  return airport ? `${code} ${airport.name}` : code;
}

function airlineName(row) {
  return row.airline_code ? `${row.airline} ${row.airline_code}` : row.airline;
}

function cityName(row) {
  return row.city_code ? `${row.city} ${row.city_code}` : row.city;
}

function download() {
  if (!state.grouped.length) return;
  const groups = yearGroups(state.data.months);
  const weeks = state.data.weeks || [];
  const headers = ["АК", "Направление", "АП", "Всего"];
  for (const group of groups) {
    headers.push(group.year);
    for (const month of group.months) headers.push(month.label);
  }
  for (const week of weeks) headers.push(week.label);
  const lines = [headers.join(";")];
  let previousAirline = "";
  let previousCity = "";
  for (const row of state.grouped) {
    const airline = airlineKey(row);
    const city = `${airline}|${cityKey(row)}`;
    const cells = [
      airline === previousAirline ? "" : airlineName(row),
      city === previousCity ? "" : cityName(row),
      airportName(row.airport),
      row.flights,
    ];
    previousAirline = airline;
    previousCity = city;
    for (const group of groups) {
      cells.push(yearCount(row, group.year));
      for (const month of group.months) cells.push((row.months || {})[month.key] || 0);
    }
    for (const week of weeks) cells.push((row.weeks || {})[week.key] || 0);
    lines.push(cells.join(";"));
  }
  const blob = new Blob(["\uFEFF" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "top10-flights.csv";
  link.click();
  URL.revokeObjectURL(link.href);
}

function add(target, source) {
  for (const [key, value] of Object.entries(source || {})) target[key] = (target[key] || 0) + value;
}

function card(label, value) {
  const text = typeof value === "number" ? numberFormat.format(value) : value;
  return `<article class="card"><p class="meta">${label}</p><strong>${text}</strong></article>`;
}

function formatDay(value) {
  if (!value) return "";
  const [year, month, day] = value.split("-");
  return `${day}.${month}.${year}`;
}

function escapeText(value) {
  return String(value || "").replace(/[&<>]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[char]));
}

function escapeAttr(value) {
  return escapeText(value).replace(/"/g, "&quot;");
}
