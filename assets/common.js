// OpenClaw Dashboard — Common utilities

const PAGES = [
  { id: 'index', title: 'Dashboard', icon: '🏠', href: 'index.html' },
  { id: 'a-shares', title: 'A 股', icon: '🇨🇳', href: 'a-shares.html' },
  { id: 'global-market', title: '国际市场', icon: '🌍', href: 'global-market.html' },
  { id: 'helloquant', title: 'HelloQuant', icon: '📈', href: 'helloquant.html' },
  { id: 'papers', title: '论文', icon: '📚', href: 'papers.html' },
  { id: 'projects', title: '项目', icon: '💻', href: 'projects.html' },
];

// Format helpers
function formatChange(pct) {
  if (pct == null) return '';
  const sign = pct >= 0 ? '+' : '';
  const cls = pct > 0 ? 'up' : pct < 0 ? 'down' : 'neutral';
  return `<span class="${cls}">${sign}${pct.toFixed(2)}%</span>`;
}

function formatNumber(n) {
  if (n == null) return '—';
  return n.toLocaleString('zh-CN');
}

function formatTime(isoStr) {
  if (!isoStr) return '—';
  const d = new Date(isoStr);
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function timeAgo(isoStr) {
  if (!isoStr) return '—';
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// Load JSON data
async function loadData(filename) {
  try {
    const resp = await fetch(`data/${filename}?t=${Date.now()}`);
    if (!resp.ok) return null;
    return await resp.json();
  } catch (e) {
    console.warn(`Failed to load ${filename}:`, e);
    return null;
  }
}

// Render navigation
function renderNav(activeId) {
  const nav = document.querySelector('.header nav');
  if (!nav) return;
  nav.innerHTML = PAGES.map(p =>
    `<a href="${p.href}" class="${p.id === activeId ? 'active' : ''}">${p.icon} ${p.title}</a>`
  ).join('');
}

// ECharts dark theme
const ECHARTS_THEME = {
  backgroundColor: 'transparent',
  textStyle: { color: '#8b949e' },
  title: { textStyle: { color: '#e6edf3' } },
  legend: { textStyle: { color: '#8b949e' } },
  xAxis: {
    axisLine: { lineStyle: { color: '#30363d' } },
    splitLine: { lineStyle: { color: '#21262d' } },
    axisLabel: { color: '#6e7681' },
  },
  yAxis: {
    axisLine: { lineStyle: { color: '#30363d' } },
    splitLine: { lineStyle: { color: '#21262d' } },
    axisLabel: { color: '#6e7681' },
  },
  tooltip: {
    backgroundColor: '#1c2128',
    borderColor: '#30363d',
    textStyle: { color: '#e6edf3' },
  },
};

function initChart(domId, option) {
  const el = document.getElementById(domId);
  if (!el) return null;
  const chart = echarts.init(el, null, { renderer: 'canvas' });
  const merged = { ...ECHARTS_THEME, ...option };
  // Deep merge axis styles
  if (merged.xAxis && !Array.isArray(merged.xAxis)) {
    merged.xAxis = { ...ECHARTS_THEME.xAxis, ...merged.xAxis };
  }
  if (merged.yAxis && !Array.isArray(merged.yAxis)) {
    merged.yAxis = { ...ECHARTS_THEME.yAxis, ...merged.yAxis };
  }
  chart.setOption(merged);
  window.addEventListener('resize', () => chart.resize());
  return chart;
}

// Signal badge
function signalBadge(signal) {
  const map = {
    long: ['signal-long', '做多'],
    short: ['signal-short', '做空'],
    neutral: ['signal-neutral', '观望'],
  };
  const [cls, label] = map[signal] || map.neutral;
  return `<span class="signal ${cls}">${label}</span>`;
}

// Star rating
function starRating(score) {
  return '★'.repeat(score) + '☆'.repeat(5 - score);
}
