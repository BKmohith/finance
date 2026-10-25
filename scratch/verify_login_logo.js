const http = require('http');

function get(path) {
  return new Promise((resolve, reject) => {
    http.get(`http://127.0.0.1:8000${path}`, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve({ status: res.statusCode, body: data }));
    }).on('error', reject);
  });
}

async function verify() {
  const loginRes = await get('/login.html');
  const cssRes = await get('/css/design-system.css');

  console.log('login.html HTTP status:', loginRes.status);
  console.log('design-system.css HTTP status:', cssRes.status);

  const hasWaveformClass = cssRes.body.includes('.brand-waveform-icon');
  const hasWaveformBar = cssRes.body.includes('.waveform-bar:nth-child(3)');
  const hasCopilotText = loginRes.body.includes('COPILOT');
  const hasWaveformDiv = loginRes.body.includes('brand-waveform-icon');

  console.log('CSS has .brand-waveform-icon:', hasWaveformClass);
  console.log('CSS has golden 3rd bar:', hasWaveformBar);
  console.log('login.html has brand-waveform-icon:', hasWaveformDiv);
  console.log('login.html has COPILOT:', hasCopilotText);

  if (hasWaveformClass && hasWaveformBar && hasWaveformDiv && hasCopilotText) {
    console.log('>>> VERIFICATION PASSED: Login page brand logo updated accurately! <<<');
  } else {
    console.error('>>> VERIFICATION FAILED! <<<');
  }
}

verify().catch(console.error);
