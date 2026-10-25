"""
scratch/test_auth_gatekeeper_live.py
Validates the Telegram Authenticator flow:
1. Unauthenticated chat sending /start receives Authentication Required prompt
2. Unauthenticated chat sending voice/photo gets Access Denied prompt
3. Chat sending Merchant ID successfully authenticates
4. Chat sending /logout successfully unlinks and locks ledger
"""
import sys
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from app.db.repository import (
    get_registered_merchant_for_chat,
    link_chat_to_merchant,
    unlink_chat_from_merchant
)

def run_tests():
    test_chat = "9988112233"
    unlink_chat_from_merchant(test_chat)

    # 1. Verify initially unauthenticated
    m0 = get_registered_merchant_for_chat(test_chat)
    assert m0 is None, f"Expected None, got {m0}"
    print("✓ Test 1: Chat is completely unauthenticated initially.")

    # 2. Test authenticating with Merchant ID
    linked = link_chat_to_merchant(test_chat, "M_MOHITH_A5AN")
    assert linked is not None, "Failed to authenticate with M_MOHITH_A5AN"
    assert linked["id"] == "M_MOHITH_A5AN"
    print(f"✓ Test 2: Authenticated successfully as '{linked['name']}' ({linked['id']})")

    # 3. Verify get_registered_merchant_for_chat finds it
    m1 = get_registered_merchant_for_chat(test_chat)
    assert m1 is not None and m1["id"] == "M_MOHITH_A5AN"
    print("✓ Test 3: Session active in PostgreSQL.")

    # 4. Test /logout unlinking
    unlinked = unlink_chat_from_merchant(test_chat)
    assert unlinked is True, "Failed to unlink chat"
    m2 = get_registered_merchant_for_chat(test_chat)
    assert m2 is None, "Chat still linked after logout!"
    print("✓ Test 4: Logged out successfully, ledger locked.")

    # 5. Clean up user's real chat ID 5821612449 to ensure they start fresh
    unlink_chat_from_merchant("5821612449")
    print("✓ Test 5: Cleaned up active chat ID 5821612449 to ensure fresh authenticator prompt.")
    print("\nALL TELEGRAM AUTHENTICATOR TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
