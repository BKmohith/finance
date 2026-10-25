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

function post(path, body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const req = http.request({
      hostname: '127.0.0.1',
      port: 8000,
      path: path,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data)
      }
    }, (res) => {
      let respBody = '';
      res.on('data', chunk => respBody += chunk);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(respBody) });
        } catch (e) {
          resolve({ status: res.statusCode, body: respBody });
        }
      });
    });
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

async function testLoginFlow() {
  console.log('Testing login page content & auth endpoint...');
  const loginHtml = await get('/login.html');
  console.log('login.html status:', loginHtml.status);

  const hasGoogleBtn = loginHtml.body.includes('id="btnGoogleAuth"') && loginHtml.body.includes('Continue with Google');
  const hasEmailInput = loginHtml.body.includes('id="authEmailInput"') && loginHtml.body.includes('merchant@kirana.com');
  const hasLoginBtn = loginHtml.body.includes('id="btnAuthLogin"') && loginHtml.body.includes('Sign in / Login');
  const hasRegisterBtn = loginHtml.body.includes('id="btnAuthRegister"') && loginHtml.body.includes('Register Store');

  console.log('Google Auth button present:', hasGoogleBtn);
  console.log('Email input present:', hasEmailInput);
  console.log('Login button present:', hasLoginBtn);
  console.log('Register button present:', hasRegisterBtn);

  const loginApiRes = await post('/api/v1/auth/merchant-login', { email: 'merchant@kirana.com' });
  console.log('merchant-login API response:', loginApiRes);

  if (hasGoogleBtn && hasEmailInput && hasLoginBtn && hasRegisterBtn && loginApiRes.status === 200 && loginApiRes.data.status === 'success') {
    console.log('>>> ALL LOGIN FLOW TESTS PASSED! <<<');
  } else {
    console.error('>>> TEST FAILED! <<<');
  }
}

testLoginFlow().catch(console.error);
