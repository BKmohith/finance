# Sahayak System Dataflow (Telegram Bot Gateway)

```
  [LAPTOP 1: TELEGRAM BOT]           [LAPTOP 3: VISION AI]               [LAPTOP 2: DATA CORE]
  Telegram Bot (Long-Polling/Webhook) Celery Worker + Gemini Flash       Supabase PostgreSQL 16 + RLS
  
  Merchant snaps paper bill          Pre-processes image (OpenCV)        Atomic ACID Transaction Write
             │                                     │                                    │
             ▼                                     ▼                                    ▼
  Receives Photo / Voice ─────────>  Decodes dot-matrix invoice  ───────>  Saves Invoice & Items to Supabase
  Deduplicates in Redis (<1ms)       Validates: qty * rate == total        Calculates Margin-Guard (>3% hike)
                                                                                        │
                                                                                        ▼
  Dispatches Telegram Alert  <────────────────────────────────────────────  Emits PriceHikeAlert payload
  to merchant: "Raise MRP!"
```
