# Sahayak (सहायक) — Autonomous Predictive Cash-Flow Copilot Showcase

A high-fidelity editorial product showcase for **Sahayak (सहायक)**, built with vanilla HTML5, CSS3, and ES6 JavaScript.

Designed for **Target Problem Statement: F-03 (Predictive Cash-Flow Management for 30 Million Small Indian Retailers)**.

---

## 🎯 Target Problem: F-03 & Architectural Highlights

1. **The Payment-Basket Attribution Gap**:
   - Resolves the blindspot where standard payment soundboxes and UPI webhooks emit monetary amounts (e.g. ₹300) without itemized SKU data.
   - Sahayak captures counter intent in vernacular speech (*"Paytm pe 300 aaya, 2 tel diya"*), enabling automatic FIFO inventory decrements.

2. **Wholesale Paper Bill Digitizer & Margin Guard**:
   - Reads 9-pin dot-matrix distributor bills in <15s with Gemini 1.5 Flash Vision.
   - Detects wholesale cost price hikes >3% and instantly calculates calibrated shelf MRPs to preserve retailer profit margins.

3. **System 1 Jev Reflex Router (<18ms, $0 Compute)**:
   - Ultra-fast intent classification dropping spam and memes while routing retail transactions to frozen Pydantic contracts.

4. **Multi-Agent Blackboard Fabric**:
   - **Agent 1**: Voice Khata & Receivables Engine (Kannada, Hindi, Hinglish)
   - **Agent 2**: Invoice & Due-Date Ingestion (Gemini 1.5 Flash Vision)
   - **Agent 3**: Margin-Guard Price Shield
   - **Agent 4**: FIFO Inventory Depletion & Dead-Capital Hunter
   - **Agent 5**: Predictive Liquidity & Cash-Flow Simulator
   - **Agent 6**: 10:15 PM Closing Vernacular Audio Storyteller

---

## 🎨 Design & Animation Aesthetics

- **Editorial Luxury**: Google Fonts `Newsreader` (serif headlines) and `Plus Jakarta Sans` (UI body).
- **Financial Warmth**: Warm ivory canvas (`#FAF7F2`), ethereal mesh aurora (`#FFECCC`, `#F9DEE4`, `#E9D9FC`, `#DBF3E8`), and gold/emerald/purple accents.
- **Harmonic Voice Canvas**: Layered sinusoidal curves in saffron gold, lilac, and emerald green with dynamic audio reacting to live microphone input or simulated speech.
- **3-Step Workflow Line-Art**:
  1. **Perception**: Line-art microphone with ambient sound wave trail & bill outline.
  2. **System 1 Reflex**: Circular wave with sub-LLM classification ticks.
  3. **Deterministic Core**: Hand cradling an illuminated rupee shield.
- **Interactive Margin-Guard Simulator**:
  - Live sliders for wholesale cost rate (₹140 -> ₹147) and target margin (10%).
  - Dynamically calculates price delta % and recommended shelf MRP, updating a simulated WhatsApp alert bubble.
- **Live Frozen Contract Inspector Modal**:
  - Inspects real Pydantic contract payloads (`VoiceKhataIntent`, `CounterSaleEvent`, `InvoiceSchema`), ACID double-entry debits/credits, and WhatsApp confirmation previews.

---

## 🚀 Running the Showcase Locally

```bash
# From the project root
python -m http.server 8080 --directory frontend
```

Open `http://localhost:8080` in your desktop browser.
