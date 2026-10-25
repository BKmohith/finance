"""
scratch/test_telegram_forecast_output.py
Verifies the new dynamic Telegram report output.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from app.services.forecast_agent import forecast_agent

data = forecast_agent.generate_forecast("M_MOHITH_KIE2", forecast_days=14)
report = forecast_agent.format_telegram_report(data)
print(report)
