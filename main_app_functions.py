# main_app_functions.py

import pandas as pd
from decimal import Decimal
from sqlalchemy.orm import Session, selectinload, joinedload

# Import all necessary models
from models import (
    Product, ProductMaterial, ProductProductionTask, ProductShippingTask,
    Employee, GlobalCosts
)

def calculate_cost_breakdown(product_id: int, db: Session, current_user_id: int):
    """
    Calculates a detailed cost breakdown for a given product.
    This is a core business logic function.
    """
    product = db.query(Product).options(
        selectinload(Product.materials).joinedload(ProductMaterial.ingredient_ref),
        selectinload(Product.production_tasks).joinedload(ProductProductionTask.employee_ref),
        selectinload(Product.production_tasks).joinedload(ProductProductionTask.standard_task_ref),
        selectinload(Product.shipping_tasks).joinedload(ProductShippingTask.employee_ref),
        selectinload(Product.shipping_tasks).joinedload(ProductShippingTask.standard_task_ref),
        joinedload(Product.salary_alloc_employee_ref).joinedload(Employee.global_salary_entry)
    ).filter(Product.id == product_id, Product.user_id == current_user_id).first()

    if not product:
        return None

    breakdown = {}
    
    # --- Material Costs ---
    material_details = []
    total_material_cost_per_item = Decimal('0.0')
    for pm in product.materials:
        if pm.ingredient_ref:
            ing = pm.ingredient_ref
            qty_grams = Decimal(str(pm.quantity_grams)) if pd.notna(pm.quantity_grams) else Decimal('0.0')
            price_per_unit = Decimal(str(ing.price_per_unit)) if pd.notna(ing.price_per_unit) else Decimal('0.0')
            unit_kg = Decimal(str(ing.unit_quantity_kg)) if pd.notna(ing.unit_quantity_kg) and ing.unit_quantity_kg > 0 else Decimal('1.0')
            cost = (qty_grams / Decimal('1000.0')) * (price_per_unit / unit_kg) if unit_kg > Decimal('0.0') else Decimal('0.0')
            total_material_cost_per_item += cost
            material_details.append({"Ingredient": ing.name, "Provider": ing.provider or "-","Qty (g)": qty_grams, "Cost": cost})
    breakdown['material_details'] = material_details
    breakdown['total_material_cost_per_item'] = total_material_cost_per_item

    # --- Production Labor Costs ---
    prod_labor_details = []
    total_production_labor_cost_per_item = Decimal('0.0')
    for ppt in product.production_tasks:
        if ppt.employee_ref:
            emp = ppt.employee_ref
            time_min = Decimal(str(ppt.time_minutes)) if pd.notna(ppt.time_minutes) else Decimal('0.0')
            hourly_rate = Decimal(str(emp.hourly_rate)) if pd.notna(emp.hourly_rate) else Decimal('0.0')
            items_proc = Decimal(str(ppt.items_processed_in_task)) if pd.notna(ppt.items_processed_in_task) and ppt.items_processed_in_task > 0 else Decimal('1.0')
            cost = (time_min / Decimal('60.0')) * hourly_rate
            cost_per_item = cost / items_proc if items_proc > Decimal('0.0') else Decimal('0.0')
            total_production_labor_cost_per_item += cost_per_item
            prod_labor_details.append({"Task": ppt.standard_task_ref.task_name if ppt.standard_task_ref else "N/A", "Employee": emp.name, "Time (min)": time_min, "Items in Task": items_proc, "Cost": cost_per_item})
    breakdown['prod_labor_details'] = prod_labor_details
    breakdown['total_production_labor_cost_per_item'] = total_production_labor_cost_per_item

    # --- Shipping Labor Costs ---
    ship_labor_details = []
    total_shipping_labor_cost_per_item = Decimal('0.0')
    for pst in product.shipping_tasks:
        if pst.employee_ref:
            emp = pst.employee_ref
            time_min = Decimal(str(pst.time_minutes)) if pd.notna(pst.time_minutes) else Decimal('0.0')
            hourly_rate = Decimal(str(emp.hourly_rate)) if pd.notna(emp.hourly_rate) else Decimal('0.0')
            items_proc = Decimal(str(pst.items_processed_in_task)) if pd.notna(pst.items_processed_in_task) and pst.items_processed_in_task > 0 else Decimal('1.0')
            cost = (time_min / Decimal('60.0')) * hourly_rate
            cost_per_item = cost / items_proc if items_proc > Decimal('0.0') else Decimal('0.0')
            total_shipping_labor_cost_per_item += cost_per_item
            ship_labor_details.append({"Task": pst.standard_task_ref.task_name if pst.standard_task_ref else "N/A", "Employee": emp.name, "Time (min)": time_min, "Items in Task": items_proc, "Cost": cost_per_item})
    breakdown['ship_labor_details'] = ship_labor_details
    breakdown['total_shipping_labor_cost_per_item'] = total_shipping_labor_cost_per_item

    # --- Packaging & Direct COGS ---
    pkg_label_cost = Decimal(str(product.packaging_label_cost)) if pd.notna(product.packaging_label_cost) else Decimal('0.0')
    pkg_material_cost = Decimal(str(product.packaging_material_cost)) if pd.notna(product.packaging_material_cost) else Decimal('0.0')
    breakdown['packaging_label_cost_per_item'] = pkg_label_cost
    breakdown['packaging_material_cost_per_item'] = pkg_material_cost
    breakdown['total_packaging_cost_per_item'] = pkg_label_cost + pkg_material_cost
    breakdown['direct_cogs_per_item'] = (total_material_cost_per_item + total_production_labor_cost_per_item + total_shipping_labor_cost_per_item + breakdown['total_packaging_cost_per_item'])

    # --- Allocated Overheads ---
    allocated_salary_cost_per_item = Decimal('0.0')
    if product.salary_allocation_employee_id and product.salary_alloc_employee_ref and product.salary_alloc_employee_ref.global_salary_entry and pd.notna(product.salary_allocation_items_per_month) and product.salary_allocation_items_per_month > 0:
        monthly_salary = Decimal(str(product.salary_alloc_employee_ref.global_salary_entry.monthly_amount)) if pd.notna(product.salary_alloc_employee_ref.global_salary_entry.monthly_amount) else Decimal('0.0')
        alloc_items = Decimal(str(product.salary_allocation_items_per_month))
        allocated_salary_cost_per_item = monthly_salary / alloc_items if alloc_items > Decimal('0.0') else Decimal('0.0')
    breakdown['allocated_salary_cost_per_item'] = allocated_salary_cost_per_item

    allocated_rent_utilities_cost_per_item = Decimal('0.0')
    global_costs_obj = db.query(GlobalCosts).filter(GlobalCosts.user_id == current_user_id).first()
    if global_costs_obj and pd.notna(product.rent_utilities_allocation_items_per_month) and product.rent_utilities_allocation_items_per_month > 0:
        rent = Decimal(str(global_costs_obj.monthly_rent)) if pd.notna(global_costs_obj.monthly_rent) else Decimal('0.0')
        utilities = Decimal(str(global_costs_obj.monthly_utilities)) if pd.notna(global_costs_obj.monthly_utilities) else Decimal('0.0')
        total_monthly_fixed_overheads = rent + utilities
        alloc_items_rent = Decimal(str(product.rent_utilities_allocation_items_per_month))
        allocated_rent_utilities_cost_per_item = total_monthly_fixed_overheads / alloc_items_rent if alloc_items_rent > Decimal('0.0') else Decimal('0.0')
    breakdown['allocated_rent_utilities_cost_per_item'] = allocated_rent_utilities_cost_per_item
    
    breakdown['total_allocated_overheads_per_item'] = allocated_salary_cost_per_item + allocated_rent_utilities_cost_per_item
    breakdown['total_production_cost_per_item'] = breakdown['direct_cogs_per_item'] + breakdown['total_allocated_overheads_per_item']

    # --- Retail Channel Metrics ---
    retail_price = Decimal(str(product.retail_price_per_item)) if pd.notna(product.retail_price_per_item) else Decimal('0.0')
    items_per_retail_order = Decimal('1.0')
    retail_avg_order_val = Decimal(str(product.retail_avg_order_value)) if pd.notna(product.retail_avg_order_value) else Decimal('0.0')
    if retail_avg_order_val > Decimal('0.0') and retail_price > Decimal('0.0'):
        items_per_retail_order = retail_avg_order_val / retail_price
    if items_per_retail_order <= Decimal('0.0'): items_per_retail_order = Decimal('1.0') 
    
    retail_cc_fee_percent_val = Decimal(str(product.retail_cc_fee_percent)) if pd.notna(product.retail_cc_fee_percent) else Decimal('0.0')
    retail_platform_fee_percent_val = Decimal(str(product.retail_platform_fee_percent)) if pd.notna(product.retail_platform_fee_percent) else Decimal('0.0')
    retail_shipping_cost_paid_val = Decimal(str(product.retail_shipping_cost_paid_by_you)) if pd.notna(product.retail_shipping_cost_paid_by_you) else Decimal('0.0')
    
    retail_cc_fee = retail_price * retail_cc_fee_percent_val
    retail_platform_fee = retail_price * retail_platform_fee_percent_val
    retail_shipping_per_item = retail_shipping_cost_paid_val / items_per_retail_order
    total_retail_channel_costs = retail_cc_fee + retail_platform_fee + retail_shipping_per_item
    total_cost_retail_item = breakdown['total_production_cost_per_item'] + total_retail_channel_costs
    profit_retail = retail_price - total_cost_retail_item
    margin_retail = (profit_retail / retail_price) * Decimal('100.0') if retail_price > Decimal('0.0') else Decimal('0.0')
    breakdown['retail_metrics'] = {"price": retail_price, "cc_fee": retail_cc_fee, "platform_fee": retail_platform_fee, "shipping_cost": retail_shipping_per_item, "total_channel_costs": total_retail_channel_costs, "total_cost_item": total_cost_retail_item, "profit": profit_retail, "margin_percent": margin_retail}

    # --- Wholesale Channel Metrics ---
    wholesale_price = Decimal(str(product.wholesale_price_per_item)) if pd.notna(product.wholesale_price_per_item) else Decimal('0.0')
    items_per_ws_order = Decimal('1.0')
    ws_avg_order_val = Decimal(str(product.wholesale_avg_order_value)) if pd.notna(product.wholesale_avg_order_value) else Decimal('0.0')
    if ws_avg_order_val > Decimal('0.0') and wholesale_price > Decimal('0.0'):
        items_per_ws_order = ws_avg_order_val / wholesale_price
    if items_per_ws_order <= Decimal('0.0'): items_per_ws_order = Decimal('1.0')
    
    ws_commission_percent_val = Decimal(str(product.wholesale_commission_percent)) if pd.notna(product.wholesale_commission_percent) else Decimal('0.0')
    ws_processing_fee_percent_val = Decimal(str(product.wholesale_processing_fee_percent)) if pd.notna(product.wholesale_processing_fee_percent) else Decimal('0.0')
    ws_flat_fee_per_order_val = Decimal(str(product.wholesale_flat_fee_per_order)) if pd.notna(product.wholesale_flat_fee_per_order) else Decimal('0.0')
    
    ws_commission = wholesale_price * ws_commission_percent_val
    ws_processing_fee = wholesale_price * ws_processing_fee_percent_val
    ws_flat_fee_per_item = ws_flat_fee_per_order_val / items_per_ws_order
    total_wholesale_channel_costs = ws_commission + ws_processing_fee + ws_flat_fee_per_item
    total_cost_wholesale_item = breakdown['total_production_cost_per_item'] + total_wholesale_channel_costs
    profit_wholesale = wholesale_price - total_cost_wholesale_item
    margin_wholesale = (profit_wholesale / wholesale_price) * Decimal('100.0') if wholesale_price > Decimal('0.0') else Decimal('0.0')
    breakdown['wholesale_metrics'] = {"price": wholesale_price, "commission": ws_commission, "processing_fee": ws_processing_fee, "flat_fee_item_share": ws_flat_fee_per_item, "total_channel_costs": total_wholesale_channel_costs, "total_cost_item": total_cost_wholesale_item, "profit": profit_wholesale, "margin_percent": margin_wholesale}

    # --- Blended & Final Metrics ---
    ws_dist_val = Decimal(str(product.distribution_wholesale_percentage)) if pd.notna(product.distribution_wholesale_percentage) else Decimal('0.0')
    rt_dist_val = Decimal('1.0') - ws_dist_val
    breakdown['blended_avg_price'] = (retail_price * rt_dist_val) + (wholesale_price * ws_dist_val)
    breakdown['blended_avg_total_cost'] = (total_cost_retail_item * rt_dist_val) + (total_cost_wholesale_item * ws_dist_val)
    breakdown['blended_avg_profit'] = breakdown['blended_avg_price'] - breakdown['blended_avg_total_cost']
    breakdown['blended_avg_margin_percent'] = (breakdown['blended_avg_profit'] / breakdown['blended_avg_price']) * Decimal('100.0') if breakdown['blended_avg_price'] > Decimal('0.0') else Decimal('0.0')
    
    buffer_percentage_val = Decimal(str(product.buffer_percentage)) if pd.notna(product.buffer_percentage) else Decimal('0.0')
    breakdown['cost_plus_buffer'] = breakdown['total_production_cost_per_item'] * (Decimal('1.0') + buffer_percentage_val)
    
    return breakdown