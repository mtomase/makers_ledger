# pages/page_06_cost_breakdown.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from models import Product, User

# --- CORRECTED IMPORT ---
from main_app_functions import calculate_cost_breakdown 
# --- END CORRECTION ---

from utils.formatters import format_currency, format_percentage, format_decimal_for_table

def render(db: Session, user: User, is_mobile: bool):
    st.header("📊 Product Cost Breakdown")
    products_for_calc = db.query(Product).filter(Product.user_id == user.id).order_by(Product.product_name).all()
    
    if not products_for_calc:
        st.info("No products found. Please add products in 'Manage Products' to see a cost breakdown.")
        return

    product_names_for_calc = {p.product_name: p.id for p in products_for_calc}
    
    if 'calc_selected_product_name' not in st.session_state or st.session_state.calc_selected_product_name not in product_names_for_calc:
        st.session_state.calc_selected_product_name = list(product_names_for_calc.keys())[0]

    selected_product_name_calc = st.selectbox(
        "Select Product for Breakdown:", 
        options=list(product_names_for_calc.keys()), 
        key="calc_prod_select_sb",
        index=list(product_names_for_calc.keys()).index(st.session_state.calc_selected_product_name)
    )
    if selected_product_name_calc != st.session_state.calc_selected_product_name:
        st.session_state.calc_selected_product_name = selected_product_name_calc
    
    if selected_product_name_calc:
        selected_product_id_calc = product_names_for_calc[selected_product_name_calc]
        breakdown_data = calculate_cost_breakdown(selected_product_id_calc, db, user.id)

        if breakdown_data:
            st.subheader(f"Cost Analysis for: **{selected_product_name_calc}**")
            
            # --- The rest of the rendering logic is the same ---
            if is_mobile:
                st.metric("Total Production Cost/Item", format_currency(breakdown_data['total_production_cost_per_item']))
                st.metric("Target Price (with Buffer)", format_currency(breakdown_data['cost_plus_buffer']))
                st.metric("Blended Avg Profit/Item", format_currency(breakdown_data['blended_avg_profit']))
            else:
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Production Cost/Item", format_currency(breakdown_data['total_production_cost_per_item']))
                col2.metric("Target Price (with Buffer)", format_currency(breakdown_data['cost_plus_buffer']))
                col3.metric("Blended Avg Profit/Item", format_currency(breakdown_data['blended_avg_profit']))
            
            st.markdown("---")
            with st.expander("💰 Direct COGS Details", expanded=True):
                st.markdown(f"**Total Material Cost/Item:** {format_currency(breakdown_data['total_material_cost_per_item'])}")
                if breakdown_data['material_details']:
                    df_mat = pd.DataFrame(breakdown_data['material_details']); df_mat_display = df_mat.copy()
                    df_mat_display["Qty (g)"] = df_mat_display["Qty (g)"].apply(lambda x: format_decimal_for_table(x, '0.001'))
                    df_mat_display["Cost"] = df_mat_display["Cost"].apply(format_currency)
                    st.dataframe(df_mat_display, hide_index=True, use_container_width=True)
                
                st.markdown(f"**Total Production Labor Cost/Item:** {format_currency(breakdown_data['total_production_labor_cost_per_item'])}")
                if breakdown_data['prod_labor_details']:
                    df_prod_labor = pd.DataFrame(breakdown_data['prod_labor_details']); df_prod_labor_display = df_prod_labor.copy()
                    df_prod_labor_display["Time (min)"] = df_prod_labor_display["Time (min)"].apply(lambda x: format_decimal_for_table(x, '0.1'))
                    df_prod_labor_display["Items in Task"] = df_prod_labor_display["Items in Task"].apply(lambda x: format_decimal_for_table(x, '0'))
                    df_prod_labor_display["Cost"] = df_prod_labor_display["Cost"].apply(format_currency)
                    st.dataframe(df_prod_labor_display, hide_index=True, use_container_width=True)
                
                # ... The rest of the file is identical to the previous version ...
                st.markdown(f"**Total Shipping Labor Cost/Item (Direct):** {format_currency(breakdown_data['total_shipping_labor_cost_per_item'])}")
                if breakdown_data['ship_labor_details']:
                    df_ship_labor = pd.DataFrame(breakdown_data['ship_labor_details']); df_ship_labor_display = df_ship_labor.copy()
                    df_ship_labor_display["Time (min)"] = df_ship_labor_display["Time (min)"].apply(lambda x: format_decimal_for_table(x, '0.1'))
                    df_ship_labor_display["Items in Task"] = df_ship_labor_display["Items in Task"].apply(lambda x: format_decimal_for_table(x, '0'))
                    df_ship_labor_display["Cost"] = df_ship_labor_display["Cost"].apply(format_currency)
                    st.dataframe(df_ship_labor_display, hide_index=True, use_container_width=True)
                
                st.markdown(f"**Packaging - Label Cost/Item:** {format_currency(breakdown_data['packaging_label_cost_per_item'])}")
                st.markdown(f"**Packaging - Material Cost/Item:** {format_currency(breakdown_data['packaging_material_cost_per_item'])}")
                st.markdown(f"**Total Packaging Cost/Item:** {format_currency(breakdown_data['total_packaging_cost_per_item'])}")
                st.markdown(f"##### **Subtotal Direct COGS/Item:** {format_currency(breakdown_data['direct_cogs_per_item'])}")
            
            with st.expander("🏢 Allocated Overheads per Item"):
                st.markdown(f"**Allocated Salary Cost/Item:** {format_currency(breakdown_data['allocated_salary_cost_per_item'])}")
                st.markdown(f"**Allocated Rent/Utilities Cost/Item:** {format_currency(breakdown_data['allocated_rent_utilities_cost_per_item'])}")
                st.markdown(f"##### **Subtotal Allocated Overheads/Item:** {format_currency(breakdown_data['total_allocated_overheads_per_item'])}")
            
            st.markdown("---")
            st.subheader("📈 Channel Performance Analysis (per Item)")
            
            if is_mobile:
                st.markdown("#### 🛍️ Retail Channel")
                rt = breakdown_data['retail_metrics']
                st.metric("Retail Price", format_currency(rt['price']))
                st.write(f"CC Fee: {format_currency(rt['cc_fee'])} | Platform Fee: {format_currency(rt['platform_fee'])}")
                st.write(f"Shipping Paid by You (per item): {format_currency(rt['shipping_cost'])}")
                st.write(f"**Total Retail Channel Costs:** {format_currency(rt['total_channel_costs'])}")
                st.metric("Total Cost (Prod + Retail Fees)", format_currency(rt['total_cost_item']))
                st.metric("Profit per Retail Item", format_currency(rt['profit']), delta_color="normal")
                st.metric("Retail Margin", format_percentage(rt['margin_percent']))
                st.markdown("---")
                st.markdown("#### 🏭 Wholesale Channel")
                ws = breakdown_data['wholesale_metrics']
                st.metric("Wholesale Price", format_currency(ws['price']))
                st.write(f"Commission: {format_currency(ws['commission'])} | Processing Fee: {format_currency(ws['processing_fee'])}")
                st.write(f"Flat Fee (Item Share): {format_currency(ws['flat_fee_item_share'])}")
                st.write(f"**Total Wholesale Channel Costs:** {format_currency(ws['total_channel_costs'])}")
                st.metric("Total Cost (Prod + Wholesale Fees)", format_currency(ws['total_cost_item']))
                st.metric("Profit per Wholesale Item", format_currency(ws['profit']), delta_color="normal")
                st.metric("Wholesale Margin", format_percentage(ws['margin_percent']))
            else:
                col_ret, col_ws = st.columns(2)
                with col_ret:
                    st.markdown("#### 🛍️ Retail Channel")
                    rt = breakdown_data['retail_metrics']
                    st.metric("Retail Price", format_currency(rt['price']))
                    st.write(f"CC Fee: {format_currency(rt['cc_fee'])} | Platform Fee: {format_currency(rt['platform_fee'])}")
                    st.write(f"Shipping Paid by You (per item): {format_currency(rt['shipping_cost'])}")
                    st.write(f"**Total Retail Channel Costs:** {format_currency(rt['total_channel_costs'])}")
                    st.metric("Total Cost (Prod + Retail Fees)", format_currency(rt['total_cost_item']))
                    st.metric("Profit per Retail Item", format_currency(rt['profit']), delta_color="normal")
                    st.metric("Retail Margin", format_percentage(rt['margin_percent']))
                with col_ws:
                    st.markdown("#### 🏭 Wholesale Channel")
                    ws = breakdown_data['wholesale_metrics']
                    st.metric("Wholesale Price", format_currency(ws['price']))
                    st.write(f"Commission: {format_currency(ws['commission'])} | Processing Fee: {format_currency(ws['processing_fee'])}")
                    st.write(f"Flat Fee (Item Share): {format_currency(ws['flat_fee_item_share'])}")
                    st.write(f"**Total Wholesale Channel Costs:** {format_currency(ws['total_channel_costs'])}")
                    st.metric("Total Cost (Prod + Wholesale Fees)", format_currency(ws['total_cost_item']))
                    st.metric("Profit per Wholesale Item", format_currency(ws['profit']), delta_color="normal")
                    st.metric("Wholesale Margin", format_percentage(ws['margin_percent']))
            
            st.markdown("---")
            st.subheader("⚖️ Blended Performance (Weighted by Distribution)")
            st.metric("Weighted Average Selling Price/Item", format_currency(breakdown_data['blended_avg_price']))
            st.metric("Weighted Average Total Cost/Item", format_currency(breakdown_data['blended_avg_total_cost']))
            st.metric("Weighted Average Profit/Item", format_currency(breakdown_data['blended_avg_profit']), delta_color="normal")
            st.metric("Weighted Average Margin", format_percentage(breakdown_data['blended_avg_margin_percent']))
        else:
            st.error("Could not calculate breakdown. Ensure product data is complete.")