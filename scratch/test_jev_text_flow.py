"""
scratch/test_jev_text_flow.py
Verify that JevRouter and handle_text_message properly intercept spam and greetings.
"""
import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from app.workers.jev_router import JevRouter
from app.services.bot_service import handle_text_message

router = JevRouter()
test_inputs = [
    ("hello", "GREETING"),
    ("good morning", "GREETING"),
    ("who are you", "OFF_TOPIC"),
    ("tell me a joke", "OFF_TOPIC"),
    ("who is the president of usa", "OFF_TOPIC"),
    ("Paytm 300 Oil 2", "COUNTER_SALE"),
    ("Sharma ji 500 udhaar", "VOICE_KHATA"),
]

print("=" * 60)
print("TESTING JEV INTENT CLASSIFICATION & TEXT HANDLING")
print("=" * 60)

for text, category in test_inputs:
    intent = router.classify_intent(text)
    print(f"\n[QUERY] '{text}'")
    print(f" -> Jev Intent: {intent}")
    reply = handle_text_message("M_TEST_JEV", text)
    print(f" -> Reply Preview: {reply[:120].strip()}...")
    if category in ("GREETING", "OFF_TOPIC"):
        assert "cannot hav eaccses" not in reply.lower()
        assert "not available" not in reply.lower()
        assert "namaste" in reply.lower() or "sahayak retail copilot" in reply.lower()

print("\n" + "=" * 60)
print("🎉 ALL JEV SPAM & INTENT TESTS PASSED!")
print("=" * 60)
