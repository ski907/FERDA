function setupCanvas(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);  
    return ctx;
}

const rangeCtx = setupCanvas(document.getElementById('rangeChart'));
const batteryCtx = setupCanvas(document.getElementById('batteryChart'));
const freeboardCtx = setupCanvas(document.getElementById('freeboardChart'));

const rangeData = [];
const batteryData = [];
const freeboardData = [];
const timeLabels = [];  // Store time labels for the x-axis

function formatTime(timestamp) {
    const date = new Date(timestamp * 1000);
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    return `${hours}:${minutes}:${seconds}`;
}

function drawAxes(ctx, min, max, label) {
    const width = ctx.canvas.width / (window.devicePixelRatio || 1);
    const height = ctx.canvas.height / (window.devicePixelRatio || 1);

    ctx.clearRect(0, 0, width, height);

    ctx.strokeStyle = '#cccccc';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(40, 20);
    ctx.lineTo(40, height - 40);  // Y-axis
    ctx.lineTo(width - 20, height - 40);  // X-axis
    ctx.stroke();

    const numHorizontalLines = 5;
    const verticalSpacing = (height - 60) / numHorizontalLines;
    for (let i = 0; i <= numHorizontalLines; i++) {
        const y = 20 + i * verticalSpacing;
        const value = max - (i * (max - min) / numHorizontalLines);
        
        ctx.strokeStyle = '#e0e0e0';
        ctx.beginPath();
        ctx.moveTo(40, y);
        ctx.lineTo(width - 20, y);
        ctx.stroke();

        ctx.fillStyle = '#666';
        ctx.font = '12px Arial';
        ctx.textAlign = 'right';
        ctx.fillText(value.toFixed(1), 35, y + 4);
    }

    ctx.textAlign = 'center';
    ctx.fillText(label, width / 2, height - 10);

    const numVerticalLines = 6;
    const horizontalSpacing = (width - 60) / numVerticalLines;
    for (let i = 0; i <= numVerticalLines; i++) {
        const x = 40 + i * horizontalSpacing;
        
        ctx.strokeStyle = '#e0e0e0';
        ctx.beginPath();
        ctx.moveTo(x, 20);
        ctx.lineTo(x, height - 40);
        ctx.stroke();
    }
}
// Variables to track the current vertical limits with some padding
let rangeMin = null, rangeMax = null;
let batteryMin = null, batteryMax = null;
let freeboardMin = null, freeboardMax = null;

function updateAxisLimits(dataArray, currentMin, currentMax, buffer = 0.1) {
    const dataMin = Math.min(...dataArray);
    const dataMax = Math.max(...dataArray);

    // Apply buffer to prevent constant shifting (10% buffer as an example)
    const newMin = dataMin - Math.abs(dataMin * buffer);
    const newMax = dataMax + Math.abs(dataMax * buffer);

    // Update axis limits only if the data goes outside the current buffered range
    if (currentMin === null || dataMin < currentMin || dataMax > currentMax) {
        return { min: newMin, max: newMax };
    } else {
        return { min: currentMin, max: currentMax };
    }
}

function drawPlot(ctx, data, color, min, max, label) {
    const width = ctx.canvas.width / (window.devicePixelRatio || 1);
    const height = ctx.canvas.height / (window.devicePixelRatio || 1);

    drawAxes(ctx, min, max, label);

    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    for (let i = 0; i < data.length; i++) {
        const x = 40 + (width - 60) * (i / 60);
        const y = height - 40 - ((data[i] - min) / (max - min)) * (height - 60);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();

    // X-axis time labels
    ctx.fillStyle = '#666';
    ctx.font = '10px Arial';
    ctx.textAlign = 'center';
    for (let i = 0; i < timeLabels.length; i++) {
        const x = 40 + (width - 60) * (i / 60);
        if (i % 10 === 0) {
            ctx.fillText(timeLabels[i], x, height - 25);
        }
    }
}

async function fetchDataAndUpdate() {
    try {
        const response = await fetch('/log_data.json');
        const dataArray = await response.json();

        if (dataArray.length > 0) {
            const latestData = dataArray[dataArray.length - 1];
            const { battery, freeboard, range, timestamp } = latestData;
            const timeLabel = formatTime(timestamp);

            document.getElementById('currentRange').textContent = Math.round(range) + ' mm';
            document.getElementById('currentBattery').textContent = battery.toFixed(2) + ' V';
            document.getElementById('currentFreeboard').textContent = Math.round(freeboard) + ' mm';

            if (rangeData.length >= 60) rangeData.shift();
            if (batteryData.length >= 60) batteryData.shift();
            if (freeboardData.length >= 60) freeboardData.shift();
            if (timeLabels.length >= 60) timeLabels.shift();

            rangeData.push(range);
            batteryData.push(battery);
            freeboardData.push(freeboard);
            timeLabels.push(timeLabel);

            // Update axis limits with dynamic scaling
            ({ min: rangeMin, max: rangeMax } = updateAxisLimits(rangeData, rangeMin, rangeMax));
            ({ min: batteryMin, max: batteryMax } = updateAxisLimits(batteryData, batteryMin, batteryMax));
            ({ min: freeboardMin, max: freeboardMax } = updateAxisLimits(freeboardData, freeboardMin, freeboardMax));

            // Draw updated plots
            drawPlot(rangeCtx, rangeData, "#2196F3", rangeMin, rangeMax, "Range (mm)");
            drawPlot(batteryCtx, batteryData, "#4CAF50", batteryMin, batteryMax, "Battery (V)");
            drawPlot(freeboardCtx, freeboardData, "#FF9800", freeboardMin, freeboardMax, "Freeboard (mm)");
        }
    } catch (error) {
        console.error("Failed to fetch data:", error);
    }
}

setInterval(fetchDataAndUpdate, 1000);
