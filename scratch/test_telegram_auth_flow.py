"""
scratch/test_telegram_auth_flow.py
Verifies end-to-end Telegram authentication:
1. link_chat_to_merchant via python with case-insensitive ID and phone
2. API /api/v1/auth/merchant-status
3. API /api/v1/auth/link-telegram
"""
import sys
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
import httpx
from app.db.repository import link_chat_to_merchant, get_registered_merchant_for_chat

BASE_URL = "http://127.0.0.1:8000"

def test_telegram_auth():
    print("=== Testing Telegram Authentication Backend ===")

    # 1. Test case-insensitive linking via repository
    test_chat = "9988776655"
    test_m_id = "m_lakshmi_jq7t" # Lowercase test
    print(f"\n1. Testing repository link_chat_to_merchant with lowercase '{test_m_id}' and chat '{test_chat}'...")
    res = link_chat_to_merchant(test_chat, test_m_id)
    assert res is not None, f"Failed to link with lowercase ID: {test_m_id}"
    print(f"   ✓ Successfully linked: {res['name']} ({res['id']})")

    # 2. Verify get_registered_merchant_for_chat
    print(f"\n2. Verifying get_registered_merchant_for_chat for chat '{test_chat}'...")
    found = get_registered_merchant_for_chat(test_chat)
    assert found is not None and found["id"].upper() == "M_LAKSHMI_JQ7T", f"Could not find registered chat: {found}"
    print(f"   ✓ Chat {test_chat} correctly resolves to {found['id']}")

    # 3. Test phone number linking via repository
    print("\n3. Testing linking with phone number '+919845099887'...")
    res_phone = link_chat_to_merchant(test_chat, "9845099887")
    assert res_phone is not None, "Failed to link with phone number"
    print(f"   ✓ Successfully linked via phone: {res_phone['name']} ({res_phone['id']})")

    # 4. Test API GET /api/v1/auth/merchant-status
    print("\n4. Testing API GET /api/v1/auth/merchant-status...")
    with httpx.Client(base_url=BASE_URL) as client:
        r = client.get(f"/api/v1/auth/merchant-status?merchant_id={res['id']}")
        assert r.status_code == 200, f"Status check failed: {r.status_code} {r.text}"
        data = r.json()
        assert data["is_telegram_active"] is True, f"Expected active telegram: {data}"
        print(f"   ✓ API Status returned is_telegram_active={data['is_telegram_active']} with chat_id={data['telegram_chat_id']}")

    # 5. Test API POST /api/v1/auth/link-telegram
    print("\n5. Testing API POST /api/v1/auth/link-telegram...")
    with httpx.Client(base_url=BASE_URL) as client:
        link_payload = {
            "merchant_id": "M_LAKSHMI_JQ7T",
            "chat_id": "tg_web_user_123"
        }
        r_link = client.post("/api/v1/auth/link-telegram", json=link_payload)
        assert r_link.status_code == 200, f"link-telegram API failed: {r_link.status_code} {r_link.text}"
        link_res = r_link.json()
        assert link_res["is_telegram_active"] is True, f"Expected active: {link_res}"
        print(f"   ✓ API link-telegram succeeded: {link_res['message']}")

    print("\n✅ ALL TELEGRAM AUTHENTICATION TESTS PASSED 100%!")

if __name__ == "__main__":
    test_telegram_auth()
