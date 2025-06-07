# utils/formatters.py
import pandas as pd
from decimal import Decimal, ROUND_HALF_UP

def format_currency(value):
    if pd.notna(value) and isinstance(value, (int, float, Decimal)):
        if isinstance(value, Decimal): return f"€{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,}"
        return f"€{float(value):,.2f}" 
    return "N/A"

def format_percentage(value):
    if pd.notna(value) and isinstance(value, (int, float, Decimal)):
        if isinstance(value, Decimal): return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"
        return f"{float(value):.2f}%"
    return "N/A"

def format_decimal_for_table(value, precision='0.001'):
    if pd.notna(value) and isinstance(value, Decimal): return f"{value.quantize(Decimal(precision), rounding=ROUND_HALF_UP)}"
    elif pd.notna(value) and isinstance(value, (int,float)): return f"{float(value):.{len(precision.split('.')[1])}f}" 
    return "N/A"