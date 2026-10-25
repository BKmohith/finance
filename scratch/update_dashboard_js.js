const fs = require('fs');
const path = require('path');

const jsPath = path.join(__dirname, '..', 'frontend', 'js', 'dashboard.js');
let code = fs.readFileSync(jsPath, 'utf8');

// 1. Update live mapping in loadLiveDashboardMetrics
const oldMapping = `      if (data.inventory && data.inventory.length > 0) {
        catalogData = data.inventory.map((item, idx) => ({
          id: 'item_' + idx,
          name: item.item_name,
          category: 'all',
          price: item.retail_mrp || Math.round(item.cost_price * 1.15),
          stock: item.quantity,
          batch: item.batch_number || 'FIFO-01',
          unit: item.unit
        }));
      } else {
        catalogData = [];
      }`;

const newMapping = `      if (data.inventory && data.inventory.length > 0) {
        catalogData = data.inventory.map((item, idx) => ({
          id: item.id || ('item_' + idx),
          batch_id: item.id || '',
          name: item.item_name,
          category: 'all',
          price: item.retail_mrp || Math.round(item.cost_price * 1.15),
          cost: item.cost_price || 0,
          stock: item.quantity,
          batch: item.batch_number || 'FIFO-01',
          unit: item.unit || 'units'
        }));
      } else {
        catalogData = [];
      }`;

if (code.includes(oldMapping)) {
  code = code.replace(oldMapping, newMapping);
  console.log('Updated catalogData mapping');
} else {
  console.log('oldMapping not found, check lines manually');
}

// 2. Update renderKhataTable action cell
const oldKhataAction = `        <td>
          <button type="button" class="btn-action-sm" onclick="dispatchKhataWhatsApp('\${safeName}', '\${safePhone}', \${balance})">
            📲 Send WhatsApp
          </button>
        </td>`;

const newKhataAction = `        <td>
          <div style="display: flex; gap: 5px; align-items: center; justify-content: flex-start; flex-wrap: wrap;">
            <button type="button" class="btn-action-sm btn-repay" onclick="openRepayModal('\${safeName}', \${balance})">
              Repay
            </button>
            <button type="button" class="btn-action-sm" onclick="dispatchKhataWhatsApp('\${safeName}', '\${safePhone}', \${balance})">
              📲 WhatsApp
            </button>
            <button type="button" class="btn-action-sm btn-edit-cust" style="color: var(--color-accent-purple); font-weight: 600;" onclick="openEditCustomerModal('\${safeName}', '\${safePhone}', \${balance})">
              ✏️ Edit
            </button>
          </div>
        </td>`;

if (code.includes(oldKhataAction)) {
  code = code.replace(oldKhataAction, newKhataAction);
  console.log('Updated renderKhataTable action cell');
} else {
  console.log('oldKhataAction not found, checking alternatives');
}

// 3. Update renderCatalog zero-state and product card
const oldRenderCatalogZero = `    if (catalogData.length === 0) {
      catalogGrid.innerHTML = \`
        <div style="grid-column: 1/-1; text-align: center; color: var(--color-text-muted); padding: 48px 16px; background: #FAF7F2; border-radius: var(--radius-item);">
          <div style="font-size: 2.4rem; margin-bottom: 8px;">📦</div>
          <div style="font-weight: 700; font-size: 1.05rem; color: var(--color-text-title);">Shelf Inventory Empty (0 Stock)</div>
          <div style="font-size: 0.85rem; margin-top: 6px; max-width: 440px; margin-left: auto; margin-right: auto; line-height: 1.5;">
            All new merchant shelves start at zero stock. Send a photo of your wholesale distributor invoice to Telegram (<strong>@sahayak_retail_bot</strong>) or WhatsApp to automatically stock items via Gemini Flash OCR, or use <strong>Quick Presets (+₹50, +₹100)</strong> above for manual counter sales.
          </div>
        </div>
      \`;
      return;
    }`;

const newRenderCatalogZero = `    if (catalogData.length === 0) {
      catalogGrid.innerHTML = \`
        <div class="zero-stock-box">
          <div style="font-size: 2.6rem; margin-bottom: 8px;">📦</div>
          <div style="font-weight: 700; font-size: 1.15rem; color: var(--color-text-title); margin-bottom: 6px;">Shelf Inventory Empty (0 Stock)</div>
          <div style="font-size: 0.85rem; line-height: 1.5; max-width: 480px; margin: 0 auto 18px auto; color: var(--color-text-muted);">
            All new merchant shelves start strictly at 0 stock. Scan your wholesale distributor invoice via camera or upload to automatically stock items, or enter products manually.
          </div>
          <div style="display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
            <button type="button" class="btn-pill-dark" onclick="openScanInvoiceModal()">
              📷 Scan Distributor Invoice to Stock
            </button>
            <button type="button" class="btn-pill-light" onclick="openEditProductModal(null)">
              + Add Product Manually
            </button>
          </div>
        </div>
      \`;
      return;
    }`;

if (code.includes(oldRenderCatalogZero)) {
  code = code.replace(oldRenderCatalogZero, newRenderCatalogZero);
  console.log('Updated renderCatalog zero-state');
} else {
  console.log('oldRenderCatalogZero not found');
}

// 4. Update product card header inside renderCatalog
const oldCardHeader = `        <div class="prod-card-header">
          <span class="prod-batch-tag">\${item.batch}</span>
          <span class="prod-stock-badge">Stock: \${item.stock}</span>
        </div>`;

const newCardHeader = `        <div class="prod-card-header">
          <span class="prod-batch-tag">\${item.batch}</span>
          <div style="display: flex; gap: 5px; align-items: center;">
            <span class="prod-stock-badge">Stock: \${item.stock}</span>
            <button type="button" class="prod-edit-btn" title="Edit Product Details & Stock" onclick="event.stopPropagation(); openEditProductModalById('\${item.id}')">✏️</button>
          </div>
        </div>`;

if (code.includes(oldCardHeader)) {
  code = code.replace(oldCardHeader, newCardHeader);
  console.log('Updated product card header with edit button');
} else {
  console.log('oldCardHeader not found');
}

fs.writeFileSync(jsPath, code, 'utf8');
console.log('Saved partial dashboard.js updates');
