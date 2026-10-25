const http = require('http');

function postJSON(path, payload) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(payload);
    const req = http.request(
      {
        hostname: '127.0.0.1',
        port: 8000,
        path: path,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data),
        },
      },
      (res) => {
        let body = '';
        res.on('data', (d) => (body += d));
        res.on('end', () => {
          try {
            resolve({ status: res.statusCode, data: JSON.parse(body) });
          } catch (e) {
            resolve({ status: res.statusCode, body });
          }
        });
      }
    );
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

function getJSON(path) {
  return new Promise((resolve, reject) => {
    http.get(`http://127.0.0.1:8000${path}`, (res) => {
      let body = '';
      res.on('data', (d) => (body += d));
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(body) });
        } catch (e) {
          resolve({ status: res.statusCode, body });
        }
      });
    }).on('error', reject);
  });
}

async function runTest() {
  const merchantId = 'M_LAKSHMI_JQ7T';
  console.log('Testing adjust metrics for:', merchantId);

  // 1. Post adjust metrics: Cash = 1250, UPI = 2750, Payables = 8200
  const postRes = await postJSON('/api/counter/metrics/adjust', {
    merchant_id: merchantId,
    cash_inflow: 1250.0,
    upi_inflow: 2750.0,
    sales_count: 5,
    payables_amount: 8200.0,
    supplier_name: 'Balaji Wholesale Distributors',
    due_date: '2026-11-05'
  });
  console.log('Adjust response:', postRes);

  // 2. Fetch metrics
  const getRes = await getJSON(`/api/v1/auth/metrics?merchant_id=${merchantId}`);
  console.log('Auth metrics response KPI summary:');
  console.log({
    today_inflow: getRes.data.kpis.today_inflow,
    cash_inflow: getRes.data.kpis.cash_inflow,
    upi_inflow: getRes.data.kpis.upi_inflow,
    sales_count: getRes.data.kpis.sales_count,
    payables_upcoming: getRes.data.kpis.payables_upcoming,
    payables_count: getRes.data.kpis.payables_count
  });

  // Verify assertions
  if (getRes.data.kpis.today_inflow === 4000 &&
      getRes.data.kpis.cash_inflow === 1250 &&
      getRes.data.kpis.upi_inflow === 2750 &&
      getRes.data.kpis.payables_upcoming === 8200) {
    console.log('>>> ALL METRICS ADJUST ASSERTIONS PASSED! <<<');
  } else {
    console.error('>>> MISMATCH IN METRICS VALUES! <<<');
  }
}

runTest().catch(console.error);
