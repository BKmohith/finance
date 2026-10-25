const http = require('http');

function checkURL(urlPath) {
  return new Promise((resolve) => {
    http.get(`http://127.0.0.1:8000${urlPath}`, (res) => {
      let body = '';
      res.on('data', (d) => (body += d));
      res.on('end', () => {
        resolve({ path: urlPath, status: res.statusCode, size: body.length });
      });
    }).on('error', (err) => resolve({ path: urlPath, error: err.message }));
  });
}

async function verifyAllAssets() {
  const urls = [
    '/dashboard.html',
    '/dashboard.html?merchant_id=M_LAKSHMI_JQ7T',
    '/css/dashboard.css',
    '/js/dashboard.js',
    '/api/v1/auth/metrics?merchant_id=M_LAKSHMI_JQ7T',
    '/api/counter/forecast?merchant_id=M_LAKSHMI_JQ7T&days=14'
  ];

  for (const u of urls) {
    const res = await checkURL(u);
    console.log(res);
  }
}

verifyAllAssets();
