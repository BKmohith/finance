const fs = require('fs');
const path = require('path');

const jsPath = path.join(__dirname, '..', 'frontend', 'js', 'dashboard.js');
let code = fs.readFileSync(jsPath, 'utf8');

// 1. Update renderMarginGuard to include Payables column & custom edit on margin alerts
const oldRenderMarginGuardEnd = `    } else {
      deadCapital.slice(0, 4).forEach(item => {
        const box = document.createElement('div');
        box.style.cssText = 'background: #FAF7F2; border: 1px solid rgba(24, 21, 19, 0.08); border-radius: var(--radius-item); padding: 16px; margin-bottom: 12px;';
        box.innerHTML = \`
          <div style="display: flex; justify-content: space-between; align-items: baseline;">
            <strong style="color: var(--color-text-title);">\${item.item_name}</strong>
            <span class="status-pill-warn" style="font-size: 0.75rem;">₹\${item.locked_capital.toLocaleString('en-IN')} Capital</span>
          </div>
          <div style="font-size: 0.82rem; color: var(--color-text-muted); margin-top: 4px;">
            Batch #\${item.batch_number} • \${item.quantity} \${item.unit} in stock @ ₹\${item.cost_price.toFixed(2)} cost
          </div>
          <div style="font-size: 0.8rem; color: var(--color-accent-purple); font-weight: 500; margin-top: 8px;">
            💡 Copilot Tip: Prioritize at counter register to accelerate inventory velocity.
          </div>
        \`;
        deadContainer.appendChild(box);
      });
    }
  }`;

const newRenderMarginGuardEnd = `    } else {
      deadCapital.slice(0, 4).forEach(item => {
        const box = document.createElement('div');
        box.style.cssText = 'background: #FAF7F2; border: 1px solid rgba(24, 21, 19, 0.08); border-radius: var(--radius-item); padding: 16px; margin-bottom: 12px;';
        box.innerHTML = \`
          <div style="display: flex; justify-content: space-between; align-items: baseline;">
            <strong style="color: var(--color-text-title);">\${item.item_name}</strong>
            <span class="status-pill-warn" style="font-size: 0.75rem;">₹\${item.locked_capital.toLocaleString('en-IN')} Capital</span>
          </div>
          <div style="font-size: 0.82rem; color: var(--color-text-muted); margin-top: 4px;">
            Batch #\${item.batch_number} • \${item.quantity} \${item.unit} in stock @ ₹\${item.cost_price.toFixed(2)} cost
          </div>
          <div style="font-size: 0.8rem; color: var(--color-accent-purple); font-weight: 500; margin-top: 8px;">
            💡 Copilot Tip: Prioritize at counter register to accelerate inventory velocity.
          </div>
        \`;
        deadContainer.appendChild(box);
      });
    }

    // 3. Supplier Payables Column (With Edit Capability)
    const payablesContainer = document.getElementById('supplierPayablesContainer');
    if (payablesContainer) {
      payablesContainer.innerHTML = '';
      const payables = data.payables || [];
      if (payables.length === 0) {
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
      } else {
        payables.forEach(inv => {
          const card = document.createElement('div');
          card.className = 'payable-invoice-card';
          const safeSupp = (inv.supplier || '').replace(/'/g, "\\\\'");
          const safeNum = (inv.invoice_number || '').replace(/'/g, "\\\\'");
          card.innerHTML = \`
            <div>
              <div style="font-weight: 700; color: var(--color-text-title); font-size: 0.95rem;">\${inv.supplier}</div>
              <div style="font-size: 0.78rem; color: var(--color-text-muted); margin-top: 2px;">
                Bill #\${inv.invoice_number} • Due: <strong style="color: var(--color-accent-purple);">\${inv.due_date}</strong>
                <span class="mono-tag" style="margin-left: 6px; font-size: 0.7rem;">\${inv.status || 'LOGGED'}</span>
              </div>
            </div>
            <div style="display: flex; align-items: center; gap: 10px;">
              <span class="mono-tag" style="font-size: 1.05rem; font-weight: 700; color: var(--color-accent-coral);">
                ₹\${inv.amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <button type="button" class="btn-action-sm btn-edit-inv" title="Edit Invoice Amount or Due Date" onclick="openEditInvoiceModal('\${safeNum}', '\${safeSupp}', \${inv.amount}, '\${inv.due_date_raw || ''}', '\${inv.status || 'LOGGED'}')">
                ✏️ Edit
              </button>
            </div>
          \`;
          payablesContainer.appendChild(card);
        });
      }
    }
  }`;

if (code.includes(oldRenderMarginGuardEnd)) {
  code = code.replace(oldRenderMarginGuardEnd, newRenderMarginGuardEnd);
  console.log('Updated renderMarginGuard with Payables column');
} else {
  console.log('oldRenderMarginGuardEnd not matched directly');
}

// 2. Add Modal Handlers and Universal Edit Logic before end of DOMContentLoaded
const endTag = `  // 16. Initial Invocations & Real-Time Sync Polling`;

const modalHandlersCode = `  // ====================================================================
  // UNIVERSAL DASHBOARD EDIT & INVENTORY SCANNING HANDLERS
  // ====================================================================

  // Modal Overlay Closer Helper
  function closeModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) {
      el.classList.remove('active');
      el.style.display = 'none';
    }
  }

  function showModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) {
      el.style.display = 'flex';
      el.classList.add('active');
    }
  }

  // --- A. EDIT STORE PROFILE ---
  window.openEditStoreModal = function() {
    const editStoreName = document.getElementById('editStoreName');
    const editStoreCity = document.getElementById('editStoreCity');
    const editStorePhone = document.getElementById('editStorePhone');
    const editStoreGstin = document.getElementById('editStoreGstin');

    if (editStoreName) editStoreName.value = merchantData ? (merchantData.business_name || '') : 'Retail Store';
    if (editStoreCity) editStoreCity.value = merchantData ? (merchantData.city || '') : 'Bengaluru';
    if (editStorePhone) editStorePhone.value = merchantData ? (merchantData.phone || '') : '';
    if (editStoreGstin) editStoreGstin.value = merchantData ? (merchantData.gstin || '') : '';

    showModal('modalEditStore');
  };

  const btnEditStoreHeader = document.getElementById('btnEditStoreHeader');
  if (btnEditStoreHeader) {
    btnEditStoreHeader.addEventListener('click', () => window.openEditStoreModal());
  }

  const btnCancelEditStore = document.getElementById('btnCancelEditStore');
  if (btnCancelEditStore) {
    btnCancelEditStore.addEventListener('click', () => closeModal('modalEditStore'));
  }

  const editStoreForm = document.getElementById('editStoreForm');
  if (editStoreForm) {
    editStoreForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const bName = document.getElementById('editStoreName').value.trim();
      const city = document.getElementById('editStoreCity').value.trim();
      const phone = document.getElementById('editStorePhone').value.trim();
      const gstin = document.getElementById('editStoreGstin').value.trim();

      try {
        const resp = await fetch('/api/v1/auth/merchant-update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            merchant_id: activeMerchantId,
            business_name: bName,
            city: city,
            phone: phone,
            gstin: gstin
          })
        });

        if (resp.ok) {
          const data = await resp.json();
          if (!merchantData) merchantData = {};
          merchantData.business_name = data.business_name;
          merchantData.city = data.city;
          merchantData.phone = data.phone;
          merchantData.gstin = data.gstin;
          merchantData.merchant_id = data.merchant_id;
          localStorage.setItem('sahayak_merchant', JSON.stringify(merchantData));

          updateMerchantHeader(merchantData);
          closeModal('modalEditStore');
          alert('✓ Store profile updated successfully!');
        } else {
          alert('Could not update store details. Please try again.');
        }
      } catch (err) {
        console.error('Error updating store:', err);
      }
    });
  }

  // --- B. EDIT SHELF PRODUCT & ADD ITEM ---
  window.openEditProductModal = function(item = null) {
    const title = document.getElementById('modalEditProductTitle');
    const prodName = document.getElementById('editProdName');
    const prodPrice = document.getElementById('editProdPrice');
    const prodCost = document.getElementById('editProdCost');
    const prodStock = document.getElementById('editProdStock');
    const prodUnit = document.getElementById('editProdUnit');
    const prodBatch = document.getElementById('editProdBatch');
    const origName = document.getElementById('editProdOriginalName');
    const batchId = document.getElementById('editProdBatchId');
    const btnDelete = document.getElementById('btnDeleteProd');

    if (item) {
      if (title) title.textContent = 'Edit Shelf Product';
      if (prodName) prodName.value = item.name || '';
      if (prodPrice) prodPrice.value = item.price || 0;
      if (prodCost) prodCost.value = item.cost || Math.round((item.price || 50) * 0.85);
      if (prodStock) prodStock.value = item.stock || 0;
      if (prodUnit) prodUnit.value = item.unit || 'units';
      if (prodBatch) prodBatch.value = item.batch || 'FIFO-01';
      if (origName) origName.value = item.name || '';
      if (batchId) batchId.value = item.batch_id || '';
      if (btnDelete) btnDelete.style.display = 'inline-block';
    } else {
      if (title) title.textContent = 'Add Product to Shelf';
      if (prodName) prodName.value = '';
      if (prodPrice) prodPrice.value = '60';
      if (prodCost) prodCost.value = '50';
      if (prodStock) prodStock.value = '20';
      if (prodUnit) prodUnit.value = 'units';
      if (prodBatch) prodBatch.value = 'FIFO-01';
      if (origName) origName.value = '';
      if (batchId) batchId.value = '';
      if (btnDelete) btnDelete.style.display = 'none';
    }

    showModal('modalEditProduct');
  };

  window.openEditProductModalById = function(id) {
    const item = catalogData.find(c => c.id === id);
    window.openEditProductModal(item || null);
  };

  window.openEditProductModalByName = function(name, suggestedPrice = null) {
    let item = catalogData.find(c => c.name.toLowerCase() === name.toLowerCase());
    if (!item) {
      item = { name: name, price: suggestedPrice || 50, cost: (suggestedPrice ? suggestedPrice * 0.85 : 40), stock: 10, batch: 'FIFO-01', unit: 'units' };
    } else if (suggestedPrice) {
      item = { ...item, price: suggestedPrice };
    }
    window.openEditProductModal(item);
  };

  const btnCancelEditProd = document.getElementById('btnCancelEditProd');
  if (btnCancelEditProd) {
    btnCancelEditProd.addEventListener('click', () => closeModal('modalEditProduct'));
  }

  const editProductForm = document.getElementById('editProductForm');
  if (editProductForm) {
    editProductForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const name = document.getElementById('editProdName').value.trim();
      const origName = document.getElementById('editProdOriginalName').value.trim();
      const bId = document.getElementById('editProdBatchId').value.trim();
      const price = parseFloat(document.getElementById('editProdPrice').value || 0);
      const cost = parseFloat(document.getElementById('editProdCost').value || 0);
      const stock = parseFloat(document.getElementById('editProdStock').value || 0);
      const unit = document.getElementById('editProdUnit').value;
      const batch = document.getElementById('editProdBatch').value.trim();

      try {
        const resp = await fetch('/api/counter/inventory/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            merchant_id: activeMerchantId,
            item_name: name,
            original_item_name: origName || undefined,
            batch_id: bId || undefined,
            retail_mrp: price,
            cost_price: cost,
            quantity: stock,
            unit: unit,
            batch_number: batch
          })
        });

        if (resp.ok) {
          closeModal('modalEditProduct');
          loadLiveDashboardMetrics();
        } else {
          alert('Failed to save product. Please check values.');
        }
      } catch (err) {
        console.error('Error updating inventory item:', err);
      }
    });
  }

  const btnDeleteProd = document.getElementById('btnDeleteProd');
  if (btnDeleteProd) {
    btnDeleteProd.addEventListener('click', async () => {
      const origName = document.getElementById('editProdOriginalName').value.trim();
      const bId = document.getElementById('editProdBatchId').value.trim();
      if (!confirm(\`Remove "\${origName}" from your active shelf?\`)) return;

      try {
        const resp = await fetch('/api/counter/inventory/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            merchant_id: activeMerchantId,
            item_name: origName || undefined,
            batch_id: bId || undefined
          })
        });

        if (resp.ok) {
          closeModal('modalEditProduct');
          loadLiveDashboardMetrics();
        }
      } catch (err) {
        console.error('Error deleting product:', err);
      }
    });
  }

  // Shelf Reset Toolbar Button
  const btnClearStockToolbar = document.getElementById('btnClearStockToolbar');
  if (btnClearStockToolbar) {
    btnClearStockToolbar.addEventListener('click', async () => {
      if (!confirm('Are you sure you want to reset all shelf stock to 0? This enables new merchants to start fresh and populate stock strictly by scanning distributor invoices.')) return;
      try {
        const resp = await fetch('/api/counter/inventory/clear-all', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ merchant_id: activeMerchantId })
        });
        if (resp.ok) {
          loadLiveDashboardMetrics();
        }
      } catch (err) {
        console.error('Error clearing inventory:', err);
      }
    });
  }

  // --- C. EDIT CUSTOMER KHATA ACCOUNT ---
  window.openEditCustomerModal = function(name, phone, balance) {
    const editName = document.getElementById('editCustName');
    const editPhone = document.getElementById('editCustPhone');
    const editBalance = document.getElementById('editCustBalance');
    const editNotes = document.getElementById('editCustNotes');
    const origName = document.getElementById('editCustOriginalName');

    if (editName) editName.value = name || '';
    if (editPhone) editPhone.value = phone || '';
    if (editBalance) editBalance.value = balance || 0;
    if (editNotes) editNotes.value = 'Verified Customer Account';
    if (origName) origName.value = name || '';

    showModal('modalEditCustomer');
  };

  const btnCancelEditCust = document.getElementById('btnCancelEditCust');
  if (btnCancelEditCust) {
    btnCancelEditCust.addEventListener('click', () => closeModal('modalEditCustomer'));
  }

  const editCustomerForm = document.getElementById('editCustomerForm');
  if (editCustomerForm) {
    editCustomerForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const name = document.getElementById('editCustName').value.trim();
      const origName = document.getElementById('editCustOriginalName').value.trim();
      const phone = document.getElementById('editCustPhone').value.trim();
      const bal = parseFloat(document.getElementById('editCustBalance').value || 0);
      const notes = document.getElementById('editCustNotes').value.trim();

      try {
        const resp = await fetch('/api/counter/khata/customer/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            merchant_id: activeMerchantId,
            customer_name: name,
            original_customer_name: origName,
            customer_phone: phone,
            current_balance: bal,
            notes: notes
          })
        });

        if (resp.ok) {
          closeModal('modalEditCustomer');
          loadLiveDashboardMetrics();
        }
      } catch (err) {
        console.error('Error updating customer khata:', err);
      }
    });
  }

  const btnDeleteCust = document.getElementById('btnDeleteCust');
  if (btnDeleteCust) {
    btnDeleteCust.addEventListener('click', async () => {
      const origName = document.getElementById('editCustOriginalName').value.trim();
      if (!confirm(\`Delete credit account for "\${origName}"?\`)) return;

      try {
        const resp = await fetch('/api/counter/khata/customer/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            merchant_id: activeMerchantId,
            customer_name: origName
          })
        });

        if (resp.ok) {
          closeModal('modalEditCustomer');
          loadLiveDashboardMetrics();
        }
      } catch (err) {
        console.error('Error deleting customer:', err);
      }
    });
  }

  // --- D. EDIT SUPPLIER INVOICE & PAYABLES ---
  window.openEditInvoiceModal = function(number, supplier, amount, dueRaw, status) {
    const editSupp = document.getElementById('editInvSupplier');
    const editNum = document.getElementById('editInvNumber');
    const editAmt = document.getElementById('editInvAmount');
    const editDue = document.getElementById('editInvDueDate');
    const editStatus = document.getElementById('editInvStatus');
    const origNum = document.getElementById('editInvOriginalNumber');

    if (editSupp) editSupp.value = supplier || '';
    if (editNum) editNum.value = number || '';
    if (editAmt) editAmt.value = amount || 0;
    if (editDue) editDue.value = dueRaw || '';
    if (editStatus) editStatus.value = status || 'LOGGED';
    if (origNum) origNum.value = number || '';

    showModal('modalEditInvoice');
  };

  const btnCancelEditInv = document.getElementById('btnCancelEditInv');
  if (btnCancelEditInv) {
    btnCancelEditInv.addEventListener('click', () => closeModal('modalEditInvoice'));
  }

  const editInvoiceForm = document.getElementById('editInvoiceForm');
  if (editInvoiceForm) {
    editInvoiceForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const origNum = document.getElementById('editInvOriginalNumber').value.trim();
      const num = document.getElementById('editInvNumber').value.trim();
      const supp = document.getElementById('editInvSupplier').value.trim();
      const amt = parseFloat(document.getElementById('editInvAmount').value || 0);
      const due = document.getElementById('editInvDueDate').value;
      const status = document.getElementById('editInvStatus').value;

      try {
        const resp = await fetch('/api/counter/invoice/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            merchant_id: activeMerchantId,
            invoice_number: num,
            original_invoice_number: origNum,
            supplier_name: supp,
            amount: amt,
            credit_due_date: due || undefined,
            status: status
          })
        });

        if (resp.ok) {
          closeModal('modalEditInvoice');
          loadLiveDashboardMetrics();
        }
      } catch (err) {
        console.error('Error updating invoice:', err);
      }
    });
  }

  // --- E. INVOICE SCAN & VISION POPULATION MODAL ---
  window.openScanInvoiceModal = function() {
    const progressArea = document.getElementById('scanProgressArea');
    const fileNameTag = document.getElementById('selectedFileNameTag');
    const uploadBtn = document.getElementById('btnUploadAndStock');
    const fileInput = document.getElementById('invoiceFileInput');

    if (progressArea) progressArea.style.display = 'none';
    if (fileNameTag) fileNameTag.style.display = 'none';
    if (uploadBtn) uploadBtn.style.display = 'none';
    if (fileInput) fileInput.value = '';

    showModal('modalScanInvoice');
  };

  const btnCancelScanModal = document.getElementById('btnCancelScanModal');
  if (btnCancelScanModal) {
    btnCancelScanModal.addEventListener('click', () => closeModal('modalScanInvoice'));
  }

  const btnScanInvoiceToolbar = document.getElementById('btnScanInvoiceToolbar');
  if (btnScanInvoiceToolbar) {
    btnScanInvoiceToolbar.addEventListener('click', () => window.openScanInvoiceModal());
  }

  const btnAddProductToolbar = document.getElementById('btnAddProductToolbar');
  if (btnAddProductToolbar) {
    btnAddProductToolbar.addEventListener('click', () => window.openEditProductModal(null));
  }

  const btnScanInvoicePayables = document.getElementById('btnScanInvoicePayables');
  if (btnScanInvoicePayables) {
    btnScanInvoicePayables.addEventListener('click', () => window.openScanInvoiceModal());
  }

  // Fast 1-Click Wholesale Bill Scan
  const btnRunSampleScan = document.getElementById('btnRunSampleScan');
  if (btnRunSampleScan) {
    btnRunSampleScan.addEventListener('click', async () => {
      const progressArea = document.getElementById('scanProgressArea');
      const progressText = document.getElementById('scanProgressText');
      if (progressArea) progressArea.style.display = 'block';
      if (progressText) progressText.textContent = '🔍 Reading wholesale dot-matrix invoice via Gemini Vision OCR...';

      try {
        const formData = new FormData();
        formData.append('merchant_id', activeMerchantId);
        formData.append('template', 'wholesale');

        setTimeout(() => {
          if (progressText) progressText.textContent = '🧮 Validating arithmetic guardrails & line totals...';
        }, 600);

        const resp = await fetch('/api/counter/scan-invoice', {
          method: 'POST',
          body: formData
        });

        if (resp.ok) {
          const res = await resp.json();
          if (progressText) progressText.textContent = \`📦 Success! Stocked \${res.items_stocked} products from \${res.supplier_name}.\`;
          setTimeout(() => {
            closeModal('modalScanInvoice');
            loadLiveDashboardMetrics();
            playSoundboxChime(100, 'CASH');
          }, 800);
        } else {
          alert('Could not scan invoice. Please try again.');
          if (progressArea) progressArea.style.display = 'none';
        }
      } catch (err) {
        console.error('Invoice scan error:', err);
        if (progressArea) progressArea.style.display = 'none';
      }
    });
  }

  // File Upload Ingestion
  const invoiceFileInput = document.getElementById('invoiceFileInput');
  const selectedFileNameTag = document.getElementById('selectedFileNameTag');
  const btnUploadAndStock = document.getElementById('btnUploadAndStock');

  if (invoiceFileInput) {
    invoiceFileInput.addEventListener('change', () => {
      if (invoiceFileInput.files && invoiceFileInput.files[0]) {
        const file = invoiceFileInput.files[0];
        if (selectedFileNameTag) {
          selectedFileNameTag.textContent = \`✓ Selected: \${file.name} (\${Math.round(file.size / 1024)} KB)\`;
          selectedFileNameTag.style.display = 'block';
        }
        if (btnUploadAndStock) btnUploadAndStock.style.display = 'inline-flex';
      }
    });
  }

  if (btnUploadAndStock) {
    btnUploadAndStock.addEventListener('click', async () => {
      if (!invoiceFileInput || !invoiceFileInput.files || !invoiceFileInput.files[0]) return;
      const file = invoiceFileInput.files[0];
      const progressArea = document.getElementById('scanProgressArea');
      const progressText = document.getElementById('scanProgressText');
      if (progressArea) progressArea.style.display = 'block';
      if (progressText) progressText.textContent = \`🔍 Processing \${file.name} with Gemini Structured OCR...\`;

      try {
        const formData = new FormData();
        formData.append('merchant_id', activeMerchantId);
        formData.append('file', file);

        const resp = await fetch('/api/counter/scan-invoice', {
          method: 'POST',
          body: formData
        });

        if (resp.ok) {
          const res = await resp.json();
          if (progressText) progressText.textContent = \`📦 Shelves Stocked! Extracted \${res.items_stocked} products.\`;
          setTimeout(() => {
            closeModal('modalScanInvoice');
            loadLiveDashboardMetrics();
            playSoundboxChime(200, 'CASH');
          }, 900);
        } else {
          alert('Invoice scan failed. Please check image quality.');
          if (progressArea) progressArea.style.display = 'none';
        }
      } catch (err) {
        console.error('File scan error:', err);
        if (progressArea) progressArea.style.display = 'none';
      }
    });
  }

  \n${endTag}`;

if (code.includes(endTag)) {
  code = code.replace(endTag, modalHandlersCode);
  console.log('Added universal modal handlers to dashboard.js');
} else {
  console.log('endTag not found');
}

fs.writeFileSync(jsPath, code, 'utf8');
console.log('Saved all dashboard.js updates successfully');
