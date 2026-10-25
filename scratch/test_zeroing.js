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

async function testZeroing() {
  const merchantId = 'M_LAKSHMI_JQ7T';
  console.log('Testing zeroing metrics for:', merchantId);

  const postRes = await postJSON('/api/counter/metrics/adjust', {
    merchant_id: merchantId,
    cash_inflow: 0.0,
    upi_inflow: 0.0,
    sales_count: 0,
    payables_amount: 0.0,
    supplier_name: 'Balaji Wholesale Distributors'
  });
  console.log('Zero adjust response:', postRes.data);

  const getRes = await getJSON(`/api/v1/auth/metrics?merchant_id=${merchantId}`);
  console.log('KPIs after zeroing:', getRes.data.kpis);

  if (getRes.data.kpis.today_inflow === 0 &&
      getRes.data.kpis.cash_inflow === 0 &&
      getRes.data.kpis.upi_inflow === 0 &&
      getRes.data.kpis.payables_upcoming === 0 &&
      getRes.data.kpis.payables_count === 0) {
    console.log('>>> ZEROING TEST PASSED PERFECTLY! <<<');
  } else {
    console.error('>>> ZEROING FAILED! <<<');
  }
}

testZeroing().catch(console.error);
