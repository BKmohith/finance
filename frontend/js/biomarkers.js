/**
 * Sahayak (सहायक) Financial Intelligence & Perception Engine
 * Simulates System 1 Jev Router (<18ms), Sarvam Vernacular STT, and Margin Guard.
 */

const SAHAYAK_FINANCIAL_PROFILES = {
  kannada_khata: {
    id: "kannada_khata",
    name: "Kannada Voice Khata (Customer Credit)",
    language: "kn-IN (Kannada)",
    rawAudioText: "ರಮೇಶ್ ಅವರಿಗೆ 500 ರೂಪಾಯಿ ಸಾಲ",
    normalizedEnglish: "Ramesh credit rupees 500",
    intent: "VOICE_KHATA",
    confidence: "99.4%",
    latency: "12.4ms",
    cost: "$0.000 (Sub-LLM Fast-Path)",
    statusText: "ACID Ledger Committed",
    statusColor: "#1B8354",
    customer: "Ramesh Kumar (ID: #KHT-8924)",
    monetaryValue: "₹500.00 (Udhaar Credit Given)",
    acidEntries: [
      { type: "DEBIT", account: "Customer_Receivables (Ramesh)", amount: "+₹500.00" },
      { type: "CREDIT", account: "Inventory_Asset_Account", amount: "-₹500.00" }
    ],
    agentInsights: {
      agent1: "Customer balance updated: ₹1,450.00 total outstanding. 14-day WhatsApp payment reminder queued.",
      agent5: "Net 7-day liquidity unaffected. Working capital absorption within safe 8% threshold."
    },
    contractPayload: {
      "event_type": "VoiceKhataIntent",
      "merchant_id": "MERCHANT_BLR_0481",
      "intent_class": "VOICE_KHATA",
      "customer_id": "CUST-KHT-8924",
      "customer_name": "Ramesh Kumar",
      "action": "CREDIT_GIVEN",
      "amount": 500.00,
      "currency": "INR",
      "idempotency_hash": "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
      "sql_rls_verified": true
    },
    whatsappMessage: "ನಮಸ್ಕಾರ ರಮೇಶ್ ಅವರೆ, ನಿಮ್ಮ ಖಾತೆಗೆ ₹500 ಸಾಲ ದಾಖಲಾಗಿದೆ. ಇಂದಿನ ಒಟ್ಟು ಬಾಕಿ: ₹1,450.00. - ಶಾಪ್ ಮಾಲೀಕ"
  },

  hinglish_pos: {
    id: "hinglish_pos",
    name: "Hinglish Counter Sale & FIFO Depletion",
    language: "hi-IN (Hinglish)",
    rawAudioText: "Paytm pe 300 aaya, 2 Fortune oil diya",
    normalizedEnglish: "Paytm received 300, 2 Fortune Oil sold",
    intent: "COUNTER_SALE",
    confidence: "98.9%",
    latency: "14.8ms",
    cost: "$0.000 (Jev Reflex)",
    statusText: "FIFO Inventory Decremented",
    statusColor: "#2E8B57",
    customer: "Counter Walk-in (UPI)",
    monetaryValue: "₹300.00 (Paytm Soundbox Reconciled)",
    acidEntries: [
      { type: "DEBIT", account: "Cash_Bank_UPI_Paytm", amount: "+₹300.00" },
      { type: "CREDIT", account: "Sales_Revenue_Account", amount: "-₹300.00" }
    ],
    agentInsights: {
      agent4: "FIFO Row-Level Lock: Depleted 2 units from Batch-2026-OCT-09 (Cost: ₹138/ea). Remaining in batch: 24 units.",
      agent5: "Gross profit margin on transaction: 8.7% (₹24.00 net margin)."
    },
    contractPayload: {
      "event_type": "CounterSaleEvent",
      "merchant_id": "MERCHANT_BLR_0481",
      "intent_class": "COUNTER_SALE",
      "payment_mode": "UPI_PAYTM",
      "total_amount": 300.00,
      "items": [
        { "sku": "FORTUNE_SUNFLOWER_1L", "quantity": 2, "unit_price": 150.00, "batch_id": "B-OCT-09" }
      ],
      "idempotency_hash": "sha256:4a38f31b26c7d2426372138927161bca728923a1f94a8c88921b7618921a9992",
      "sql_rls_verified": true
    },
    whatsappMessage: "✅ Counter Sale Reconciled: ₹300.00 via Paytm UPI. 2x Fortune Oil 1L decremented from FIFO inventory."
  },

  distributor_spike: {
    id: "distributor_spike",
    name: "Distributor Price Hike (Margin Guard)",
    language: "hi-IN (Wholesale Ingestion)",
    rawAudioText: "Sharma Distributor bill 15 petiyan Fortune Mustard Oil ₹140 se ₹147 ho gaya",
    normalizedEnglish: "Sharma Distributor bill 15 cases Fortune Mustard Oil wholesale ₹140 to ₹147",
    intent: "INVOICE_BILL",
    confidence: "99.7%",
    latency: "16.1ms",
    cost: "$0.000 (Arithmetic Guard Validated)",
    statusText: "Margin-Guard Spike Triggered (>3%)",
    statusColor: "#E3536C",
    customer: "Sharma FMCG Distributors",
    monetaryValue: "₹35,280.00 (Credit Due: 15 Days)",
    acidEntries: [
      { type: "DEBIT", account: "Inventory_Asset_Oil", amount: "+₹35,280.00" },
      { type: "CREDIT", account: "Accounts_Payable_Sharma", amount: "-₹35,280.00" }
    ],
    agentInsights: {
      agent2: "Gemini 1.5 Flash Vision OCR verified arithmetic: 240 units × ₹147.00 == ₹35,280.00. Payment due in 15 days.",
      agent3: "🚨 MARGIN SPIKE ALERT: Unit wholesale rose by ₹7 (+5.0%). Recommended shelf price: ₹162 to preserve 10% margin."
    },
    contractPayload: {
      "event_type": "InvoiceSchema",
      "merchant_id": "MERCHANT_BLR_0481",
      "intent_class": "INVOICE_BILL",
      "supplier_name": "Sharma FMCG Distributors",
      "grand_total": 35280.00,
      "due_date": "2026-11-09",
      "price_delta_pct": 5.0,
      "previous_rate": 140.00,
      "new_unit_rate": 147.00,
      "recommended_mrp": 162.00,
      "sql_rls_verified": true
    },
    whatsappMessage: "⚠️ Alert: Fortune Oil wholesale cost rose by ₹7 (₹140 -> ₹147). Raise shelf price to ₹162 to protect 10% margin."
  }
};

class FinancialEngine {
  static getProfile(profileKey = 'kannada_khata') {
    return SAHAYAK_FINANCIAL_PROFILES[profileKey] || SAHAYAK_FINANCIAL_PROFILES.kannada_khata;
  }

  static playChime(type = 'start') {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.connect(gain);
      gain.connect(ctx.destination);

      if (type === 'start') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(520, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(1040, ctx.currentTime + 0.16);
        gain.gain.setValueAtTime(0.08, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.28);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.28);
      } else if (type === 'complete') {
        // High-clarity double POS register chime
        osc.type = 'sine';
        osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
        osc.frequency.setValueAtTime(880.00, ctx.currentTime + 0.12); // A5
        gain.gain.setValueAtTime(0.09, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.55);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.55);
      }
    } catch (e) {}
  }
}

window.FinancialEngine = FinancialEngine;
window.SAHAYAK_FINANCIAL_PROFILES = SAHAYAK_FINANCIAL_PROFILES;
