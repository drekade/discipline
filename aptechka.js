(function() {
  var SB = "https://btgtgcwbrrnfbctchata.supabase.co";
  var SK = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ0Z3RnY3dicnJuZmJjdGNoYXRhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY3MTQ2OTgsImV4cCI6MjA5MjI5MDY5OH0.lyEWFcmsL3GIm0FrEZdGkK2uRSx26cNiBGFvCVsjdsY";
  var SH = { "apikey": SK, "Authorization": "Bearer " + SK, "Content-Type": "application/json", "Prefer": "return=representation" };
  var TABLE = "med_log";
  var TEMP_THRESHOLD = 38.0;

  var state = { entries: [], formType: "Лекарство", formDay: 0, screen: "aptechka", syncError: null, loaded: false, historyLimit: 5 };

  var FAMILIES = {
    ibuprofen: { label: "Нурофен / ибупрофен", keywords: ["нурофен","ибупрофен","ибуфен","адвил","некст"] },
    paracetamol: { label: "Парацетамол / аналоги", keywords: ["парацетамол","панадол","panadol","эффералган","цефекон","калпол","тайленол"] }
  };
  var SAME_INTERVAL_H = 6;
  var CROSS_INTERVAL_H = 1;

  var DOSAGE_GUIDE = {
    ibuprofen: {
      label: "Ибупрофен (Нурофен и аналоги)",
      mgPerKgLow: 5, mgPerKgHigh: 10,
      maxTimesPerDay: 4,
      concentrations: [
        { label: "Таблетки 200мг", type: "tablet", mg: 200 },
        { label: "Сусп. 100мг/5мл", type: "syrup", mg: 100 },
        { label: "Капли 40мг/мл (200мг/5мл)", type: "syrup", mg: 200 },
        { label: "Своя (укажи тип и дозу)", type: "custom", mg: null }
      ]
    },
    paracetamol: {
      label: "Парацетамол (Панадол и аналоги)",
      mgPerKgLow: 10, mgPerKgHigh: 15,
      maxTimesPerDay: 4,
      concentrations: [
        { label: "Таблетки 500мг", type: "tablet", mg: 500 },
        { label: "Сусп. Панадол 120мг/5мл", type: "syrup", mg: 120 },
        { label: "Сусп. Эффералган 150мг/5мл", type: "syrup", mg: 150 },
        { label: "Своя (укажи тип и дозу)", type: "custom", mg: null }
      ]
    }
  };
  var guideCustomType = { ibuprofen: "syrup", paracetamol: "syrup" };

  var GROWTH_METRICS = [
    { key: "Рост", label: "Рост", unit: "см", placeholder: "см" },
    { key: "Вес", label: "Вес", unit: "кг", placeholder: "кг" },
    { key: "ДлинаСтопы", label: "Длина стопы, см", unit: "см", placeholder: "напр. 15,5", decimal: true },
    { key: "НомерОбуви", label: "Размер обуви", unit: "", placeholder: "напр. 24", decimal: true },
    { key: "Одежда", label: "Размер одежды", unit: "", placeholder: "напр. 92" }
  ];

  // Geox children's EU sizes 15–44, measured heel to toe in centimeters.
  var EU_FOOT_LENGTHS = [
    9, 9.7, 10.4, 11, 11.7, 12.4, 13, 13.7, 14.4, 15, 15.7, 16.4, 17, 17.7, 18.4,
    19, 19.7, 20.4, 21, 21.7, 22.4, 23, 23.7, 24.4, 25, 25.7, 26.4, 27, 27.7, 28.4
  ];

  function connectShoeSizeSuggestion() {
    var foot = document.getElementById("mt-growth-input-ДлинаСтопы");
    var shoe = document.getElementById("mt-growth-input-НомерОбуви");
    var hint = document.getElementById("mt-shoe-size-hint");

    shoe.addEventListener("input", function() { delete shoe.dataset.suggested; });
    foot.addEventListener("input", function() {
      var value = foot.value.trim();
      var cm = /^\d+(?:[.,]\d+)?$/.test(value) ? Number(value.replace(",", ".")) : NaN;
      var suggestion = "";
      if (cm >= EU_FOOT_LENGTHS[0] && cm <= EU_FOOT_LENGTHS[EU_FOOT_LENGTHS.length - 1]) {
        var nearest = 0;
        EU_FOOT_LENGTHS.forEach(function(length, i) {
          if (Math.abs(length - cm) < Math.abs(EU_FOOT_LENGTHS[nearest] - cm)) nearest = i;
        });
        suggestion = String(15 + nearest);
      }

      if (!shoe.value.trim() || shoe.dataset.suggested === shoe.value) {
        shoe.value = suggestion;
        delete shoe.dataset.suggested;
        if (suggestion) shoe.dataset.suggested = suggestion;
      }
      hint.textContent = suggestion ? "Ориентир по сетке Geox: ≈ " + suggestion + " EU" :
        "Ориентир EU по длине стопы от 9 до 28,4 см";
    });
  }

  function formatFraction(n) {
    if (isNaN(n) || n < 0) return "-";
    var rounded = Math.round(n * 4) / 4;
    var whole = Math.floor(rounded + 0.001);
    var frac = rounded - whole;
    var fracStr = "";
    if (Math.abs(frac - 0.25) < 0.01) fracStr = "\u00BC";
    else if (Math.abs(frac - 0.5) < 0.01) fracStr = "\u00BD";
    else if (Math.abs(frac - 0.75) < 0.01) fracStr = "\u00BE";
    var result = "";
    if (whole > 0) result += whole;
    if (fracStr) result += (whole > 0 ? " " : "") + fracStr;
    if (!result) result = "0";
    return result;
  }

  function detectFamily(name) {
    var n = (name || "").toLowerCase();
    for (var key in FAMILIES) {
      var kws = FAMILIES[key].keywords;
      for (var i = 0; i < kws.length; i++) {
        if (n.indexOf(kws[i]) !== -1) return key;
      }
    }
    return null;
  }

  function detectInterval(name) {
    return detectFamily(name) ? SAME_INTERVAL_H : null;
  }

  function pad2(n) { return String(n).padStart(2, "0"); }

  function fmtTime(iso) {
    var d = new Date(iso);
    var hh = pad2(d.getHours());
    var mm = pad2(d.getMinutes());
    var day = d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
    var isToday = d.toDateString() === new Date().toDateString();
    return (isToday ? "" : day + " ") + hh + ":" + mm;
  }

  function fmtDuration(ms) {
    var neg = ms < 0;
    ms = Math.abs(ms);
    var totalMin = Math.round(ms / 60000);
    var h = Math.floor(totalMin / 60);
    var m = totalMin % 60;
    var str = (h > 0 ? h + "ч " : "") + m + "м";
    return neg ? "просрочено на " + str : str;
  }

  function fmtHours(h) {
    if (h === null || h === undefined) return "-";
    var hh = Math.floor(h);
    var mm = Math.round((h - hh) * 60);
    if (mm === 60) { hh += 1; mm = 0; }
    return (hh > 0 ? hh + "ч " : "") + mm + "м";
  }

  function nowTimeValue() {
    var d = new Date();
    return pad2(d.getHours()) + ":" + pad2(d.getMinutes());
  }

  function escapeHtml(s) {
    if (s === undefined || s === null) return "";
    return String(s).replace(/[&<>"']/g, function(c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  async function dbList() {
    var res = await fetch(SB + "/rest/v1/" + TABLE + "?order=time.desc&limit=300", { headers: SH });
    if (!res.ok) throw new Error("list failed: " + res.status);
    return res.json();
  }

  async function dbInsert(entry) {
    var res = await fetch(SB + "/rest/v1/" + TABLE, {
      method: "POST", headers: SH, body: JSON.stringify(entry)
    });
    if (!res.ok) throw new Error("insert failed: " + res.status);
    return res.json();
  }

  async function dbDelete(id) {
    var res = await fetch(SB + "/rest/v1/" + TABLE + "?id=eq." + id, {
      method: "DELETE", headers: SH
    });
    if (!res.ok) throw new Error("delete failed: " + res.status);
  }

  async function refresh() {
    try {
      var rows = await dbList();
      state.entries = rows;
      state.syncError = null;
      state.loaded = true;
    } catch (e) {
      state.syncError = "Нет связи с базой — показаны последние загруженные данные";
      state.loaded = true;
    }
    renderShellIfNeeded();
    renderTopBar();
    renderAptechkaData();
    renderRepeatChips();
    renderGrowthData();
  }

  function lastOf(entries, predicate) {
    var filtered = entries.filter(predicate);
    if (filtered.length === 0) return null;
    return filtered.reduce(function(a, b) { return new Date(a.time) > new Date(b.time) ? a : b; });
  }

  // ---------- Аптечка: расчёты ----------

  function renderAntipyreticBoard() {
    var entries = state.entries.filter(function(e) { return e.type === "Лекарство"; });
    var now = new Date();
    var html = "";
    var lastByFamily = {};
    for (var key in FAMILIES) {
      lastByFamily[key] = lastOf(entries, function(e) { return detectFamily(e.name) === key; });
    }
    for (var famKey in FAMILIES) {
      var own = lastByFamily[famKey];
      var otherKey = famKey === "ibuprofen" ? "paracetamol" : "ibuprofen";
      var other = lastByFamily[otherKey];
      var constraints = [];
      if (own) constraints.push(new Date(own.time).getTime() + SAME_INTERVAL_H * 3600000);
      if (other) constraints.push(new Date(other.time).getTime() + CROSS_INTERVAL_H * 3600000);
      var chipClass = "ok", chipText = "можно сейчас";
      if (constraints.length > 0) {
        var nextAllowed = Math.max.apply(null, constraints);
        var remaining = nextAllowed - now;
        if (remaining > 0) { chipClass = "wait"; chipText = "через " + fmtDuration(remaining); }
      }
      var count24 = entries.filter(function(e) {
        return detectFamily(e.name) === famKey && (now - new Date(e.time)) < 24 * 3600000;
      }).length;
      var maxPerDay = Math.floor(24 / SAME_INTERVAL_H);
      var warnLine = "";
      if (count24 >= maxPerDay) {
        chipClass = chipClass === "wait" ? "wait" : "warn";
        warnLine = '<div class="mt-status-sub" style="color:var(--red);">' + count24 + ' раз за 24ч — обычно максимум ' + maxPerDay + '</div>';
      }
      var subLine = own
        ? "последний: " + escapeHtml(own.name) + (own.dose ? " · " + escapeHtml(own.dose) : "") + " · " + fmtTime(own.time)
        : "ещё не давали";
      html += '<div class="mt-status-row">' +
        '<div>' +
          '<div class="mt-status-name">' + FAMILIES[famKey].label + '</div>' +
          '<div class="mt-status-sub">' + subLine + '</div>' +
          warnLine +
        '</div>' +
        '<div class="mt-chip ' + chipClass + '">' + chipText + '</div>' +
      '</div>';
    }
    return html;
  }

  function renderOtherBoard() {
    var entries = state.entries.filter(function(e) {
      return (e.type === "Ингаляция" || e.type === "Другое") && e.interval_h && !detectFamily(e.name);
    });
    var groups = {};
    entries.forEach(function(e) {
      var key = e.name.trim().toLowerCase();
      if (!groups[key] || new Date(e.time) > new Date(groups[key].last.time)) {
        groups[key] = { last: e, name: e.name };
      }
    });
    var keys = Object.keys(groups);
    if (keys.length === 0) return '<div class="mt-empty">Нет записей с интервалом повтора</div>';
    var now = new Date();
    var html = "";
    keys.forEach(function(key) {
      var g = groups[key];
      var last = g.last;
      var nextTime = new Date(new Date(last.time).getTime() + last.interval_h * 3600000);
      var remaining = nextTime - now;
      var chipClass = remaining > 0 ? "wait" : "ok";
      var chipText = remaining > 0 ? "через " + fmtDuration(remaining) : "можно сейчас";
      html += '<div class="mt-status-row">' +
        '<div>' +
          '<div class="mt-status-name">' + escapeHtml(g.name) + '</div>' +
          '<div class="mt-status-sub">последний: ' + fmtTime(last.time) + (last.dose ? " · " + escapeHtml(last.dose) : "") + '</div>' +
        '</div>' +
        '<div class="mt-chip ' + chipClass + '">' + chipText + '</div>' +
      '</div>';
    });
    return html;
  }

  function renderTempList() {
    var temps = state.entries.filter(function(e) { return e.type === "Температура"; })
      .sort(function(a, b) { return new Date(b.time) - new Date(a.time); })
      .slice(0, 6);
    if (temps.length === 0) return '<div class="mt-empty">Пока нет замеров</div>';
    var html = '<div class="mt-temp-list">';
    temps.forEach(function(t, i) {
      var arrow = "";
      if (i < temps.length - 1) {
        var diff = parseFloat(t.dose) - parseFloat(temps[i + 1].dose);
        if (diff > 0.05) arrow = ' <span style="color:var(--red);">&#8593;</span>';
        else if (diff < -0.05) arrow = ' <span style="color:var(--green);">&#8595;</span>';
      }
      html += '<div class="mt-temp-item"><span>' + escapeHtml(t.dose) + '&deg;' + arrow + '</span><span class="mt-history-time">' + fmtTime(t.time) + '</span></div>';
    });
    html += '</div>';
    return html;
  }

  function renderTempFrequency() {
    var temps = state.entries.filter(function(e) { return e.type === "Температура"; })
      .slice().sort(function(a, b) { return new Date(a.time) - new Date(b.time); });
    if (temps.length === 0) return "";

    var now = new Date();
    var spikes = temps.filter(function(t) { return parseFloat(t.dose) >= TEMP_THRESHOLD; });
    var statsHtml = "";

    if (spikes.length === 0) {
      statsHtml = '<div class="mt-freq-stats">Подъёмов ≥' + TEMP_THRESHOLD + '° пока не зафиксировано</div>';
    } else {
      var count24 = spikes.filter(function(s) { return (now - new Date(s.time)) < 24 * 3600000; }).length;
      var gaps = [];
      for (var i = 1; i < spikes.length; i++) {
        gaps.push((new Date(spikes[i].time) - new Date(spikes[i - 1].time)) / 3600000);
      }
      var avgGap = gaps.length ? (gaps.reduce(function(a, b) { return a + b; }, 0) / gaps.length) : null;
      var last = spikes[spikes.length - 1];
      var sinceLast = now - new Date(last.time);

      statsHtml = '<div class="mt-freq-stats">' +
        'Подъёмов ≥' + TEMP_THRESHOLD + '° за 24ч: <b>' + count24 + '</b><br/>' +
        (avgGap !== null ? 'Средний интервал между подъёмами: <b>' + fmtHours(avgGap) + '</b><br/>' : '') +
        'С последнего подъёма (' + fmtTime(last.time) + '): <b>' + fmtDuration(sinceLast) + '</b>' +
        '</div>';
    }

    var recent = temps.slice(-12);
    var min = 35, max = 40;
    var w = 440, h = 70, pad = 6;
    var stepX = recent.length > 1 ? (w - pad * 2) / (recent.length - 1) : 0;
    var pts = recent.map(function(t, i) {
      var val = parseFloat(t.dose);
      var clamped = Math.max(min, Math.min(max, val));
      var x = pad + i * stepX;
      var y = h - pad - ((clamped - min) / (max - min)) * (h - pad * 2);
      return { x: x, y: y, val: val };
    });
    var thresholdY = h - pad - ((TEMP_THRESHOLD - min) / (max - min)) * (h - pad * 2);
    var polyPoints = pts.map(function(p) { return p.x + "," + p.y; }).join(" ");
    var circles = pts.map(function(p) {
      var color = p.val >= TEMP_THRESHOLD ? "var(--red)" : "var(--purple)";
      return '<circle cx="' + p.x + '" cy="' + p.y + '" r="3" fill="' + color + '" />';
    }).join("");

    var svg = recent.length > 1
      ? '<svg class="mt-sparkline" viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg">' +
          '<line x1="' + pad + '" y1="' + thresholdY + '" x2="' + (w - pad) + '" y2="' + thresholdY + '" stroke="var(--orange)" stroke-width="1" stroke-dasharray="4,3" />' +
          '<polyline points="' + polyPoints + '" fill="none" stroke="var(--purple)" stroke-width="2" />' +
          circles +
        '</svg>'
      : "";

    return statsHtml + svg;
  }

  function canRepeat(entry) {
    return ["Лекарство", "Ингаляция", "Другое", "Температура"].includes(entry.type);
  }

  function repeatButton(entry, text, extra) {
    return '<button type="button" class="' + (extra || "mt-refresh") + '" data-repeat-id="' +
      escapeHtml(entry.id) + '" onclick="mtRepeat(this.dataset.repeatId)">' + text + '</button>';
  }

  function renderHistory() {
    var wrap = document.getElementById("mt-history");
    var entries = state.entries.filter(function(e) { return e.type !== "Замер" && e.type !== "Курс"; });
    var html = "<h2>История</h2>";
    if (!entries.length) html += '<div class="mt-empty">Записей ещё нет</div>';
    entries.slice(0, state.historyLimit).forEach(function(e) {
      var label = e.type === "Температура" ? escapeHtml(e.dose) + " °C" :
        escapeHtml(e.name) + (e.dose ? " · " + escapeHtml(e.dose) : "");
      html += '<div class="mt-history-item"><div class="mt-history-left">' +
        '<div>' + label + ' <span class="mt-history-time">· ' + escapeHtml(e.type) + '</span></div>' +
        (e.note ? '<div class="mt-status-sub">' + escapeHtml(e.note) + '</div>' : '') +
        '<div class="mt-history-time">' + fmtTime(e.time) + '</div></div>' +
        '<div class="mt-history-actions">' +
        (canRepeat(e) ? repeatButton(e, "Повторить") : "") +
        '<button class="mt-del" aria-label="Удалить запись" data-id="' + escapeHtml(e.id) +
        '" onclick="mtDelete(this.dataset.id)">&times;</button></div></div>';
    });
    html += '<div class="mt-history-tools">' +
      (entries.length > state.historyLimit ? '<button class="mt-refresh" onclick="mtMoreHistory()">Показать ещё</button>' : '') +
      (state.historyLimit > 5 ? '<button class="mt-refresh" onclick="mtLessHistory()">Свернуть</button>' : '') + '</div>';
    wrap.innerHTML = html;
  }

  window.mtMoreHistory = function() { state.historyLimit += 15; renderHistory(); };
  window.mtLessHistory = function() {
    state.historyLimit = 5;
    renderHistory();
    document.getElementById("mt-history").scrollIntoView({ block: "nearest" });
  };

  function localDateValue(date) {
    return date.getFullYear() + "-" + pad2(date.getMonth() + 1) + "-" + pad2(date.getDate());
  }

  function courseDetails(entry) {
    try {
      return JSON.parse(entry.note || "{}") || {};
    } catch (e) {
      return {};
    }
  }

  function formatCourseDate(value) {
    return value.split("-").reverse().join(".");
  }

  function renderCourses() {
    var wrap = document.getElementById("mt-courses");
    var expanded = Boolean(wrap.querySelector("details[open]"));
    var today = localDateValue(new Date());
    var active = [], completed = [];
    state.entries.filter(function(e) { return e.type === "Курс"; }).forEach(function(e) {
      var course = courseDetails(e);
      var ended = course.end && course.end < today;
      var period = [course.start, course.end].filter(Boolean).map(formatCourseDate).join(" — ");
      var row = '<div class="mt-history-item"><div class="mt-history-left"><strong>' + escapeHtml(e.name) +
        '</strong>' + (e.dose ? ' · ' + escapeHtml(e.dose) : '') +
        '<div class="mt-history-time">' + escapeHtml(period) + '</div>' +
        (course.instructions ? '<div class="mt-status-sub">' + escapeHtml(course.instructions) + '</div>' : '') +
        '</div><div class="mt-history-actions">' +
        (ended || course.start > today ? '' : repeatButton(e, "Записать приём")) +
        '<button class="mt-del" aria-label="Удалить курс" data-id="' + escapeHtml(e.id) +
        '" onclick="mtDeleteCourse(this.dataset.id)">&times;</button></div></div>';
      (ended ? completed : active).push(row);
    });
    wrap.innerHTML = '<h2>Курсы лекарств</h2>' + (active.join("") ||
      '<div class="mt-empty">Текущих и запланированных курсов нет</div>') +
      (completed.length ? '<details class="mt-course-list"' + (expanded ? ' open' : '') +
        '><summary>Завершённые курсы (' + completed.length + ')</summary>' +
        completed.join("") + '</details>' : '');
  }

  window.mtDeleteCourse = function(id) {
    if (confirm("Удалить план курса? Записи о приёмах останутся в истории.")) mtDelete(id);
  };

  // ---------- Лила: расчёты ----------

  function renderGrowthHistory() {
    var entries = state.entries.filter(function(e) { return e.type === "Замер"; }).slice(0, 25);
    if (entries.length === 0) return '<div class="mt-empty">Записей ещё нет</div>';
    var html = "";
    entries.forEach(function(e) {
      var metric = GROWTH_METRICS.find(function(m) { return m.key === e.name; });
      var label = e.name === "Нога" ? "Размер ноги (старая запись)" :
        metric ? metric.label : e.name;
      html += '<div class="mt-history-item">' +
        '<div class="mt-history-left">' +
          '<div>' + escapeHtml(label) + ': ' + escapeHtml(e.dose) + '</div>' +
          '<div class="mt-history-time">' + fmtTime(e.time) + '</div>' +
        '</div>' +
        '<button class="mt-del" onclick="mtDelete(\'' + e.id + '\')">&times;</button>' +
      '</div>';
    });
    return html;
  }

  function renderGrowthLast() {
    GROWTH_METRICS.forEach(function(m) {
      var el = document.getElementById("mt-growth-last-" + m.key);
      if (!el) return;
      var entries = state.entries.filter(function(e) { return e.type === "Замер" && e.name === m.key; })
        .sort(function(a, b) { return new Date(b.time) - new Date(a.time); });
      if (entries.length === 0) {
        el.textContent = "ещё нет данных";
        return;
      }
      var last = entries[0];
      var deltaStr = "";
      if (entries.length > 1) {
        var prevVal = parseFloat(entries[1].dose);
        var lastVal = parseFloat(last.dose);
        if (!isNaN(prevVal) && !isNaN(lastVal) && lastVal !== prevVal) {
          deltaStr = lastVal > prevVal ? " (+" + (lastVal - prevVal).toFixed(1) + ")" : " (" + (lastVal - prevVal).toFixed(1) + ")";
        }
      }
      el.textContent = last.dose + (m.unit ? " " + m.unit : "") + deltaStr + " · " + fmtTime(last.time);
    });
  }

  function renderGrowthData() {
    renderGrowthLast();
    var histEl = document.getElementById("mt-growth-history");
    if (histEl) histEl.innerHTML = renderGrowthHistory();
  }

  window.mtAddGrowth = async function(key) {
    var input = document.getElementById("mt-growth-input-" + key);
    var rawValue = input ? input.value : "";
    var value = rawValue.trim();
    if (!value) { alert("Введи значение"); return; }
    var metric = GROWTH_METRICS.find(function(m) { return m.key === key; });
    if (metric && metric.decimal) {
      if (!/^\d+(?:[.,]\d+)?$/.test(value) || Number(value.replace(",", ".")) <= 0) {
        alert("Введи число больше нуля");
        return;
      }
      value = value.replace(",", ".");
    }
    try {
      await dbInsert({ type: "Замер", name: key, dose: value, time: new Date().toISOString() });
      if (input.value === rawValue) {
        input.value = "";
        delete input.dataset.suggested;
      }
      await refresh();
    } catch (e) {
      alert("Не удалось сохранить — проверь интернет.");
    }
  };

  // ---------- Оболочка и навигация ----------

  var shellBuilt = false;
  var growthOnly = document.body.dataset.screen === "growth";

  function renderTopBar() {
    document.getElementById("mt-date").textContent =
      new Date().toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
    var syncEl = document.getElementById("mt-sync");
    if (syncEl) {
      syncEl.innerHTML = state.syncError
        ? '<div class="mt-sync-note err">' + state.syncError + '</div>'
        : '<div class="mt-sync-note">синхронизировано, видно на всех устройствах по этой ссылке</div>';
    }
  }

  window.mtSetScreen = function(screen) {
    state.screen = screen;
    ["aptechka", "guide", "lila"].forEach(function(s) {
      var el = document.getElementById("mt-screen-" + s);
      var tab = document.getElementById("mt-tabbtn-" + s);
      if (el) el.classList.toggle("active", s === screen);
      if (tab) tab.classList.toggle("active", s === screen);
    });
  };

  function renderShellIfNeeded() {
    if (shellBuilt) return;
    var app = document.getElementById("mt-app");

    var aptechkaHtml =
      '<div class="mt-screen active" id="mt-screen-aptechka">' +
        '<div class="mt-section" id="mt-entry">' +
          '<h2>Добавить запись</h2>' +
          '<div id="mt-repeat-wrap"></div>' +
          '<div class="mt-type-grid">' +
            '<button type="button" class="mt-type-btn ' + (state.formType === "Лекарство" ? "active" : "") + '" onclick="mtSetType(\'Лекарство\')">Лекарство</button>' +
            '<button type="button" class="mt-type-btn ' + (state.formType === "Ингаляция" ? "active" : "") + '" onclick="mtSetType(\'Ингаляция\')">Ингаляция</button>' +
            '<button type="button" class="mt-type-btn ' + (state.formType === "Другое" ? "active" : "") + '" onclick="mtSetType(\'Другое\')">Другое</button>' +
            '<button type="button" class="mt-type-btn ' + (state.formType === "Температура" ? "active" : "") + '" onclick="mtSetType(\'Температура\')">Температура</button>' +
            '<button type="button" class="mt-type-btn ' + (state.formType === "Курс" ? "active" : "") + '" onclick="mtSetType(\'Курс\')">Курс</button>' +
          '</div>' +
          '<div class="mt-form" id="mt-form-fields"></div>' +
          '<button class="mt-btn" id="mt-save-btn" onclick="mtAdd()">Сохранить</button>' +
        '</div>' +
        '<div class="mt-section" id="mt-courses"></div>' +
        '<div id="mt-data"></div>' +
        '<div class="mt-section" id="mt-history"></div>' +
      '</div>';

    var guideHtml =
      '<div class="mt-screen" id="mt-screen-guide">' +
        '<div class="mt-section">' +
          '<h2>Справка: сколько давать</h2>' +
          '<label>Вес, кг</label>' +
          '<input id="mt-guide-weight" type="number" step="0.1" inputmode="decimal" placeholder="напр. 14" oninput="mtRenderGuide()" />' +
          '<div id="mt-guide-body"></div>' +
          '<div class="mt-disclaimer">Диапазон общий (мг/кг по стандартным педиатрическим ориентирам), не назначение. Смотри инструкцию к конкретному препарату и держись схемы врача, если она отличается.</div>' +
        '</div>' +
      '</div>';

    var lilaHtml =
      '<div class="mt-screen" id="mt-screen-lila">' +
        '<div class="mt-section">' +
          '<h2>Лила растёт</h2>' +
          GROWTH_METRICS.map(function(m) {
            return '<div class="mt-status-row">' +
              '<div>' +
                '<div class="mt-status-name">' + m.label + '</div>' +
                '<div class="mt-status-sub" id="mt-growth-last-' + m.key + '">—</div>' +
              '</div>' +
              '<div class="mt-growth-add">' +
                '<input class="mt-growth-input" id="mt-growth-input-' + m.key + '" aria-label="' + m.label +
                  '" placeholder="' + m.placeholder + '"' + (m.decimal ? ' inputmode="decimal"' : '') +
                  (m.key === "НомерОбуви" ? ' aria-describedby="mt-shoe-size-hint"' : '') + ' />' +
                '<button class="mt-refresh" onclick="mtAddGrowth(\'' + m.key + '\')">+</button>' +
              '</div>' +
            '</div>' + (m.key === "НомерОбуви" ?
              '<p class="mt-status-sub" id="mt-shoe-size-hint" aria-live="polite">Ориентир EU по длине стопы от 9 до 28,4 см</p>' : '');
          }).join('') +
        '</div>' +
        '<div class="mt-section">' +
          '<h2>История замеров</h2>' +
          '<div id="mt-growth-history"></div>' +
        '</div>' +
      '</div>';

    app.innerHTML = growthOnly ? lilaHtml : aptechkaHtml + guideHtml + lilaHtml;
    shellBuilt = true;
    connectShoeSizeSuggestion();
    if (growthOnly) {
      mtSetScreen("lila");
    } else {
      if (location.hash === "#lila") mtSetScreen("lila");
      renderFormFields();
      renderGuideSelectors();
    }
  }

  function renderRepeatChips() {
    var wrap = document.getElementById("mt-repeat-wrap");
    if (!wrap) return;
    var relevant = state.entries.filter(function(e) {
      return canRepeat(e);
    });
    var seen = {};
    var unique = [];
    relevant.forEach(function(e) {
      var key = e.type + "|" + String(e.name || "").trim().toLowerCase();
      if (!seen[key]) {
        seen[key] = true;
        unique.push(e);
      }
    });
    unique = unique.slice(0, 8);
    if (unique.length === 0) { wrap.innerHTML = ""; return; }
    var chips = unique.map(function(e) {
      var suffix = e.type !== "Лекарство" ? " (" + e.type.toLowerCase() + ")" : "";
      var text = e.type === "Температура" ? escapeHtml(e.dose) + " °C" : escapeHtml(e.name) + suffix;
      return repeatButton(e, text, "mt-repeat-chip");
    }).join("");
    wrap.innerHTML = '<div class="mt-repeat-label">Повторить:</div><div class="mt-repeat-wrap">' + chips + '</div>';
  }

  window.mtRepeat = function(id) {
    var entry = state.entries.find(function(e) { return String(e.id) === id; });
    if (!entry || (!canRepeat(entry) && entry.type !== "Курс")) return;
    mtSetType(entry.type === "Курс" ? "Лекарство" : entry.type);
    var fields = entry.type === "Температура" ? { "mt-temp": entry.dose } : {
      "mt-name": entry.name,
      "mt-dose": entry.dose,
      "mt-interval": entry.interval_h,
      "mt-note": entry.type === "Курс" ? courseDetails(entry).instructions : entry.note
    };
    Object.keys(fields).forEach(function(key) {
      document.getElementById(key).value = fields[key] == null ? "" : fields[key];
    });
    document.getElementById("mt-entry").scrollIntoView({ block: "start" });
    document.getElementById("mt-time-only").focus({ preventScroll: true });
  };

  function renderAptechkaData() {
    var dataEl = document.getElementById("mt-data");
    if (!dataEl) return;
    dataEl.innerHTML =
      '<div class="mt-section"><h2>Жаропонижающие</h2>' + renderAntipyreticBoard() + '</div>' +
      '<div class="mt-section"><h2>Другое (интервал)</h2>' + renderOtherBoard() + '</div>' +
      '<div class="mt-section"><h2>Температура</h2>' + renderTempList() + '</div>' +
      '<div class="mt-section"><h2>Частота подъёмов</h2>' + renderTempFrequency() + '</div>';
    renderCourses();
    renderHistory();
  }

  // ---------- Форма добавления (Аптечка) ----------

  function renderFormFields() {
    var el = document.getElementById("mt-form-fields");
    var t = state.formType;
    var dayGrid =
      '<label>Когда</label>' +
      '<div class="mt-day-grid">' +
        '<div class="mt-day-btn ' + (state.formDay === 2 ? "active" : "") + '" onclick="mtSetDay(2)">Позавчера</div>' +
        '<div class="mt-day-btn ' + (state.formDay === 1 ? "active" : "") + '" onclick="mtSetDay(1)">Вчера</div>' +
        '<div class="mt-day-btn ' + (state.formDay === 0 ? "active" : "") + '" onclick="mtSetDay(0)">Сегодня</div>' +
      '</div>' +
      '<label>Время</label>' +
      '<input id="mt-time-only" type="time" value="' + nowTimeValue() + '" />';

    if (t === "Курс") {
      var today = localDateValue(new Date());
      el.innerHTML =
        '<p class="mt-course-desc">Укажи назначенную схему. Фактический приём можно записать из карточки курса.</p>' +
        '<label for="mt-course-name">Лекарство</label><input id="mt-course-name" />' +
        '<label for="mt-course-dose">Доза</label><input id="mt-course-dose" />' +
        '<label for="mt-course-instructions">Схема приёма</label><input id="mt-course-instructions" />' +
        '<div class="mt-row2">' +
          '<div><label for="mt-course-start">Первый день</label><input id="mt-course-start" type="date" value="' + today + '" /></div>' +
          '<div><label for="mt-course-end">Последний день</label><input id="mt-course-end" type="date" /></div>' +
        '</div>';
    } else if (t === "Температура") {
      el.innerHTML =
        '<label>Температура, °C</label>' +
        '<input id="mt-temp" type="number" step="0.1" inputmode="decimal" placeholder="напр. 38.7" />' +
        dayGrid;
    } else {
      el.innerHTML =
        '<label>Название</label>' +
        '<input id="mt-name" list="mt-suggest" placeholder="напр. Нурофен" oninput="mtOnNameInput()" />' +
        '<datalist id="mt-suggest">' +
          '<option value="Нурофен">' +
          '<option value="Парацетамол">' +
          '<option value="Беродуал">' +
          '<option value="Пульмикорт">' +
        '</datalist>' +
        '<div class="mt-row2">' +
          '<div><label>Доза</label><input id="mt-dose" placeholder="напр. 5мл" /></div>' +
          '<div><label>Интервал, ч</label><input id="mt-interval" type="number" step="0.5" placeholder="напр. 6" /></div>' +
        '</div>' +
        '<label>Заметка (необязательно)</label>' +
        '<input id="mt-note" placeholder="" />' +
        dayGrid;
    }
  }

  window.mtSetType = function(t) {
    state.formType = t;
    state.formDay = 0;
    var order = ["Лекарство", "Ингаляция", "Другое", "Температура", "Курс"];
    document.querySelectorAll(".mt-type-grid .mt-type-btn").forEach(function(b, i) {
      b.classList.toggle("active", order[i] === t);
    });
    renderFormFields();
    document.getElementById("mt-save-btn").textContent = t === "Курс" ? "Сохранить курс" : "Сохранить";
  };

  window.mtSetDay = function(offset) {
    state.formDay = offset;
    document.querySelectorAll(".mt-day-btn").forEach(function(b, i) {
      b.classList.toggle("active", (2 - i) === offset);
    });
  };

  window.mtOnNameInput = function() {
    var nameEl = document.getElementById("mt-name");
    var intervalEl = document.getElementById("mt-interval");
    if (!nameEl || !intervalEl) return;
    var detected = detectInterval(nameEl.value);
    if (detected) intervalEl.value = detected;
  };

  window.mtRefresh = function() { refresh(); };

  function buildTimeISO() {
    var timeVal = document.getElementById("mt-time-only").value;
    if (!timeVal) return null;
    var parts = timeVal.split(":");
    var d = new Date();
    d.setDate(d.getDate() - state.formDay);
    d.setHours(parseInt(parts[0], 10), parseInt(parts[1], 10), 0, 0);
    return d.toISOString();
  }

  window.mtAdd = async function() {
    var type = state.formType;
    var time = type === "Курс" ? null : buildTimeISO();
    if (type !== "Курс" && !time) { alert("Укажи время"); return; }
    var payload = null;

    if (type === "Курс") {
      var courseName = document.getElementById("mt-course-name").value.trim();
      var start = document.getElementById("mt-course-start").value;
      var end = document.getElementById("mt-course-end").value;
      if (!courseName) { alert("Укажи название лекарства"); return; }
      if (!start || !end || end < start) { alert("Укажи первый и последний день курса по порядку"); return; }
      payload = {
        type: type, name: courseName,
        dose: document.getElementById("mt-course-dose").value.trim(),
        note: JSON.stringify({ start: start, end: end, instructions: document.getElementById("mt-course-instructions").value.trim() }),
        time: new Date(start + "T12:00:00").toISOString()
      };
    } else if (type === "Температура") {
      var temp = document.getElementById("mt-temp").value;
      if (!temp) { alert("Укажи температуру"); return; }
      payload = { type: type, name: "Температура", dose: temp, time: time };
    } else {
      var name = document.getElementById("mt-name").value.trim();
      if (!name) { alert("Укажи название"); return; }
      var dose = document.getElementById("mt-dose").value.trim();
      var interval = parseFloat(document.getElementById("mt-interval").value) || null;
      var note = document.getElementById("mt-note").value.trim();
      payload = { type: type, name: name, dose: dose, interval_h: interval, note: note, time: time };
    }

    var btn = document.getElementById("mt-save-btn");
    btn.disabled = true;
    btn.textContent = "Сохраняю...";
    try {
      await dbInsert(payload);
      state.formDay = 0;
      if (state.formType === type) renderFormFields();
      await refresh();
    } catch (e) {
      alert("Не удалось сохранить — проверь интернет и попробуй ещё раз.");
    }
    btn.disabled = false;
    btn.textContent = state.formType === "Курс" ? "Сохранить курс" : "Сохранить";
  };

  window.mtDelete = async function(id) {
    try {
      await dbDelete(id);
      await refresh();
    } catch (e) {
      alert("Не удалось удалить — проверь интернет.");
    }
  };

  // ---------- Справка (расчёт доз) ----------

  function renderGuideSelectors() {
    var body = document.getElementById("mt-guide-body");
    if (!body) return;
    var html = "";
    for (var key in DOSAGE_GUIDE) {
      var d = DOSAGE_GUIDE[key];
      var options = d.concentrations.map(function(c, i) {
        return '<option value="' + i + '">' + escapeHtml(c.label) + '</option>';
      }).join("");
      html += '<div class="mt-guide-drug">' +
        '<div class="mt-guide-drug-name">' + d.label + '</div>' +
        '<div class="mt-status-sub">' + d.mgPerKgLow + '-' + d.mgPerKgHigh + ' мг/кг на приём, до ' + d.maxTimesPerDay + ' раз в сутки</div>' +
        '<label>Форма</label>' +
        '<select id="mt-guide-conc-' + key + '" onchange="mtRenderGuide()">' + options + '</select>' +
        '<div id="mt-guide-custom-' + key + '" style="display:none;">' +
          '<div class="mt-day-grid" style="grid-template-columns:1fr 1fr;margin-top:8px;">' +
            '<div class="mt-day-btn active" id="mt-guide-ct-syrup-' + key + '" onclick="mtSetGuideCustomType(\'' + key + '\',\'syrup\')">Сироп, мг/5мл</div>' +
            '<div class="mt-day-btn" id="mt-guide-ct-tablet-' + key + '" onclick="mtSetGuideCustomType(\'' + key + '\',\'tablet\')">Таблетка, мг/шт</div>' +
          '</div>' +
          '<label>Значение, мг</label>' +
          '<input id="mt-guide-custom-input-' + key + '" type="number" step="1" inputmode="decimal" oninput="mtRenderGuide()" />' +
        '</div>' +
        '<div class="mt-guide-result" id="mt-guide-result-' + key + '"></div>' +
      '</div>';
    }
    body.innerHTML = html;
    mtRenderGuide();
  }

  window.mtSetGuideCustomType = function(key, type) {
    guideCustomType[key] = type;
    var syrupBtn = document.getElementById("mt-guide-ct-syrup-" + key);
    var tabletBtn = document.getElementById("mt-guide-ct-tablet-" + key);
    if (syrupBtn) syrupBtn.classList.toggle("active", type === "syrup");
    if (tabletBtn) tabletBtn.classList.toggle("active", type === "tablet");
    mtRenderGuide();
  };

  window.mtRenderGuide = function() {
    var weightEl = document.getElementById("mt-guide-weight");
    var weight = weightEl ? parseFloat(weightEl.value) : NaN;
    for (var key in DOSAGE_GUIDE) {
      var d = DOSAGE_GUIDE[key];
      var concSelect = document.getElementById("mt-guide-conc-" + key);
      var customBlock = document.getElementById("mt-guide-custom-" + key);
      var resultEl = document.getElementById("mt-guide-result-" + key);
      if (!concSelect || !resultEl) continue;

      var idx = parseInt(concSelect.value, 10) || 0;
      var chosen = d.concentrations[idx];
      var effectiveType = chosen.type;
      var mgVal = chosen.mg;

      if (chosen.type === "custom") {
        if (customBlock) customBlock.style.display = "block";
        effectiveType = guideCustomType[key];
        var customInput = document.getElementById("mt-guide-custom-input-" + key);
        mgVal = customInput ? parseFloat(customInput.value) : NaN;
      } else {
        if (customBlock) customBlock.style.display = "none";
      }

      if (!weight || weight <= 0) {
        resultEl.innerHTML = '<span class="mt-guide-sub">Укажи вес ребёнка</span>';
        continue;
      }
      var mgLow = weight * d.mgPerKgLow;
      var mgHigh = weight * d.mgPerKgHigh;
      var mgLowRound = Math.round(mgLow);
      var mgHighRound = Math.round(mgHigh);

      if (!mgVal || mgVal <= 0) {
        resultEl.innerHTML = mgLowRound + '-' + mgHighRound + ' мг на приём<br/>' +
          '<span class="mt-guide-sub">укажи дозу формы, чтобы перевести в мл/таблетки</span>';
        continue;
      }

      if (effectiveType === "tablet") {
        var cLow = mgLow / mgVal;
        var cHigh = mgHigh / mgVal;
        resultEl.innerHTML = formatFraction(cLow) + '-' + formatFraction(cHigh) + ' табл на приём<br/>' +
          '<span class="mt-guide-sub">' + mgLowRound + '-' + mgHighRound + ' мг на приём</span>';
      } else {
        var mlLow = (mgLow / mgVal) * 5;
        var mlHigh = (mgHigh / mgVal) * 5;
        resultEl.innerHTML = mlLow.toFixed(1) + '-' + mlHigh.toFixed(1) + ' мл на приём<br/>' +
          '<span class="mt-guide-sub">' + mgLowRound + '-' + mgHighRound + ' мг на приём</span>';
      }
    }
  };

  refresh();
  setInterval(function() { refresh(); }, 20000);
  window.addEventListener("focus", function() { refresh(); });
})();
