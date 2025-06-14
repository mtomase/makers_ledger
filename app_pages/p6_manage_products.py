# app_pages/p6_manage_products.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from decimal import Decimal, ROUND_HALF_UP
import sys
import os

# --- Boilerplate: Add project root to path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import (
    SessionLocal, User, Product, Ingredient, ProductMaterial, GlobalCosts, GlobalSalary,
    Employee, StandardProductionTask, ProductProductionTask, StockAddition, PurchaseOrder
)

# --- REBUILT Cost Calculation Logic (from old app) ---
def calculate_full_costs(product_id: int, db: Session, user_id: int):
    # Assuming Product model has 'shipping_tasks' relationship. If not, this line can be removed.
    product = db.query(Product).options(
        selectinload(Product.materials).joinedload(ProductMaterial.ingredient_ref),
        selectinload(Product.production_tasks).joinedload(ProductProductionTask.standard_task_ref),
        selectinload(Product.production_tasks).joinedload(ProductProductionTask.employee_ref),
        selectinload(Product.shipping_tasks),
        joinedload(Product.salary_alloc_employee_ref).joinedload(Employee.global_salary_entry)
    ).filter(Product.id == product_id, Product.user_id == user_id).first()

    if not product: return None

    breakdown = {}
    
    # Material Cost
    material_cost_per_item = Decimal('0.0')
    missing_ingredient_costs = []
    material_details = []
    if product.materials:
        for material in product.materials:
            additions = db.query(StockAddition).join(PurchaseOrder).filter(
                StockAddition.ingredient_id == material.ingredient_id,
                PurchaseOrder.user_id == user_id
            ).all()
            if not additions:
                missing_ingredient_costs.append(material.ingredient_ref.name)
                continue
            total_cost_for_ingredient = Decimal('0.0')
            total_grams_for_ingredient = Decimal('0.0')
            for add in additions:
                total_items_in_po = db.query(func.count(StockAddition.id)).filter(StockAddition.purchase_order_id == add.purchase_order_id).scalar()
                shipping_per_item = add.purchase_order_ref.shipping_cost / total_items_in_po if total_items_in_po > 0 else Decimal('0.0')
                true_cost_of_addition = add.item_cost + shipping_per_item
                total_cost_for_ingredient += true_cost_of_addition
                total_grams_for_ingredient += add.quantity_added_grams
            
            if total_grams_for_ingredient > 0:
                avg_cost_per_gram = total_cost_for_ingredient / total_grams_for_ingredient
                cost_for_material = material.quantity_grams * avg_cost_per_gram
                material_cost_per_item += cost_for_material
                material_details.append({"Ingredient": material.ingredient_ref.name, "Qty (g)": material.quantity_grams, "Cost": cost_for_material})
            else:
                missing_ingredient_costs.append(material.ingredient_ref.name)
    
    breakdown['material_details'] = material_details
    breakdown['total_material_cost_per_item'] = material_cost_per_item
    breakdown['missing_ingredient_costs'] = missing_ingredient_costs

    # Labor Cost
    labor_cost_per_item = Decimal('0.0')
    labor_details = []
    for p_task in product.production_tasks:
        if p_task.standard_task_ref and p_task.employee_ref and p_task.time_minutes:
            hourly_rate = p_task.employee_ref.hourly_rate or Decimal('0.0')
            cost = (Decimal(str(p_task.time_minutes)) / 60) * hourly_rate
            labor_cost_per_item += cost
            labor_details.append({"Task": p_task.standard_task_ref.task_name, "Employee": p_task.employee_ref.name, "Time (min)": p_task.time_minutes, "Cost": cost})
    breakdown['labor_details'] = labor_details
    breakdown['total_labor_cost_per_item'] = labor_cost_per_item

    # Overhead Cost
    allocated_salary_cost_per_item = Decimal('0.0')
    if product.salary_allocation_employee_id and product.salary_alloc_employee_ref and product.salary_alloc_employee_ref.global_salary_entry:
        monthly_salary = product.salary_alloc_employee_ref.global_salary_entry.monthly_amount or Decimal('0.0')
        alloc_items = product.salary_allocation_items_per_month or 1
        if alloc_items > 0:
            allocated_salary_cost_per_item = monthly_salary / Decimal(alloc_items)
    
    allocated_rent_utilities_cost_per_item = Decimal('0.0')
    global_costs = db.query(GlobalCosts).filter(GlobalCosts.user_id == user_id).first()
    if global_costs:
        total_monthly_overheads = (global_costs.monthly_rent or Decimal('0.0')) + (global_costs.monthly_utilities or Decimal('0.0'))
        alloc_items = product.rent_utilities_allocation_items_per_month or 1
        if alloc_items > 0:
            allocated_rent_utilities_cost_per_item = total_monthly_overheads / Decimal(alloc_items)
    
    breakdown['allocated_salary_cost_per_item'] = allocated_salary_cost_per_item
    breakdown['allocated_rent_utilities_cost_per_item'] = allocated_rent_utilities_cost_per_item
    breakdown['total_allocated_overheads_per_item'] = allocated_salary_cost_per_item + allocated_rent_utilities_cost_per_item

    # Packaging Cost
    pkg_label_cost = product.packaging_label_cost or Decimal('0.0')
    pkg_material_cost = product.packaging_material_cost or Decimal('0.0')
    breakdown['packaging_label_cost_per_item'] = pkg_label_cost
    breakdown['packaging_material_cost_per_item'] = pkg_material_cost
    breakdown['total_packaging_cost_per_item'] = pkg_label_cost + pkg_material_cost

    # Total Production Cost
    total_production_cost = material_cost_per_item + labor_cost_per_item + breakdown['total_allocated_overheads_per_item'] + breakdown['total_packaging_cost_per_item']
    breakdown['total_production_cost_per_item'] = total_production_cost
    
    # Channel Costs & Profitability
    retail_price = product.retail_price_per_item or Decimal('0.0')
    retail_cc_fee = retail_price * (product.retail_cc_fee_percent or Decimal('0.0'))
    retail_platform_fee = retail_price * (product.retail_platform_fee_percent or Decimal('0.0'))
    total_retail_channel_costs = retail_cc_fee + retail_platform_fee + (product.retail_shipping_cost_paid_by_you or Decimal('0.0'))
    total_cost_retail_item = total_production_cost + total_retail_channel_costs
    profit_retail = retail_price - total_cost_retail_item
    margin_retail = (profit_retail / retail_price) * 100 if retail_price > 0 else Decimal('0.0')
    breakdown['retail_metrics'] = {"price": retail_price, "total_channel_costs": total_retail_channel_costs, "total_cost_item": total_cost_retail_item, "profit": profit_retail, "margin_percent": margin_retail}

    wholesale_price = product.wholesale_price_per_item or Decimal('0.0')
    ws_commission = wholesale_price * (product.wholesale_commission_percent or Decimal('0.0'))
    ws_processing_fee = wholesale_price * (product.wholesale_processing_fee_percent or Decimal('0.0'))
    ws_flat_fee = product.wholesale_flat_fee_per_order or Decimal('0.0')
    total_wholesale_channel_costs = ws_commission + ws_processing_fee + ws_flat_fee
    total_cost_wholesale_item = total_production_cost + total_wholesale_channel_costs
    profit_wholesale = wholesale_price - total_cost_wholesale_item
    margin_wholesale = (profit_wholesale / wholesale_price) * 100 if wholesale_price > 0 else Decimal('0.0')
    breakdown['wholesale_metrics'] = {"price": wholesale_price, "total_channel_costs": total_wholesale_channel_costs, "total_cost_item": total_cost_wholesale_item, "profit": profit_wholesale, "margin_percent": margin_wholesale}

    dist_ws = product.distribution_wholesale_percentage or Decimal('0.5')
    dist_rt = Decimal('1.0') - dist_ws
    breakdown['blended_avg_price'] = (retail_price * dist_rt) + (wholesale_price * dist_ws)
    breakdown['blended_avg_total_cost'] = (total_cost_retail_item * dist_rt) + (total_cost_wholesale_item * dist_ws)
    breakdown['blended_avg_profit'] = breakdown['blended_avg_price'] - breakdown['blended_avg_total_cost']
    breakdown['blended_avg_margin_percent'] = (breakdown['blended_avg_profit'] / breakdown['blended_avg_price']) * 100 if breakdown['blended_avg_price'] > 0 else Decimal('0.0')
    
    buffer = product.buffer_percentage or Decimal('0.0')
    breakdown['cost_plus_buffer'] = total_production_cost * (Decimal('1.0') + buffer)

    return breakdown

# --- UI Rendering Functions ---

def render_new_product_form(user: User):
    st.subheader("➕ Add New Product")
    with st.form("new_product_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        new_product_name = c1.text_input("New Product Name*")
        new_product_code = c2.text_input("Product Code/SKU (optional)")
        if st.form_submit_button("Create Product"):
            if not new_product_name.strip():
                st.error("Product Name is a required field.")
            else:
                with SessionLocal() as db:
                    try:
                        product_name_stripped = new_product_name.strip()
                        new_prod = Product(user_id=user.id, product_name=product_name_stripped, product_code=new_product_code.strip() or None)
                        db.add(new_prod)
                        db.commit()
                        st.success(f"Product '{product_name_stripped}' created!")
                        st.session_state.selected_product_name = product_name_stripped
                    except IntegrityError:
                        db.rollback()
                        st.error(f"A product with the name '{new_product_name}' already exists.")
                    except Exception as e:
                        db.rollback()
                        st.error(f"An error occurred: {e}")
                st.rerun()

def render_product_editor(db: Session, user: User, product: Product, is_mobile: bool):
    st.header(f"⚙️ Editing: {product.product_name}")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Recipe", "Workflow", "Pricing & Channels", "Cost Analysis"])

    with tab1:
        st.subheader("Product Recipe / Bill of Materials")
        all_ingredients = db.query(Ingredient).filter(Ingredient.user_id == user.id).order_by(Ingredient.name).all()
        
        # --- ROBUST FIX: Check for prerequisites ---
        prerequisites_met_recipe = bool(all_ingredients)
        
        if not prerequisites_met_recipe:
            st.warning("No ingredients found. Please add ingredients first on the 'Manage Ingredients' page to create a recipe.")

        # --- ROBUST FIX: Always create the DataFrame with the correct columns ---
        df_recipe_columns = {
            "ID": [], "Ingredient": [], "Quantity (g)": []
        }
        
        recipe_data = []
        if product.materials:
            recipe_data = [{"ID": m.id, "Ingredient": m.ingredient_ref.name, "Quantity (g)": m.quantity_grams} for m in product.materials]
        
        df_recipe = pd.DataFrame(recipe_data if recipe_data else df_recipe_columns)

        edited_recipe_df = st.data_editor(
            df_recipe, 
            num_rows="dynamic", 
            key="recipe_editor",
            disabled=not prerequisites_met_recipe,
            column_config={
                "ID": None,
                "Ingredient": st.column_config.SelectboxColumn("Ingredient*", options=[ing.name for ing in all_ingredients], required=True),
                "Quantity (g)": st.column_config.NumberColumn("Quantity (g)*", required=True, min_value=0.0, format="%.3f")
            }, 
            use_container_width=True, 
            hide_index=True
        )
        
        if st.button("💾 Save Recipe Changes", type="primary", disabled=not prerequisites_met_recipe):
            with SessionLocal() as transaction_db:
                try:
                    transaction_db.query(ProductMaterial).filter(ProductMaterial.product_id == product.id).delete(synchronize_session=False)
                    ing_map = {ing.name: ing.id for ing in all_ingredients}
                    for _, row in edited_recipe_df.iterrows():
                        ing_name, quantity = row["Ingredient"], row["Quantity (g)"]
                        if not ing_name or pd.isna(quantity) or quantity <= 0: continue
                        ing_id = ing_map.get(ing_name)
                        if ing_id:
                            transaction_db.add(ProductMaterial(product_id=product.id, ingredient_id=ing_id, quantity_grams=Decimal(str(quantity))))
                    transaction_db.commit()
                    st.success("Recipe updated successfully!")
                except Exception as e:
                    transaction_db.rollback(); st.error(f"Error saving recipe: {e}")
            st.rerun()

    with tab2:
        st.subheader("Production Tasks & Labor")
        all_tasks = db.query(StandardProductionTask).filter(StandardProductionTask.user_id == user.id).all()
        all_employees = db.query(Employee).filter(Employee.user_id == user.id).all()

        task_names = [t.task_name for t in all_tasks]
        employee_names = [e.name for e in all_employees]
        
        prerequisites_met_workflow = bool(task_names and employee_names)

        if not prerequisites_met_workflow:
            if not task_names:
                st.warning("You must define at least one 'Standard Production Task' before building a workflow. Please go to the 'Settings' page to add tasks.")
            if not employee_names:
                st.warning("You must add at least one 'Employee' before assigning tasks. Please go to the 'Settings' page to add employees.")
        
        df_workflow_columns = {
            "ID": [], "Task": [], "Assigned To": [], "Time (minutes)": []
        }
        
        workflow_data = []
        if product.production_tasks:
             workflow_data = [
                {"ID": pt.id, "Task": pt.standard_task_ref.task_name, "Assigned To": pt.employee_ref.name, "Time (minutes)": pt.time_minutes} 
                for pt in product.production_tasks if pt.standard_task_ref and pt.employee_ref
            ]
        
        df_workflow = pd.DataFrame(workflow_data if workflow_data else df_workflow_columns)

        edited_workflow_df = st.data_editor(
            df_workflow, 
            num_rows="dynamic", 
            key="workflow_editor",
            disabled=not prerequisites_met_workflow,
            column_config={
                "ID": None,
                "Task": st.column_config.SelectboxColumn("Task*", options=task_names, required=True),
                "Assigned To": st.column_config.SelectboxColumn("Assigned To*", options=employee_names, required=True),
                "Time (minutes)": st.column_config.NumberColumn("Time (minutes)*", required=True, min_value=0.1, format="%.1f")
            }, 
            use_container_width=True, 
            hide_index=True
        )
        
        if st.button("💾 Save Workflow Changes", type="primary", disabled=not prerequisites_met_workflow):
            with SessionLocal() as transaction_db:
                try:
                    transaction_db.query(ProductProductionTask).filter(ProductProductionTask.product_id == product.id).delete(synchronize_session=False)
                    task_map = {t.task_name: t.id for t in all_tasks}
                    emp_map = {e.name: e.id for e in all_employees}
                    for _, row in edited_workflow_df.iterrows():
                        task_name, emp_name, time = row["Task"], row["Assigned To"], row["Time (minutes)"]
                        if not all([task_name, emp_name, pd.notna(time)]): continue
                        task_id, emp_id = task_map.get(task_name), emp_map.get(emp_name)
                        if task_id and emp_id:
                            transaction_db.add(ProductProductionTask(product_id=product.id, standard_task_id=task_id, employee_id=emp_id, time_minutes=Decimal(str(time))))
                    transaction_db.commit()
                    st.success("Workflow updated successfully!")
                except Exception as e:
                    transaction_db.rollback(); st.error(f"Error saving workflow: {e}")
            st.rerun()

    with tab3:
        st.subheader("Pricing, Packaging, Overheads & Channels")
        with st.form("pricing_form"):
            st.markdown("#### Pricing Strategy")
            c1, c2, c3 = st.columns(3)
            retail_price = c1.number_input("Retail Price/Item (€)", value=float(product.retail_price_per_item or 0.0), format="%.2f")
            wholesale_price = c2.number_input("Wholesale Price/Item (€)", value=float(product.wholesale_price_per_item or 0.0), format="%.2f")
            buffer = c3.slider("Profit Buffer (%)", 0, 200, int((product.buffer_percentage or 0)*100), format="%d%%")
            
            st.markdown("#### Packaging Costs (per Item)")
            c1, c2 = st.columns(2)
            label_cost = c1.number_input("Label Cost/Item (€)", value=float(product.packaging_label_cost or 0.0), format="%.3f")
            pkg_cost = c2.number_input("Other Packaging Cost/Item (€)", value=float(product.packaging_material_cost or 0.0), format="%.3f")

            st.markdown("#### Overhead Allocation")
            all_salaried_employees = db.query(Employee).join(GlobalSalary).filter(Employee.user_id==user.id).all()
            salaried_emp_options = {emp.id: emp.name for emp in all_salaried_employees}
            salaried_emp_options[None] = "None"
            
            c1, c2 = st.columns(2)
            selected_sal_emp_id = c1.selectbox("Allocate Salary Of", options=list(salaried_emp_options.keys()), format_func=lambda x: salaried_emp_options[x], index=list(salaried_emp_options.keys()).index(product.salary_allocation_employee_id) if product.salary_allocation_employee_id in salaried_emp_options else 0)
            sal_alloc_items = c2.number_input("Items/Month (for Salary Alloc.)", value=int(product.salary_allocation_items_per_month or 1000), min_value=1)
            rent_alloc_items = c1.number_input("Items/Month (for Rent/Util Alloc.)", value=int(product.rent_utilities_allocation_items_per_month or 1000), min_value=1)
            
            st.markdown("#### Sales Channel Details")
            dist_ws = st.slider("Wholesale Distribution (%)", 0, 100, int((product.distribution_wholesale_percentage or 0)*100))
            
            with st.expander("Retail Channel Fees"):
                r1, r2, r3 = st.columns(3)
                ret_cc = r1.number_input("Retail CC Fee (%)", value=float((product.retail_cc_fee_percent or 0)*100), format="%.2f")
                ret_plat = r2.number_input("Retail Platform Fee (%)", value=float((product.retail_platform_fee_percent or 0)*100), format="%.2f")
                ret_ship = r3.number_input("Retail Shipping Paid By You (€)", value=float(product.retail_shipping_cost_paid_by_you or 0.0), format="%.2f")

            with st.expander("Wholesale Channel Fees"):
                w1, w2, w3 = st.columns(3)
                ws_comm = w1.number_input("Wholesale Commission (%)", value=float((product.wholesale_commission_percent or 0)*100), format="%.2f")
                ws_proc = w2.number_input("Wholesale Processing Fee (%)", value=float((product.wholesale_processing_fee_percent or 0)*100), format="%.2f")
                ws_flat = w3.number_input("Wholesale Flat Fee/Order (€)", value=float(product.wholesale_flat_fee_per_order or 0.0), format="%.2f")

            if st.form_submit_button("💾 Save Pricing & Channel Details", type="primary"):
                with SessionLocal() as transaction_db:
                    p_to_update = transaction_db.query(Product).filter(Product.id == product.id).one()
                    p_to_update.retail_price_per_item = Decimal(str(retail_price))
                    p_to_update.wholesale_price_per_item = Decimal(str(wholesale_price))
                    p_to_update.buffer_percentage = Decimal(buffer) / 100
                    p_to_update.packaging_label_cost = Decimal(str(label_cost))
                    p_to_update.packaging_material_cost = Decimal(str(pkg_cost))
                    p_to_update.salary_allocation_employee_id = selected_sal_emp_id
                    p_to_update.salary_allocation_items_per_month = sal_alloc_items
                    p_to_update.rent_utilities_allocation_items_per_month = rent_alloc_items
                    p_to_update.distribution_wholesale_percentage = Decimal(dist_ws) / 100
                    p_to_update.retail_cc_fee_percent = Decimal(ret_cc) / 100
                    p_to_update.retail_platform_fee_percent = Decimal(ret_plat) / 100
                    p_to_update.retail_shipping_cost_paid_by_you = Decimal(str(ret_ship))
                    p_to_update.wholesale_commission_percent = Decimal(ws_comm) / 100
                    p_to_update.wholesale_processing_fee_percent = Decimal(ws_proc) / 100
                    p_to_update.wholesale_flat_fee_per_order = Decimal(str(ws_flat))
                    transaction_db.commit()
                    st.success("Pricing and channel details saved!")
                st.rerun()

    with tab4:
        render_cost_analysis(db, user, product, is_mobile)

def render_cost_analysis(db: Session, user: User, product: Product, is_mobile: bool):
    st.header(f"🔍 Cost & Profit Analysis for: {product.product_name}")
    
    cost_data = calculate_full_costs(product.id, db, user.id)
    
    if cost_data is None: 
        st.error("An error occurred during cost calculation.")
        return
    if cost_data["missing_ingredient_costs"]:
        st.warning(f"Could not calculate full material cost. Please record a purchase for these ingredients: {', '.join(cost_data['missing_ingredient_costs'])}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Prod. Cost/Item", f"€{cost_data['total_production_cost_per_item']:.2f}")
    c2.metric("Target Price (w/ Buffer)", f"€{cost_data['cost_plus_buffer']:.2f}")
    c3.metric("Blended Profit/Item", f"€{cost_data['blended_avg_profit']:.2f}")
    c4.metric("Blended Margin", f"{cost_data['blended_avg_margin_percent']:.1f}%")

    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Retail Channel")
        rt = cost_data['retail_metrics']
        st.metric("Retail Price", f"€{rt['price']:.2f}")
        st.metric("Total Cost (Prod + Fees)", f"€{rt['total_cost_item']:.2f}")
        st.metric("Profit per Item", f"€{rt['profit']:.2f}", delta_color="normal")
        st.metric("Margin", f"{rt['margin_percent']:.1f}%")

    with col2:
        st.subheader("Wholesale Channel")
        ws = cost_data['wholesale_metrics']
        st.metric("Wholesale Price", f"€{ws['price']:.2f}")
        st.metric("Total Cost (Prod + Fees)", f"€{ws['total_cost_item']:.2f}")
        st.metric("Profit per Item", f"€{ws['profit']:.2f}", delta_color="normal")
        st.metric("Margin", f"{ws['margin_percent']:.1f}%")

# --- Main Page Render Function ---
def render(db: Session, user: User, is_mobile: bool):
    st.header("📦 Product Management")
    st.write("Create new products or select an existing one to manage its recipe, workflow, and costs.")

    products = db.query(Product).filter(Product.user_id == user.id).order_by(Product.product_name).all()
    product_names = [p.product_name for p in products]
    CREATE_NEW_OPTION = "✨ Create a New Product..."
    product_names.insert(0, CREATE_NEW_OPTION)

    pre_selected_index = 0
    if 'selected_product_name' in st.session_state and st.session_state.selected_product_name in product_names:
        pre_selected_index = product_names.index(st.session_state.selected_product_name)
    
    selected_product_name = st.selectbox("Select a Product", options=product_names, index=pre_selected_index, key="product_selector")
    
    if 'selected_product_name' in st.session_state and st.session_state.selected_product_name != selected_product_name:
        st.session_state.selected_product_name = selected_product_name
    elif 'selected_product_name' not in st.session_state:
        st.session_state.selected_product_name = selected_product_name

    st.markdown("---")

    if selected_product_name == CREATE_NEW_OPTION:
        render_new_product_form(user)
    elif selected_product_name:
        product = db.query(Product).options(
            selectinload(Product.materials).joinedload(ProductMaterial.ingredient_ref),
            selectinload(Product.production_tasks).joinedload(ProductProductionTask.standard_task_ref),
            selectinload(Product.production_tasks).joinedload(ProductProductionTask.employee_ref)
        ).filter(Product.product_name == selected_product_name, Product.user_id == user.id).first()
        
        if product:
            render_product_editor(db, user, product, is_mobile)