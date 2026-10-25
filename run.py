"""
run.py - Production Server Runner for Render & Cloud Platforms
Provides explicit traceback logging, safe port resolution, and reliable startup.
"""
import os
import sys
import traceback

print("==================================================", flush=True)
print(">>> [Sahayak] Booting Production Service...", flush=True)
print(f">>> [Sahayak] Python executable: {sys.executable}", flush=True)
print(f">>> [Sahayak] Python version: {sys.version}", flush=True)
print(f">>> [Sahayak] PORT env var: {os.environ.get('PORT', '8000 (default)')}", flush=True)
print("==================================================", flush=True)

try:
    print(">>> [Sahayak] Testing app.main import...", flush=True)
    import app.main
    print(">>> [Sahayak] app.main imported successfully! All dependencies verified.", flush=True)
except Exception as e:
    print(">>> [Sahayak] CRITICAL ERROR IMPORTING app.main:", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
    sys.stderr.flush()
    sys.exit(1)

if __name__ == "__main__":
    import uvicorn
    raw_port = os.environ.get("PORT", "8000")
    try:
        port = int(raw_port)
    except ValueError:
        print(f">>> [Sahayak] Warning: PORT '{raw_port}' could not be parsed as int. Falling back to 8000.", flush=True)
        port = 8000

    print(f">>> [Sahayak] Starting Uvicorn on 0.0.0.0:{port}...", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True
    )
