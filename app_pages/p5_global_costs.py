# app_pages/p5_global_costs.py
import streamlit as st
from sqlalchemy.orm import Session
from decimal import Decimal
import sys
import os

# --- Boilerplate: Add project root to path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import get_db, User, GlobalCosts

# --- Page-specific content ---
def render(db: Session, user: User, is_mobile: bool):
    st.header("💰 Global Costs")
    st.write("Set your fixed monthly overheads. These costs will be allocated across your products to determine a more accurate cost per item.")

    costs = db.query(GlobalCosts).filter(GlobalCosts.user_id == user.id).first()
    if not costs:
        costs = GlobalCosts(user_id=user.id)
        db.add(costs)
        db.commit()
        db.refresh(costs)

    st.subheader("Fixed Monthly Overheads")
    st.info("These are costs that do not change month-to-month, like rent for your workshop.")

    with st.form("global_costs_form"):
        rent = st.number_input("Monthly Rent (€)", value=float(costs.monthly_rent or 0.0), min_value=0.0, format="%.2f")
        utilities = st.number_input(
            "Monthly Utilities (€)", value=float(costs.monthly_utilities or 0.0), min_value=0.0, format="%.2f",
            help="Average monthly cost for electricity, water, internet, etc."
        )
        total_items = st.number_input(
            "Total Items Produced Monthly for Allocation", value=int(costs.total_monthly_items_for_rent_utilities or 1000),
            min_value=1, step=1,
            help="To calculate cost per item, enter the total number of items (across all products) you typically produce in a month. This will be used to divide the overhead costs."
        )

        if st.form_submit_button("Save Global Costs"):
            costs.monthly_rent = Decimal(str(rent))
            costs.monthly_utilities = Decimal(str(utilities))
            costs.total_monthly_items_for_rent_utilities = total_items
            db.commit()
            st.success("Global costs updated successfully!")
            st.rerun()