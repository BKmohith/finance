# Sahayak System Dataflow

```
  [LAPTOP 1: GATEWAY]                [LAPTOP 3: VISION AI]               [LAPTOP 2: YOU / DATA CORE]
  WhatsApp Webhook Ingestion         Celery Worker + Gemini Flash        Supabase PostgreSQL 16 + RLS
  
  Merchant snaps paper bill          Pre-processes image (OpenCV)        Atomic ACID Transaction Write
             │                                     │                                    │
             ▼                                     ▼                                    ▼
  Receives image payload  ────────>  Decodes dot-matrix invoice  ───────>  Saves Invoice & Items to Supabase
  Deduplicates in Redis (<1ms)       Validates: qty * rate == total        Calculates Margin-Guard (>3% hike)
                                                                                        │
                                                                                        ▼
  Dispatches WhatsApp Alert  <─────────────────────────────────────────────  Emits PriceHikeAlert payload
  to merchant: "Raise MRP!"
```
