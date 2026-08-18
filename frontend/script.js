const API_URL = 'http://localhost:8000';
let refreshInterval;

let cpuChart = null;
let ramChart = null;
let networkChart = null;

const MAX_HISTORY = 60;

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

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatTime(iso) {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function getProcessStatus(status) {
    const statusMap = {
        'running': 'running',
        'sleeping': 'sleeping',
        'stopped': 'stopped',
        'disk-sleep': 'sleeping',
        'zombie': 'stopped'
    };
    return statusMap[status] || status;
}

function createChart(canvasId, label, color, datasets) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: datasets.map(ds => ({
                label: ds.label,
                data: [],
                borderColor: ds.color,
                backgroundColor: ds.color + '20',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 4,
            }))
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    display: datasets.length > 1,
                    labels: {
                        color: '#a0a0a0',
                        boxWidth: 12,
                        padding: 16,
                    }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                }
            },
            scales: {
                x: {
                    display: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)',
                    },
                    ticks: {
                        color: '#a0a0a0',
                        maxRotation: 0,
                        maxTicksLimit: 8,
                    }
                },
                y: {
                    display: true,
                    beginAtZero: true,
                    max: label === 'CPU' ? 100 : undefined,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)',
                    },
                    ticks: {
                        color: '#a0a0a0',
                    }
                }
            }
        }
    });
}

function initCharts() {
    if (cpuChart) cpuChart.destroy();
    if (ramChart) ramChart.destroy();
    if (networkChart) networkChart.destroy();

    cpuChart = createChart('cpuChart', 'CPU', '#ff6b6b', [
        { label: 'CPU %', color: '#ff6b6b' }
    ]);

    ramChart = createChart('ramChart', 'RAM', '#4ecdc4', [
        { label: 'RAM %', color: '#4ecdc4' }
    ]);

    networkChart = createChart('networkChart', 'Network', '#45b7d1', [
        { label: 'Uploaded', color: '#667eea' },
        { label: 'Downloaded', color: '#4ecdc4' }
    ]);
}

function updateCharts(history) {
    if (!history || history.length === 0) return;

    const labels = history.map(h => formatTime(h.timestamp));
    const cpuData = history.map(h => h.cpu);
    const ramData = history.map(h => h.ram_percent);
    const sentData = history.map(h => h.bytes_sent);
    const receivedData = history.map(h => h.bytes_received);

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

    const latest = history[history.length - 1];
    document.getElementById('cpuPercentage').textContent = cpuData[cpuData.length - 1]?.toFixed(1) || '0';
    document.getElementById('ramPercentage').textContent = ramData[ramData.length - 1]?.toFixed(1) || '0';
    document.getElementById('bytesSent').textContent = formatBytes(sentData[sentData.length - 1] || 0);
    document.getElementById('bytesReceived').textContent = formatBytes(receivedData[receivedData.length - 1] || 0);
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

    tbody.innerHTML = processes.map(proc => {
        const status = getProcessStatus('running');
        return `
            <tr>
                <td>${proc.pid}</td>
                <td>${proc.name}</td>
                <td>${proc.cpu_percent ? proc.cpu_percent.toFixed(1) : '0.0'}%</td>
                <td>${proc.memory_percent ? proc.memory_percent.toFixed(1) : '0.0'}%</td>
                <td><span class="status-badge status-${status}">${status}</span></td>
            </tr>
        `;
    }).join('');
}

function updateLastUpdated() {
    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    document.getElementById('lastUpdated').textContent = `Last updated: ${timeString}`;
}

function showError(message) {
    const modal = document.getElementById('errorModal');
    const errorMessage = document.getElementById('errorMessage');
    errorMessage.textContent = message;
    modal.classList.add('active');

    const statusIndicator = document.getElementById('statusIndicator');
    statusIndicator.classList.add('disconnected');
}

function hideError() {
    document.getElementById('errorModal').classList.remove('active');
    const statusIndicator = document.getElementById('statusIndicator');
    statusIndicator.classList.remove('disconnected');
}

async function updateDashboard() {
    const processFilter = document.getElementById('processFilter').value;

    try {
        const [data, history] = await Promise.all([
            fetchSystemData(processFilter),
            fetchHistory(MAX_HISTORY)
        ]);

        updateCharts(history);
        updateProcesses(data.processes);
        updateLastUpdated();

        hideError();
    } catch (error) {
        console.error('Failed to fetch data:', error);
        showError(`Unable to connect to server. Make sure the backend is running on ${API_URL}`);
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

document.getElementById('refreshBtn').addEventListener('click', () => {
    updateDashboard();
});

document.getElementById('processFilter').addEventListener('change', () => {
    updateDashboard();
});

document.getElementById('closeModal').addEventListener('click', hideError);

document.getElementById('errorModal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) {
        hideError();
    }
});

window.addEventListener('online', () => {
    hideError();
    updateDashboard();
});

window.addEventListener('offline', () => {
    showError('You are currently offline. Please check your connection.');
});

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
