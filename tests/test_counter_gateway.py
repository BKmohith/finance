"""
tests/test_counter_gateway.py
Isolated Phase 2 Unit Test Suite for Laptop 1 (Counter POS, Customer Khata & Touchpoints).
Runs in 100% isolation with zero dependency on Laptop 2 or Laptop 3.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.api.counter_notifier import CounterNotifier, counter_notifier
from app.core.contracts import (
    CELERY_COUNTER_TASK_NAME,
    CounterItemSale,
    CounterSaleEvent,
    PaymentMethod,
)
from app.main import app

client = TestClient(app)


# ============================================================================
# 1. POS Web Terminal & Catalog Endpoints
# ============================================================================
def test_counter_pos_html_served():
    response = client.get("/counter")
    assert response.status_code == 200
    assert "Sahayak" in response.text
    assert "Touch Counter POS" in response.text
    assert "Paytm UPI" in response.text


def test_counter_fmcg_catalog_endpoint():
    response = client.get("/api/counter/catalog")
    assert response.status_code == 200
    data = response.json()
    assert "catalog" in data
    assert len(data["catalog"]) >= 5
    first_item = data["catalog"][0]
    assert "item_name" in first_item
    assert "unit_retail_price" in first_item


# ============================================================================
# 2. Counter Sale Ingestion & Validation Tests
# ============================================================================
def test_counter_sale_cash_quick_denomination():
    payload = {
        "merchant_id": "M_TEST_001",
        "amount_paid": 500.0,
        "payment_method": "CASH",
        "items": [],
        "credit_amount": 0.0,
        "timestamp": datetime.utcnow().isoformat()
    }

    with patch("app.api.counter.celery_client.send_task") as mock_celery:
        response = client.post("/api/counter/sale", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "COMPLETED"
        assert data["amount_paid"] == 500.0
        assert data["payment_method"] == "CASH"
        assert "sale_id" in data
        assert "latency_ms" in data
        mock_celery.assert_called_once()


def test_counter_sale_paytm_upi_with_basket_items():
    items = [
        {"item_name": "Fortune Sunflower Oil 1L", "quantity": 2.0, "unit": "litres", "unit_retail_price": 165.0, "line_total": 330.0},
        {"item_name": "Tata Salt 1kg", "quantity": 1.0, "unit": "units", "unit_retail_price": 28.0, "line_total": 28.0}
    ]
    payload = {
        "merchant_id": "M_KIRANA_777",
        "amount_paid": 358.0,
        "payment_method": "PAYTM_UPI",
        "payment_reference": "UPI_TEST_REF_12345",
        "items": items,
        "credit_amount": 0.0,
        "timestamp": datetime.utcnow().isoformat()
    }

    with patch("app.api.counter.celery_client.send_task") as mock_celery:
        response = client.post("/api/counter/sale", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "COMPLETED"
        assert data["amount_paid"] == 358.0
        assert data["items_count"] == 2
        assert data["fifo_depletion_queued"] is True

        # Verify Celery task contract arguments
        mock_celery.assert_called_once()
        task_name, kwargs = mock_celery.call_args[0][0], mock_celery.call_args[1]["kwargs"]
        assert task_name == CELERY_COUNTER_TASK_NAME
        assert kwargs["merchant_id"] == "M_KIRANA_777"
        assert len(kwargs["items"]) == 2


def test_counter_sale_khata_credit_receipt_dispatch():
    items = [
        {"item_name": "Aashirvaad Atta 10kg", "quantity": 1.0, "unit": "bags", "unit_retail_price": 360.0, "line_total": 360.0}
    ]
    payload = {
        "merchant_id": "M_KIRANA_777",
        "amount_paid": 0.0,
        "payment_method": "KHATA_CREDIT",
        "items": items,
        "customer_name": "Sharma ji",
        "customer_phone": "9876543210",
        "credit_amount": 360.0,
        "timestamp": datetime.utcnow().isoformat()
    }

    with patch("app.api.counter.celery_client.send_task"), \
         patch("app.api.counter_notifier.counter_notifier.send_khata_credit_receipt") as mock_receipt:
        mock_receipt.return_value = {"status": "delivered", "channel": "mock"}
        response = client.post("/api/counter/sale", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "COMPLETED"
        assert data["credit_amount"] == 360.0
        assert data["receipt_dispatched"] == "delivered"
        mock_receipt.assert_called_once()


def test_counter_sale_split_payment_success():
    items = [
        {"item_name": "Surf Excel 1kg", "quantity": 2.0, "unit": "units", "unit_retail_price": 135.0, "line_total": 270.0}
    ]
    payload = {
        "merchant_id": "M_TEST_001",
        "amount_paid": 100.0,
        "payment_method": "SPLIT",
        "items": items,
        "customer_name": "Verma ji",
        "customer_phone": "9988776655",
        "credit_amount": 170.0,
        "timestamp": datetime.utcnow().isoformat()
    }

    with patch("app.api.counter.celery_client.send_task"), \
         patch("app.api.counter_notifier.counter_notifier.send_khata_credit_receipt"):
        response = client.post("/api/counter/sale", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["amount_paid"] == 100.0
        assert data["credit_amount"] == 170.0


# ============================================================================
# 3. Validation & Error Handling Tests
# ============================================================================
def test_counter_sale_zero_total_fails():
    payload = {
        "merchant_id": "M_001",
        "amount_paid": 0.0,
        "credit_amount": 0.0,
        "payment_method": "CASH",
        "items": []
    }
    response = client.post("/api/counter/sale", json=payload)
    assert response.status_code == 400
    assert "Transaction value must be greater than zero" in response.json()["detail"]


def test_counter_sale_credit_missing_customer_fails():
    payload = {
        "merchant_id": "M_001",
        "amount_paid": 0.0,
        "credit_amount": 150.0,
        "payment_method": "KHATA_CREDIT",
        "items": [
            {"item_name": "Tata Salt", "quantity": 5.0, "unit": "units", "unit_retail_price": 30.0, "line_total": 150.0}
        ],
        "customer_name": None,
        "customer_phone": None
    }
    response = client.post("/api/counter/sale", json=payload)
    assert response.status_code == 400
    assert "Customer name or phone is required" in response.json()["detail"]


def test_counter_sale_basket_mismatch_fails():
    payload = {
        "merchant_id": "M_001",
        "amount_paid": 100.0,  # Paid ₹100, but items total ₹200!
        "credit_amount": 0.0,
        "payment_method": "CASH",
        "items": [
            {"item_name": "Oil", "quantity": 1.0, "unit": "litres", "unit_retail_price": 200.0, "line_total": 200.0}
        ]
    }
    response = client.post("/api/counter/sale", json=payload)
    assert response.status_code == 400
    assert "does not match basket total" in response.json()["detail"]


# ============================================================================
# 4. Summary Snapshot & Receipt Formatting Tests
# ============================================================================
def test_counter_summary_snapshot():
    response = client.get("/api/counter/summary?merchant_id=M_TEST_001")
    assert response.status_code == 200
    data = response.json()
    assert "total_transactions" in data
    assert "total_cash_inflow" in data
    assert "total_upi_inflow" in data
    assert "total_khata_credit_extended" in data


def test_khata_receipt_formatting():
    event = CounterSaleEvent(
        merchant_id="M_001",
        amount_paid=200.0,
        payment_method=PaymentMethod.SPLIT,
        items=[
            CounterItemSale(item_name="Fortune Oil", quantity=2.0, unit="litres", unit_retail_price=160.0, line_total=320.0)
        ],
        customer_name="Gupta ji",
        customer_phone="9876500000",
        credit_amount=120.0
    )
    formatted = CounterNotifier.format_khata_receipt(event, total_balance=850.0, store_name="Ramesh Kirana")
    assert "Gupta ji" in formatted
    assert "Ramesh Kirana" in formatted
    assert "₹320.00" in formatted
    assert "₹120.00" in formatted
    assert "₹850.00" in formatted
    assert "Sahayak Digital Khata" in formatted
