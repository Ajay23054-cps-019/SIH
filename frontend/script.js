const API_URL = 'http://localhost:8000';
let refreshInterval;
let processUpdateCounter = 0;

let cpuChart = null;
let ramChart = null;
let networkChart = null;

const MAX_HISTORY = 30;

async function fetchSystemData(processName) {
    const url = processName === 'all'
        ? `${API_URL}/?code=`
        : `${API_URL}/?code=${processName}`;

    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        throw error;
    }
}

async function fetchHistory(limit = MAX_HISTORY) {
    try {
        const response = await fetch(`${API_URL}/history?limit=${limit}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error('Failed to fetch history:', error);
        return [];
    }
}

const BYTES_UNITS = ['B', 'KB', 'MB', 'GB'];
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), BYTES_UNITS.length - 1);
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + BYTES_UNITS[i];
}

function formatTime(iso) {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function getProcessStatus(status) {
    const map = { running: 'running', sleeping: 'sleeping', stopped: 'stopped', 'disk-sleep': 'sleeping', zombie: 'stopped' };
    return map[status] || status;
}

function createChart(canvasId, label, color, datasets) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    const ds = datasets || [{ label: label, color: color }];
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: ds.map(d => ({
                label: d.label,
                data: [],
                borderColor: d.color,
                backgroundColor: d.color + '20',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 3,
            }))
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: ds.length > 1, labels: { color: '#a0a0a0', boxWidth: 12, padding: 8 } },
                tooltip: { mode: 'index', intersect: false }
            },
            scales: {
                x: {
                    display: true,
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#a0a0a0', maxRotation: 0, maxTicksLimit: 6 }
                },
                y: {
                    display: true,
                    beginAtZero: true,
                    max: label === 'CPU' ? 100 : undefined,
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#a0a0a0', maxTicksLimit: 5 }
                }
            }
        }
    });
}

function initCharts() {
    if (cpuChart) cpuChart.destroy();
    if (ramChart) ramChart.destroy();
    if (networkChart) networkChart.destroy();

    cpuChart = createChart('cpuChart', 'CPU %', '#ff6b6b');

    ramChart = createChart('ramChart', 'RAM %', '#4ecdc4');

    networkChart = createChart('networkChart', 'Network', '#45b7d1', [
        { label: 'Uploaded', color: '#667eea' },
        { label: 'Downloaded', color: '#4ecdc4' }
    ]);
}

function updateCharts(history) {
    if (!history || history.length === 0) return;

    const len = history.length;
    const labels = new Array(len);
    const cpuData = new Array(len);
    const ramData = new Array(len);
    const sentData = new Array(len);
    const receivedData = new Array(len);

    for (let i = 0; i < len; i++) {
        const h = history[i];
        labels[i] = formatTime(h.timestamp);
        cpuData[i] = h.cpu;
        ramData[i] = h.ram_percent;
        sentData[i] = h.bytes_sent;
        receivedData[i] = h.bytes_received;
    }

    cpuChart.data.labels = labels;
    cpuChart.data.datasets[0].data = cpuData;
    cpuChart.update('none');

    ramChart.data.labels = labels;
    ramChart.data.datasets[0].data = ramData;
    ramChart.update('none');

    networkChart.data.labels = labels;
    networkChart.data.datasets[0].data = sentData;
    networkChart.data.datasets[1].data = receivedData;
    networkChart.update('none');

    const last = len - 1;
    document.getElementById('cpuPercentage').textContent = cpuData[last].toFixed(1);
    document.getElementById('ramPercentage').textContent = ramData[last].toFixed(1);
    document.getElementById('bytesSent').textContent = formatBytes(sentData[last] || 0);
    document.getElementById('bytesReceived').textContent = formatBytes(receivedData[last] || 0);
}

function updateProcesses(processes) {
    const tbody = document.getElementById('processesBody');
    const processCount = document.getElementById('processCount');

    if (!processes || processes.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No processes found</td></tr>';
        processCount.textContent = '0 running';
        return;
    }

    processCount.textContent = `${processes.length} running`;

    let html = '';
    for (let i = 0; i < processes.length; i++) {
        const p = processes[i];
        html += `<tr><td>${p.pid}</td><td>${p.name}</td><td>${(p.cpu_percent || 0).toFixed(1)}%</td><td>${(p.memory_percent || 0).toFixed(1)}%</td><td><span class="status-badge status-running">running</span></td></tr>`;
    }
    tbody.innerHTML = html;
}

function updateLastUpdated() {
    document.getElementById('lastUpdated').textContent = 'Last updated: ' + new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function showError(message) {
    document.getElementById('errorMessage').textContent = message;
    document.getElementById('errorModal').classList.add('active');
    document.getElementById('statusIndicator').classList.add('disconnected');
}

function hideError() {
    document.getElementById('errorModal').classList.remove('active');
    document.getElementById('statusIndicator').classList.remove('disconnected');
}

async function updateDashboard() {
    const processFilter = document.getElementById('processFilter').value;

    try {
        const [data, history] = await Promise.all([
            fetchSystemData(processFilter),
            fetchHistory(MAX_HISTORY)
        ]);

        updateCharts(history);
        processUpdateCounter++;
        if (processUpdateCounter % 5 === 0) {
            updateProcesses(data.processes);
        }
        updateLastUpdated();
        hideError();
    } catch (error) {
        console.error('Failed to fetch data:', error);
        showError('Unable to connect to server. Make sure the backend is running on ' + API_URL);
    }
}

function startAutoRefresh() {
    const interval = 1000;
    refreshInterval = setInterval(updateDashboard, interval);
    document.getElementById('refreshInterval').textContent = `${interval / 1000}s`;
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

document.getElementById('refreshBtn').addEventListener('click', updateDashboard);

document.getElementById('processFilter').addEventListener('change', () => {
    processUpdateCounter = 0;
    updateDashboard();
});

document.getElementById('closeModal').addEventListener('click', hideError);
document.getElementById('errorModal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) hideError();
});

window.addEventListener('online', () => { hideError(); updateDashboard(); });
window.addEventListener('offline', () => { showError('You are currently offline. Please check your connection.'); });

document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    updateDashboard();
    startAutoRefresh();
});

if (document.readyState === 'complete' || document.readyState === 'interactive') {
    initCharts();
    updateDashboard();
    startAutoRefresh();
}
