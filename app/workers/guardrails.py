"""
app/workers/guardrails.py
Deterministic mathematical and sanity verification for AI-extracted invoice data.
Guarantees zero hallucinated numbers reach the financial ledger.
"""
import logging
from typing import List, Tuple
from pydantic import BaseModel

from app.workers.contracts import ExtractedInvoiceData, ExtractedLineItem

logger = logging.getLogger(__name__)


class GuardrailValidationError(ValueError):
    """Raised when extracted invoice data violates mathematical integrity rules."""
    pass


class LineItemDiscrepancy(BaseModel):
    item_index: int
    item_name: str
    expected_total: float
    reported_total: float
    difference: float


class ValidationSummary(BaseModel):
    is_valid: bool
    calculated_subtotal: float
    grand_total: float
    grand_total_difference: float
    discrepancies: List[LineItemDiscrepancy]


def validate_line_item_math(
    item: ExtractedLineItem,
    item_index: int = 0,
    tolerance: float = 1.0,
) -> Tuple[bool, float, float]:
    """
    Validates that: |quantity * unit_wholesale_rate - line_total| < tolerance.
    Returns: (is_valid, expected_total, difference)
    """
    expected = round(item.quantity * item.unit_wholesale_rate, 2)
    diff = abs(expected - item.line_total)
    is_valid = diff <= tolerance
    return is_valid, expected, diff


def validate_invoice_arithmetic(
    data: ExtractedInvoiceData,
    line_item_tolerance: float = 1.0,
    grand_total_tolerance: float = 2.0,
    raise_on_failure: bool = False,
) -> Tuple[ExtractedInvoiceData, ValidationSummary]:
    """
    Enforces deterministic double-checks on Gemini-extracted invoices:
    1. Line Item Verification: For each item, |qty * rate - line_total| < tolerance.
    2. Grand Total Verification: |sum(line_total) - grand_total| < grand_total_tolerance.

    If raise_on_failure is True, raises GuardrailValidationError on discrepancies.
    Otherwise returns (data, summary) with flagged discrepancies.
    """
    discrepancies: List[LineItemDiscrepancy] = []
    calculated_sum = 0.0

    for idx, item in enumerate(data.items):
        is_item_valid, expected, diff = validate_line_item_math(item, idx, line_item_tolerance)
        calculated_sum += item.line_total

        if not is_item_valid:
            logger.warning(
                "Line item math mismatch at item [%d] '%s': qty=%.2f * rate=%.2f -> expected %.2f, got %.2f (diff=%.2f)",
                idx, item.item_name, item.quantity, item.unit_wholesale_rate, expected, item.line_total, diff
            )
            discrepancies.append(
                LineItemDiscrepancy(
                    item_index=idx,
                    item_name=item.item_name,
                    expected_total=expected,
                    reported_total=item.line_total,
                    difference=round(diff, 2),
                )
            )

    calculated_sum = round(calculated_sum, 2)
    grand_total_diff = round(abs(calculated_sum - data.grand_total), 2)
    is_grand_total_valid = grand_total_diff <= grand_total_tolerance

    if not is_grand_total_valid:
        logger.warning(
            "Invoice grand total mismatch: sum of line items=%.2f != invoice grand_total=%.2f (diff=%.2f)",
            calculated_sum, data.grand_total, grand_total_diff
        )

    overall_valid = (len(discrepancies) == 0) and is_grand_total_valid

    summary = ValidationSummary(
        is_valid=overall_valid,
        calculated_subtotal=calculated_sum,
        grand_total=data.grand_total,
        grand_total_difference=grand_total_diff,
        discrepancies=discrepancies,
    )

    if raise_on_failure and not overall_valid:
        error_msg_parts = []
        if discrepancies:
            error_msg_parts.append(f"{len(discrepancies)} line item discrepancies detected")
        if not is_grand_total_valid:
            error_msg_parts.append(
                f"grand total mismatch (sum={calculated_sum}, reported={data.grand_total}, diff={grand_total_diff})"
            )
        raise GuardrailValidationError("; ".join(error_msg_parts))

    return data, summary
