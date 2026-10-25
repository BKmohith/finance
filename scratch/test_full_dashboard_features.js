const http = require('http');

function request(method, path, data = null, isForm = false) {
  return new Promise((resolve, reject) => {
    let postData = '';
    const headers = {};
    if (data) {
      if (isForm) {
        // Simple urlencoded form
        postData = new URLSearchParams(data).toString();
        headers['Content-Type'] = 'application/x-www-form-urlencoded';
        headers['Content-Length'] = Buffer.byteLength(postData);
      } else {
        postData = JSON.stringify(data);
        headers['Content-Type'] = 'application/json';
        headers['Content-Length'] = Buffer.byteLength(postData);
      }
    }

    const req = http.request({
      hostname: '127.0.0.1',
      port: 8000,
      path: path,
      method: method,
      headers: headers
    }, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(body) });
        } catch (e) {
          resolve({ status: res.statusCode, raw: body });
        }
      });
    });

    req.on('error', reject);
    if (postData) req.write(postData);
    req.end();
  });
}

async function runTests() {
  console.log('--- TEST 1: Initial Zero Stock Verification ---');
  let res = await request('GET', '/api/v1/auth/metrics?merchant_id=M_LAKSHMI_JQ7T');
  console.log('Status:', res.status);
  console.log('Stock items count:', res.data.inventory.length);
  if (res.data.inventory.length !== 0) {
    console.error('FAILED: Stock is not 0 for new user');
  } else {
    console.log('PASSED: Stock is strictly 0 for new user!');
  }

  console.log('\n--- TEST 2: Update Store Profile (Universal Edit 1) ---');
  res = await request('POST', '/api/v1/auth/merchant-update', {
    merchant_id: 'M_LAKSHMI_JQ7T',
    business_name: 'Lakshmi Super Kirana & General Store',
    city: 'Malleshwaram 8th Cross, Bengaluru',
    phone: '+919845099887',
    gstin: '29AABCS1429B1ZB'
  });
  console.log('Update Store:', res.data.status, res.data.business_name, res.data.city);

  console.log('\n--- TEST 3: Scan Distributor Invoice to Stock Shelves ---');
  res = await request('POST', '/api/counter/scan-invoice', {
    merchant_id: 'M_LAKSHMI_JQ7T',
    template: 'wholesale'
  }, true);
  console.log('Scan Result:', res.data.status, res.data.message);

  console.log('\n--- TEST 4: Verify Shelves Now Have Items After Scan ---');
  res = await request('GET', '/api/v1/auth/metrics?merchant_id=M_LAKSHMI_JQ7T');
  console.log('Stock items count after scan:', res.data.inventory.length);
  console.log('Items on shelf:', res.data.inventory.map(i => `${i.item_name} (Stock: ${i.quantity}, ₹${i.retail_mrp})`));
  console.log('Upcoming payables count:', res.data.payables.length);

  console.log('\n--- TEST 5: Edit Product on Shelf (Universal Edit 2) ---');
  res = await request('POST', '/api/counter/inventory/update', {
    merchant_id: 'M_LAKSHMI_JQ7T',
    item_name: 'Fortune Sunflower Oil 1L',
    retail_mrp: 175.0,
    cost_price: 142.0,
    quantity: 45.0,
    unit: 'litres',
    batch_number: 'BATCH-2026-EDIT'
  });
  console.log('Product Edit Result:', res.data.status, res.data.item);

  console.log('\n--- TEST 6: Edit Customer Khata (Universal Edit 3) ---');
  res = await request('POST', '/api/counter/khata/customer/update', {
    merchant_id: 'M_LAKSHMI_JQ7T',
    customer_name: 'Ramesh Gowda',
    customer_phone: '9845011223',
    current_balance: 650.0,
    notes: 'Regular store credit buyer'
  });
  console.log('Customer Khata Edit Result:', res.data.status, res.data.customer);

  console.log('\n--- TEST 7: Edit Supplier Invoice (Universal Edit 4) ---');
  if (res.data && res.data.payables && res.data.payables.length > 0) {
    const inv = res.data.payables[0];
    res = await request('POST', '/api/counter/invoice/update', {
      merchant_id: 'M_LAKSHMI_JQ7T',
      invoice_number: inv.invoice_number,
      supplier_name: 'Sri Balaji Wholesale (Updated)',
      amount: 15500.0,
      credit_due_date: '2026-11-15',
      status: 'LOGGED'
    });
    console.log('Invoice Edit Result:', res.data.status, res.data.invoice);
  }

  console.log('\n--- TEST 8: Reset Shelf Stock to 0 (Merchant Fresh Start) ---');
  res = await request('POST', '/api/counter/inventory/clear-all', {
    merchant_id: 'M_LAKSHMI_JQ7T'
  });
  console.log('Clear All Result:', res.data.status, 'Cleared batches:', res.data.cleared_batches);

  console.log('\n--- TEST 9: Verify Final Shelf Stock is strictly 0 ---');
  res = await request('GET', '/api/v1/auth/metrics?merchant_id=M_LAKSHMI_JQ7T');
  console.log('Final stock items count:', res.data.inventory.length);
  if (res.data.inventory.length === 0) {
    console.log('PASSED: Shelf stock is completely 0 for merchant as demanded!');
  } else {
    console.error('FAILED: Stock is not 0');
  }
}

runTests().catch(console.error);
