const fs = require('fs');
const path = require('path');

// 1. UPDATE DASHBOARD.HTML
const htmlPath = path.join(__dirname, '..', 'frontend', 'dashboard.html');
let html = fs.readFileSync(htmlPath, 'utf8');

// A. Remove btnScanInvoiceToolbar from catalog-action-strip
const oldToolbar = `            <!-- Shelf Catalog Actions Toolbar -->
            <div class="catalog-action-strip" style="display: flex; gap: 8px; margin: 12px 0; align-items: center; justify-content: space-between; flex-wrap: wrap;">
              <div style="display: flex; gap: 8px; align-items: center;">
                <button type="button" id="btnScanInvoiceToolbar" class="btn-pill-dark" style="font-size: 0.8rem; padding: 6px 12px; display: inline-flex; align-items: center; gap: 5px;">
                  <span>📷</span> <span>Scan Invoice to Stock</span>
                </button>
                <button type="button" id="btnAddProductToolbar" class="btn-pill-light" style="font-size: 0.8rem; padding: 6px 12px; display: inline-flex; align-items: center; gap: 5px;">
                  <span>+</span> <span>Add Product</span>
                </button>
              </div>
              <button type="button" id="btnClearStockToolbar" class="btn-action-sm" style="font-size: 0.72rem; color: var(--color-accent-coral); border: 1px solid rgba(224, 86, 36, 0.25); background: rgba(224, 86, 36, 0.05); padding: 5px 9px;" title="Reset active merchant shelf stock to 0">
                Reset Shelf to 0
              </button>
            </div>`;

const newToolbar = `            <!-- Shelf Catalog Actions Toolbar -->
            <div class="catalog-action-strip" style="display: flex; gap: 8px; margin: 12px 0; align-items: center; justify-content: space-between; flex-wrap: wrap;">
              <div style="display: flex; gap: 8px; align-items: center;">
                <button type="button" id="btnAddProductToolbar" class="btn-pill-dark" style="font-size: 0.8rem; padding: 6px 14px; display: inline-flex; align-items: center; gap: 5px;">
                  <span>+</span> <span>Add Product to Shelf</span>
                </button>
              </div>
              <button type="button" id="btnClearStockToolbar" class="btn-action-sm" style="font-size: 0.72rem; color: var(--color-accent-coral); border: 1px solid rgba(224, 86, 36, 0.25); background: rgba(224, 86, 36, 0.05); padding: 5px 9px;" title="Reset active merchant shelf stock to 0">
                Reset Shelf to 0
              </button>
            </div>`;

if (html.includes(oldToolbar)) {
  html = html.replace(oldToolbar, newToolbar);
  console.log('Removed btnScanInvoiceToolbar from dashboard.html');
} else {
  console.log('oldToolbar not matched exactly, checking substring');
}

// B. Remove btnScanInvoicePayables from MarginGuard tab
const oldPayablesHeader = `            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 8px;">
              <h3 style="font-size: 1.25rem; font-weight: 700; color: var(--color-text-title);">
                Supplier Invoices &amp; Payables (Agent 2)
              </h3>
              <button type="button" id="btnScanInvoicePayables" class="btn-pill-dark" style="font-size: 0.78rem; padding: 5px 12px;">
                📷 Scan Invoice
              </button>
            </div>`;

const newPayablesHeader = `            <div style="margin-bottom: 6px;">
              <h3 style="font-size: 1.25rem; font-weight: 700; color: var(--color-text-title);">
                Supplier Invoices &amp; Payables (Agent 2)
              </h3>
            </div>`;

if (html.includes(oldPayablesHeader)) {
  html = html.replace(oldPayablesHeader, newPayablesHeader);
  console.log('Removed btnScanInvoicePayables from dashboard.html');
} else {
  console.log('oldPayablesHeader not matched');
}

// C. Update Margin Spike subtitle text
html = html.replace(
  'Automatically calculated upon 9-pin dot-matrix invoice scanning. Prevents silent margin erosion.',
  'Automatically calculated from supplier rate histories. Prevents silent margin erosion.'
);

// D. Remove modalScanInvoice completely
const scanModalIndex = html.indexOf('<!-- ====================================================================\n       MODAL 5: SCAN DISTRIBUTOR INVOICE TO STOCK SHELF');
const nextSectionIndex = html.indexOf('<!-- ====================================================================\n       CORNER FLOATING VERNACULAR VOICE COPILOT');

if (scanModalIndex !== -1 && nextSectionIndex !== -1) {
  html = html.slice(0, scanModalIndex) + html.slice(nextSectionIndex);
  console.log('Removed modalScanInvoice from dashboard.html');
} else {
  console.log('Could not find slice boundaries for modalScanInvoice');
}

fs.writeFileSync(htmlPath, html, 'utf8');

// 2. UPDATE DASHBOARD.JS
const jsPath = path.join(__dirname, '..', 'frontend', 'js', 'dashboard.js');
let js = fs.readFileSync(jsPath, 'utf8');

// A. Update payables empty state in renderMarginGuard
const oldPayablesZero = `      if (payables.length === 0) {
        payablesContainer.innerHTML = \`
          <div style="text-align: center; padding: 40px 16px; color: var(--color-text-muted); background: #FAF7F2; border-radius: var(--radius-item);">
            <div style="font-size: 2.4rem; margin-bottom: 8px;">📦</div>
            <div style="font-weight: 700; font-size: 1.05rem; color: var(--color-text-title);">Zero Upcoming Payables</div>
            <div style="font-size: 0.85rem; margin-top: 6px; line-height: 1.5; max-width: 420px; margin-left: auto; margin-right: auto;">
              No distributor payments currently pending. Scan wholesale invoices to track credit windows and protect liquidity.
            </div>
            <button type="button" class="btn-pill-dark" style="margin-top: 14px; font-size: 0.82rem;" onclick="openScanInvoiceModal()">
              📷 Scan Wholesale Invoice
            </button>
          </div>
        \`;
      }`;

const newPayablesZero = `      if (payables.length === 0) {
        payablesContainer.innerHTML = \`
          <div style="text-align: center; padding: 40px 16px; color: var(--color-text-muted); background: #FAF7F2; border-radius: var(--radius-item);">
            <div style="font-size: 2.4rem; margin-bottom: 8px;">📦</div>
            <div style="font-weight: 700; font-size: 1.05rem; color: var(--color-text-title);">Zero Upcoming Payables</div>
            <div style="font-size: 0.85rem; margin-top: 6px; line-height: 1.5; max-width: 420px; margin-left: auto; margin-right: auto;">
              No distributor payments currently pending. All supplier invoices and credit windows are settled.
            </div>
          </div>
        \`;
      }`;

if (js.includes(oldPayablesZero)) {
  js = js.replace(oldPayablesZero, newPayablesZero);
  console.log('Updated payables empty state in dashboard.js');
} else {
  console.log('oldPayablesZero not matched');
}

// B. Update renderCatalog zero-state
const oldCatalogZero = `    if (catalogData.length === 0) {
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

const newCatalogZero = `    if (catalogData.length === 0) {
      catalogGrid.innerHTML = \`
        <div class="zero-stock-box">
          <div style="font-size: 2.6rem; margin-bottom: 8px;">📦</div>
          <div style="font-weight: 700; font-size: 1.15rem; color: var(--color-text-title); margin-bottom: 6px;">Shelf Inventory Empty (0 Stock)</div>
          <div style="font-size: 0.85rem; line-height: 1.5; max-width: 480px; margin: 0 auto 18px auto; color: var(--color-text-muted);">
            All new merchant shelves start strictly at 0 stock. Add your products manually to start counter sales and track inventory.
          </div>
          <div style="display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
            <button type="button" class="btn-pill-dark" onclick="openEditProductModal(null)">
              + Add Product to Shelf
            </button>
          </div>
        </div>
      \`;
      return;
    }`;

if (js.includes(oldCatalogZero)) {
  js = js.replace(oldCatalogZero, newCatalogZero);
  console.log('Updated catalog zero-state in dashboard.js');
} else {
  console.log('oldCatalogZero not matched');
}

// C. Update confirm message on reset shelf
js = js.replace(
  `if (!confirm('Are you sure you want to reset all shelf stock to 0? This enables new merchants to start fresh and populate stock strictly by scanning distributor invoices.')) return;`,
  `if (!confirm('Are you sure you want to reset all shelf stock to 0?')) return;`
);

// D. Remove invoice scan modal functions and event listeners from dashboard.js
const scanJsStart = js.indexOf('  // --- E. INVOICE SCAN & VISION POPULATION MODAL ---');
const scanJsEnd = js.indexOf('  // 16. Initial Invocations & Real-Time Sync Polling');

if (scanJsStart !== -1 && scanJsEnd !== -1) {
  const replacementJs = `  const btnAddProductToolbar = document.getElementById('btnAddProductToolbar');
  if (btnAddProductToolbar) {
    btnAddProductToolbar.addEventListener('click', () => window.openEditProductModal(null));
  }

  `;
  js = js.slice(0, scanJsStart) + replacementJs + js.slice(scanJsEnd);
  console.log('Removed scan modal handlers from dashboard.js');
} else {
  console.log('Could not find slice boundaries for scan modal in dashboard.js');
}

fs.writeFileSync(jsPath, js, 'utf8');
console.log('All scan invoice references successfully removed!');
