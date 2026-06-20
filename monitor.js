// ── Tab management ──────────────────────────────────────────────────────────

function showTab(name, btn) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    btn.classList.add('active');
    if (name === 'settings') loadSettingsForm();
}

// ── Canvas setup ─────────────────────────────────────────────────────────────

function setupCanvas(id) {
    const canvas = document.getElementById(id);
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    return ctx;
}

const freeboardCtx = setupCanvas('freeboardChart');
const rangeCtx     = setupCanvas('rangeChart');
const batteryCtx   = setupCanvas('batteryChart');

// ── Chart data ───────────────────────────────────────────────────────────────

const freeboardData = [], rangeData = [], batteryData = [], timeLabels = [];
let freeboardMin = null, freeboardMax = null;
let rangeMin = null, rangeMax = null;
let batteryMin = null, batteryMax = null;
const MAX_POINTS = 60;

let config = {};
let lastTimestamp = 0;

// ── Chart drawing ─────────────────────────────────────────────────────────────

function drawChart(ctx, data, color, min, max, thresholdMm) {
    const dpr = window.devicePixelRatio || 1;
    const w = ctx.canvas.width / dpr;
    const h = ctx.canvas.height / dpr;
    const pad = { top: 14, right: 8, bottom: 28, left: 42 };
    const pw = w - pad.left - pad.right;
    const ph = h - pad.top - pad.bottom;
    const range = (max - min) || 1;

    ctx.clearRect(0, 0, w, h);

    // Horizontal grid lines + Y labels
    const gridLines = 4;
    for (let i = 0; i <= gridLines; i++) {
        const y = pad.top + i * ph / gridLines;
        const val = max - i * range / gridLines;
        ctx.strokeStyle = '#1e3a5f';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke();
        ctx.fillStyle = '#555';
        ctx.font = '10px Arial';
        ctx.textAlign = 'right';
        ctx.fillText(val.toFixed(Math.abs(val) < 10 ? 1 : 0), pad.left - 3, y + 4);
    }

    // Alarm threshold dashed line
    if (thresholdMm !== undefined && thresholdMm >= min && thresholdMm <= max) {
        const ty = pad.top + ph * (1 - (thresholdMm - min) / range);
        ctx.strokeStyle = '#f44336';
        ctx.lineWidth = 1;
        ctx.setLineDash([5, 4]);
        ctx.beginPath(); ctx.moveTo(pad.left, ty); ctx.lineTo(w - pad.right, ty); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = '#f44336';
        ctx.font = '9px Arial';
        ctx.textAlign = 'left';
        ctx.fillText('alarm', pad.left + 3, ty - 3);
    }

    // Zero line on freeboard chart
    if (thresholdMm !== undefined && 0 >= min && 0 <= max) {
        const zy = pad.top + ph * (1 - (0 - min) / range);
        ctx.strokeStyle = '#ff980044';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(pad.left, zy); ctx.lineTo(w - pad.right, zy); ctx.stroke();
    }

    // Axes
    ctx.strokeStyle = '#2a4a7f';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad.left, pad.top);
    ctx.lineTo(pad.left, h - pad.bottom);
    ctx.lineTo(w - pad.right, h - pad.bottom);
    ctx.stroke();

    // Data line
    if (data.length > 1) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        data.forEach((v, i) => {
            const x = pad.left + pw * (i / (data.length - 1));
            const y = pad.top + ph * (1 - (v - min) / range);
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        });
        ctx.stroke();
    }

    // X-axis time labels (every ~10 points)
    if (timeLabels.length > 0) {
        ctx.fillStyle = '#444';
        ctx.font = '9px Arial';
        ctx.textAlign = 'center';
        const step = Math.max(1, Math.floor(timeLabels.length / 6));
        timeLabels.forEach((t, i) => {
            if (i % step === 0) {
                const x = pad.left + pw * (i / Math.max(timeLabels.length - 1, 1));
                ctx.fillText(t, x, h - pad.bottom + 11);
            }
        });
    }
}

function updateLimits(data, min, max, buffer) {
    if (!data.length) return { min: min || 0, max: max || 1 };
    buffer = buffer || 0.12;
    const dMin = Math.min.apply(null, data);
    const dMax = Math.max.apply(null, data);
    const spread = (dMax - dMin) || 1;
    if (min === null || dMin < min || dMax > max) {
        return { min: dMin - spread * buffer, max: dMax + spread * buffer };
    }
    return { min: min, max: max };
}

function redrawAll() {
    const threshold = config.alarm_threshold_mm || 20;

    // Freeboard axis always includes 0 and the alarm threshold
    let fbMin = freeboardMin !== null ? freeboardMin : -10;
    let fbMax = freeboardMax !== null ? freeboardMax : threshold * 2;
    fbMin = Math.min(fbMin, -5);
    fbMax = Math.max(fbMax, threshold * 1.5);

    drawChart(freeboardCtx, freeboardData, '#4caf50', fbMin, fbMax, threshold);
    drawChart(rangeCtx,     rangeData,     '#2196f3', rangeMin   || 0, rangeMax   || 1);
    drawChart(batteryCtx,   batteryData,   '#ff9800', batteryMin || 0, batteryMax || 1);
}

// ── Data ingestion ────────────────────────────────────────────────────────────

function formatTime(ts) {
    const d = new Date(ts * 1000);
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
}

function pushEntry(entry) {
    if (freeboardData.length >= MAX_POINTS) {
        freeboardData.shift(); rangeData.shift(); batteryData.shift(); timeLabels.shift();
    }
    freeboardData.push(entry.freeboard);
    rangeData.push(entry.range);
    batteryData.push(entry.battery);
    timeLabels.push(formatTime(entry.timestamp));

    ({ min: freeboardMin, max: freeboardMax } = updateLimits(freeboardData, freeboardMin, freeboardMax));
    ({ min: rangeMin,     max: rangeMax     } = updateLimits(rangeData,     rangeMin,     rangeMax));
    ({ min: batteryMin,   max: batteryMax   } = updateLimits(batteryData,   batteryMin,   batteryMax));
}

function updateDisplay(entry) {
    const fb        = entry.freeboard;
    const threshold = config.alarm_threshold_mm || 20;
    const expected  = config.expected_freeboard_mm || 0;

    // Freeboard value + color
    const fbEl = document.getElementById('currentFreeboard');
    fbEl.textContent = Math.round(fb) + ' mm';
    fbEl.className = 'val' +
        (fb <= 0            ? ' danger' :
         fb < threshold     ? ' warn'   : ' ok');

    // Expected vs actual callout
    const subEl = document.getElementById('freeboardSub');
    if (expected > 0) {
        const diff = Math.round(fb - expected);
        subEl.textContent = 'Expected ' + Math.round(expected) + ' mm  Δ ' +
            (diff >= 0 ? '+' : '') + diff + ' mm';
    } else {
        subEl.textContent = 'Run Setup to set expected value';
    }

    document.getElementById('currentRange').textContent = Math.round(entry.range);
    document.getElementById('currentBattery').textContent = entry.battery.toFixed(2);
    document.getElementById('alarmBanner').style.display = fb < threshold ? 'block' : 'none';
    document.getElementById('lastUpdate').textContent = 'Last update: ' + formatTime(entry.timestamp);
}

// ── Polling ───────────────────────────────────────────────────────────────────

async function fetchConfig() {
    try {
        const r = await fetch('/config');
        config = await r.json();
    } catch (e) {}
}

async function initHistory() {
    try {
        const r = await fetch('/log_data.json');
        const data = await r.json();
        if (data.length > 0) {
            data.forEach(pushEntry);
            updateDisplay(data[data.length - 1]);
            lastTimestamp = data[data.length - 1].timestamp;
            redrawAll();
        }
    } catch (e) {}
}

async function poll() {
    try {
        const r = await fetch('/latest.json');
        const entry = await r.json();
        if (entry.timestamp && entry.timestamp !== lastTimestamp) {
            lastTimestamp = entry.timestamp;
            pushEntry(entry);
            updateDisplay(entry);
            redrawAll();
        }
    } catch (e) {
        console.error('Poll error:', e);
    }
}

// ── Setup tab ─────────────────────────────────────────────────────────────────

function setResult(id, cls, text) {
    const el = document.getElementById(id);
    el.className = 'result ' + cls;
    el.textContent = text;
}

async function doCalibrate() {
    const capMm = document.getElementById('capDistance').value;
    if (!capMm) { alert('Enter cap distance first'); return; }
    setResult('calResult', '', 'Reading sensor…');
    document.getElementById('calResult').style.display = 'block';
    try {
        const r = await fetch('/calibrate?cap_mm=' + encodeURIComponent(capMm));
        const d = await r.json();
        if (d.status === 'ok') {
            setResult('calResult', 'ok',
                'Done. Raw reading: ' + d.raw_range_mm + ' mm  →  offset saved: ' + d.range_offset_mm + ' mm');
            document.getElementById('step2').classList.add('active-step');
        } else {
            setResult('calResult', 'error', 'Calibration failed.');
        }
    } catch (e) {
        setResult('calResult', 'error', 'Error: ' + e);
    }
}

async function doSetIce() {
    const iceCm = document.getElementById('iceThickness').value;
    if (!iceCm || isNaN(iceCm)) { alert('Enter ice thickness in cm'); return; }
    setResult('iceResult', '', 'Calculating…');
    document.getElementById('iceResult').style.display = 'block';
    try {
        const r = await fetch('/set_ice?ice_cm=' + encodeURIComponent(iceCm));
        const d = await r.json();
        config.expected_freeboard_mm = d.expected_freeboard_mm;
        setResult('iceResult', 'ok',
            'Ice: ' + d.ice_thickness_cm + ' cm  →  expected freeboard: ' + d.expected_freeboard_mm + ' mm');
        const step3 = document.getElementById('step3');
        step3.style.display = 'block';
        step3.classList.add('active-step');
    } catch (e) {
        setResult('iceResult', 'error', 'Error: ' + e);
    }
}

async function doVerify() {
    const el = document.getElementById('verifyResult');
    el.innerHTML = 'Measuring…';
    try {
        const r = await fetch('/verify');
        const d = await r.json();
        const pass = d.status === 'ok';
        const statusColor = pass ? '#4caf50' : '#ff9800';
        const statusLabel = pass ? '✓ PASS' : '⚠ CHECK SENSOR';
        el.innerHTML =
            '<div class="verify-row"><span>Expected freeboard</span><span class="vval">' + d.expected_freeboard_mm + ' mm</span></div>' +
            '<div class="verify-row"><span>Measured freeboard</span><span class="vval">' + d.measured_freeboard_mm + ' mm</span></div>' +
            '<div class="verify-row"><span>Difference</span><span class="vval">' + d.difference_mm + ' mm (' + d.difference_pct + '%)</span></div>' +
            '<div class="verify-status" style="color:' + statusColor + '">' + statusLabel + '</div>';
    } catch (e) {
        el.innerHTML = '<span style="color:#f44336">Error: ' + e + '</span>';
    }
}

// ── Settings tab ──────────────────────────────────────────────────────────────

async function loadSettingsForm() {
    try {
        const r = await fetch('/config');
        const s = await r.json();
        config = s;
        document.getElementById('sensorToFlange').value  = s.sensor_to_flange_mm  || '';
        document.getElementById('alarmThreshold').value  = s.alarm_threshold_mm   || '';
        document.getElementById('logInterval').value     = s.log_interval_sec      || '';
        document.getElementById('wifiSsid').value        = s.wifi_ssid             || '';
        document.getElementById('wifiPassword').value    = '';
        // Pre-fill setup fields if previously saved
        if (s.cap_distance_mm)   document.getElementById('capDistance').value   = s.cap_distance_mm;
        if (s.ice_thickness_cm)  document.getElementById('iceThickness').value  = s.ice_thickness_cm;
    } catch (e) {}
}

async function saveSettings() {
    const params = new URLSearchParams({
        sensor_to_flange_mm: document.getElementById('sensorToFlange').value,
        alarm_threshold_mm:  document.getElementById('alarmThreshold').value,
        log_interval_sec:    document.getElementById('logInterval').value,
        wifi_ssid:           document.getElementById('wifiSsid').value,
    });
    const pw = document.getElementById('wifiPassword').value;
    if (pw) params.set('wifi_password', pw);

    try {
        const r = await fetch('/save_config?' + params.toString());
        const d = await r.json();
        setResult('settingsResult', 'ok', d.status);
        // Refresh config so alarm threshold updates on monitor tab
        freeboardMin = freeboardMax = null;
        await fetchConfig();
    } catch (e) {
        setResult('settingsResult', 'error', 'Error: ' + e);
    }
}

// ── Init ──────────────────────────────────────────────────────────────────────

fetchConfig().then(initHistory).then(() => {
    setInterval(poll, 1000);
});
