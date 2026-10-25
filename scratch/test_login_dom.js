const fs = require('fs');

// Read frontend/login.html
const html = fs.readFileSync('frontend/login.html', 'utf8');

// Mock localStorage
const storage = {};
const localStorage = {
  getItem: (k) => storage[k] || null,
  setItem: (k, v) => { storage[k] = String(v); },
  removeItem: (k) => { delete storage[k]; }
};

// Mock Elements
class MockElement {
  constructor(id, tag = 'div') {
    this.id = id;
    this.tagName = tag.toUpperCase();
    this.className = '';
    this.classList = {
      add: (c) => { if (!this.className.includes(c)) this.className = (this.className + ' ' + c).trim(); },
      remove: (c) => { this.className = this.className.replace(new RegExp('\\b' + c + '\\b', 'g'), '').trim(); },
      contains: (c) => this.className.includes(c)
    };
    this.textContent = '';
    this.innerHTML = '';
    this.value = '';
    this.src = '';
    this.href = '';
    this.style = {};
    this.listeners = {};
  }
  addEventListener(event, fn) {
    this.listeners[event] = fn;
  }
  async dispatchEvent(event, evData = {}) {
    if (this.listeners[event]) {
      await this.listeners[event]({ preventDefault: () => {}, ...evData });
    }
  }
}

const elements = {};
function getElementById(id) {
  if (!elements[id]) {
    elements[id] = new MockElement(id);
  }
  return elements[id];
}

// Simulated User JWT Payload from Google OAuth
const payload = {
  sub: '90458b61-fc98-4f22-b1a5-1fc4dcd13720',
  email: 'mohithbt18@gmail.com',
  user_metadata: {
    full_name: 'Mohith B K',
    name: 'Mohith B K',
    avatar_url: 'https://lh3.googleusercontent.com/a/ACg8ocLHb5LPJDnrowux3qfAeu1l8jODHp8xQAWODVS11d1fHeZ6_giV=s96-c'
  },
  role: 'authenticated',
  exp: Math.floor(Date.now() / 1000) + 3600
};
const dummyToken = 'eyJhbGciOiJIUzI1NiJ9.' + Buffer.from(JSON.stringify(payload)).toString('base64url') + '.simulated_sig';

// Mock Window & Document
const windowObj = {
  location: {
    origin: 'http://localhost:8000',
    pathname: '/login.html',
    hash: `#access_token=${dummyToken}&expires_at=${payload.exp}&expires_in=3600&refresh_token=test_refresh&token_type=bearer`
  },
  history: {
    replaceState: (state, title, url) => {
      windowObj.location.hash = '';
      windowObj.location.pathname = url;
    }
  },
  supabase: {
    createClient: () => ({
      auth: {
        getSession: async () => ({ data: { session: null }, error: new Error('Invalid API key') }),
        onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } })
      }
    })
  }
};

// Mock fetch for onboarding API
global.fetch = async (url, opts) => {
  if (url === '/api/v1/auth/merchant-onboard') {
    const body = JSON.parse(opts.body);
    return {
      ok: true,
      json: async () => ({
        status: 'success',
        merchant_id: 'M_MOHITH_98AB',
        business_name: body.business_name,
        telegram_activation_url: 'https://t.me/sahayak_retail_bot?start=M_MOHITH_98AB',
        telegram_qr_code_url: 'https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=test'
      })
    };
  }
  return { ok: false };
};

// Extract and execute the script from login.html in our simulated browser context
const scripts = html.match(/<script[\s\S]*?<\/script>/gi);
const inlineScript = scripts[1].replace(/<\/?script>/gi, '');

// Run script
const contextFunc = new Function(
  'window', 'document', 'localStorage', 'navigator', 'atob',
  inlineScript
);

console.log('--- EXECUTING LOGIN.HTML SCRIPT WITH OAUTH REDIRECT HASH ---');
contextFunc(
  windowObj,
  {
    getElementById: (id) => getElementById(id)
  },
  localStorage,
  { clipboard: { writeText: async () => {} } },
  atob
);

// Allow async checkExistingAuth to settle
setTimeout(async () => {
  console.log('\n[ASSERTION 1] Checking Step 2 is active:');
  const panel2 = getElementById('panelStep2');
  console.log('Panel 2 Class:', panel2.className);
  if (!panel2.className.includes('active')) throw new Error('Panel 2 is not active');

  console.log('\n[ASSERTION 2] Checking User Details Populated from JWT:');
  const email = getElementById('chipEmail').textContent;
  const name = getElementById('chipName').textContent;
  const ownerInput = getElementById('ownerName').value;
  const businessInput = getElementById('businessName').value;

  console.log('Chip Email:', email);
  console.log('Chip Name:', name);
  console.log('Owner Input Value:', ownerInput);
  console.log('Business Name Input Value:', businessInput);

  if (email !== 'mohithbt18@gmail.com') throw new Error('Email was not extracted correctly');
  if (name !== 'Mohith B K') throw new Error('Name was not extracted correctly');
  if (ownerInput !== 'Mohith B K') throw new Error('Owner name input was not pre-filled');

  console.log('\n[ASSERTION 3] Checking URL Hash Fragment Sanitization (No Token Exposure):');
  console.log('Remaining window.location.hash:', JSON.stringify(windowObj.location.hash));
  if (windowObj.location.hash !== '') throw new Error('Access token was not wiped from hash fragment!');

  console.log('\n[ASSERTION 4] Checking LocalStorage Session Persistence:');
  const savedUser = JSON.parse(storage['sahayak_auth_user']);
  console.log('Saved User in LocalStorage:', savedUser);
  if (savedUser.email !== 'mohithbt18@gmail.com') throw new Error('User not saved in localStorage');

  console.log('\n[ASSERTION 5] Simulating Step 2 Form Submission -> Step 3 Activation:');
  getElementById('ownerPhone').value = '9845012345';
  await getElementById('onboardForm').dispatchEvent('submit');

  const panel3 = getElementById('panelStep3');
  console.log('Panel 3 Class:', panel3.className);
  console.log('Display Merchant ID:', getElementById('displayMerchantId').textContent);
  console.log('Telegram Link:', getElementById('btnTelegramLink').href);

  if (!panel3.className.includes('active')) throw new Error('Panel 3 did not activate after onboarding');
  if (getElementById('displayMerchantId').textContent !== 'M_MOHITH_98AB') throw new Error('Merchant ID not displayed');

  console.log('\n🎉 ALL 5 OAUTH LOGIN & ONBOARDING DOM ASSERTIONS PASSED 100%!');
}, 50);
