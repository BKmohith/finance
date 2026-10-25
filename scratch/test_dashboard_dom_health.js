const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

async function testDashboardDOM() {
  console.log('Testing dashboard DOM health and script evaluation...');
  const htmlPath = path.join(__dirname, '..', 'frontend', 'dashboard.html');
  const jsPath = path.join(__dirname, '..', 'frontend', 'js', 'dashboard.js');

  const html = fs.readFileSync(htmlPath, 'utf8');
  const js = fs.readFileSync(jsPath, 'utf8');

  const dom = new JSDOM(html, {
    runScripts: 'outside-only',
    url: 'http://localhost:8000/dashboard.html?merchant_id=M_LAKSHMI_JQ7T',
  });

  const { window } = dom;

  // Mock necessary browser APIs in JSDOM
  window.AudioContext = class {
    createOscillator() { return { type: '', frequency: { setValueAtTime: () => {} }, connect: () => {}, start: () => {}, stop: () => {} }; }
    createGain() { return { gain: { setValueAtTime: () => {}, exponentialRampToValueAtTime: () => {} }, connect: () => {} }; }
    get destination() { return {}; }
    get currentTime() { return 0; }
  };
  window.alert = (msg) => console.log('[MOCK ALERT]:', msg);
  window.fetch = async (url, opts) => {
    return {
      ok: true,
      json: async () => ({ status: 'success', kpis: { today_inflow: 0, cash_inflow: 0, upi_inflow: 0, sales_count: 0 }, inventory: [] })
    };
  };

  const errors = [];
  window.addEventListener('error', (e) => {
    errors.push(e.error || e.message);
  });

  try {
    window.eval(js);
    window.document.dispatchEvent(new window.Event('DOMContentLoaded'));
  } catch (err) {
    console.error('CRITICAL RUNTIME ERROR in dashboard.js:', err);
    process.exit(1);
  }

  if (errors.length > 0) {
    console.error('Errors caught during initialization:', errors);
    process.exit(1);
  }

  // Check header elements
  const btnEditMetrics = window.document.getElementById('btnEditMetricsHeader');
  const storeBadge = window.document.getElementById('storeLiveBadge');
  const modalEditMetrics = window.document.getElementById('modalEditMetrics');

  console.log('btnEditMetricsHeader exists?', !!btnEditMetrics);
  console.log('storeBadge exists?', !!storeBadge);
  console.log('modalEditMetrics exists?', !!modalEditMetrics);

  if (!btnEditMetrics) {
    console.error('btnEditMetricsHeader not found in DOM!');
    process.exit(1);
  }

  // Test opening modal
  btnEditMetrics.click();
  console.log('Modal display after click:', modalEditMetrics.style.display);
  if (modalEditMetrics.style.display !== 'flex') {
    console.error('Modal failed to open on click!');
    process.exit(1);
  }

  console.log('>>> ALL DASHBOARD DOM & SCRIPT TESTS PASSED! <<<');
}

testDashboardDOM().catch((err) => {
  console.error(err);
  process.exit(1);
});
