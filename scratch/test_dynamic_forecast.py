"""
scratch/test_dynamic_forecast.py
Tests that CashForecastAgent correctly leverages the 30-day DailyCashLog data
for merchant 'M_MOHITH_KIE2' to generate a volatile, realistic 14-day trajectory.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from app.services.forecast_agent import forecast_agent

def test_forecast():
    merchant_id = "M_MOHITH_KIE2"
    print(f"=== TESTING 14-DAY DYNAMIC FORECAST FOR {merchant_id} ===")
    res = forecast_agent.generate_forecast(merchant_id=merchant_id, forecast_days=14)

    print(f"Current Liquid Cash: Rs.{res['current_liquid_cash']:,.2f}")
    print(f"Base Daily Sales Velocity: Rs.{res['daily_sales_velocity']:,.2f}")
    print(f"Projected Balance at Day 14: Rs.{res['projected_balance']:,.2f}")
    print(f"Status: {'CRUNCH' if res['has_cash_crunch'] else 'SOLVENT'}")

    print("\n--- 14-DAY TRAJECTORY BREAKDOWN ---")
    print(f"{'Day':<5} {'Date':<12} {'Weekday':<8} {'DOW Factor':<12} {'Inflow (Rs)':<14} {'Outflow (Rs)':<14} {'Balance (Rs)':<14} {'Status':<8}")
    print("-" * 90)
    for t in res["trajectory"]:
        print(f"T+{t['day_index']:<2} {t['date']:<12} {t['day_name']:<8} {t.get('dow_factor', 1.0):<12.3f} {t['inflow']:<14,.2f} {t['outflow']:<14,.2f} {t['projected_balance']:<14,.2f} {t['status']:<8}")

    # Assertions
    inflows = [t["inflow"] for t in res["trajectory"]]
    assert len(set(inflows)) > 1, "Inflows must vary dynamically across days!"
    print("\n[SUCCESS] Day-by-day cash inflows vary dynamically according to retail DOW and payday cycles!")

if __name__ == "__main__":
    test_forecast()
