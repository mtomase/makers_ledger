# app_pages/p4_manage_tasks.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import sys
import os

# --- Boilerplate: Add project root to path ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# --- THE FIX: Import SessionLocal directly to create a new session ---
from models import SessionLocal, User, StandardProductionTask, StandardShippingTask

def render(db: Session, user: User, is_mobile: bool):
    """
    Renders the page for managing standard tasks.
    The 'db: Session' is used for READ-ONLY operations on page load.
    WRITE operations will use a new, dedicated session.
    """
    st.header("🏭 Manage Standard Tasks")
    st.write("Define the generic names for tasks used in your workflow (e.g., 'Mixing', 'Cutting', 'Packing').")

    # --- Production Tasks Section ---
    st.subheader("Production Tasks")
    
    # Use the provided 'db' session for initial, read-only loading
    prod_tasks_db = db.query(StandardProductionTask).filter(StandardProductionTask.user_id == user.id).order_by(StandardProductionTask.task_name).all()
    prod_task_data = [{"Task Name": task.task_name} for task in prod_tasks_db]
    df_prod_tasks = pd.DataFrame(prod_task_data, columns=["Task Name"])
    
    edited_df_prod = st.data_editor(
        df_prod_tasks, 
        num_rows="dynamic", 
        key="prod_tasks_editor",
        column_config={"Task Name": st.column_config.TextColumn("Task Name*", required=True, help="Names must be unique.")},
        use_container_width=True, 
        hide_index=True
    )

    if st.button("Save Production Task Changes", type="primary", key="save_prod_tasks"):
        # --- THE FIX: Create a new, dedicated session for this transaction ---
        with SessionLocal() as transaction_db:
            try:
                final_names = {name.strip() for name in edited_df_prod["Task Name"].dropna() if name.strip()}

                # Delete all existing tasks for this user within the new transaction
                transaction_db.query(StandardProductionTask).filter(StandardProductionTask.user_id == user.id).delete(synchronize_session=False)
                
                # Add all the tasks from the UI back into the database
                for name in final_names:
                    transaction_db.add(StandardProductionTask(user_id=user.id, task_name=name))
                
                # Commit the transaction
                transaction_db.commit()
                st.success("Production Tasks updated successfully!")
            except IntegrityError:
                transaction_db.rollback()
                st.error("Save failed. Task names must be unique. Please remove any duplicate entries.")
            except Exception as e:
                transaction_db.rollback()
                st.error(f"An unexpected error occurred: {e}")
        # Rerun the page outside the 'with' block to reflect the changes
        st.rerun()


    st.markdown("---")

    # --- Shipping Tasks Section ---
    st.subheader("Shipping Tasks")

    # Use the provided 'db' session for initial, read-only loading
    ship_tasks_db = db.query(StandardShippingTask).filter(StandardShippingTask.user_id == user.id).order_by(StandardShippingTask.task_name).all()
    ship_task_data = [{"Task Name": task.task_name} for task in ship_tasks_db]
    df_ship_tasks = pd.DataFrame(ship_task_data, columns=["Task Name"])

    edited_df_ship = st.data_editor(
        df_ship_tasks, 
        num_rows="dynamic", 
        key="ship_tasks_editor",
        column_config={"Task Name": st.column_config.TextColumn("Task Name*", required=True, help="Names must be unique.")},
        use_container_width=True, 
        hide_index=True
    )

    if st.button("Save Shipping Task Changes", type="primary", key="save_ship_tasks"):
        # --- APPLYING THE SAME FIX HERE ---
        with SessionLocal() as transaction_db:
            try:
                final_names = {name.strip() for name in edited_df_ship["Task Name"].dropna() if name.strip()}

                transaction_db.query(StandardShippingTask).filter(StandardShippingTask.user_id == user.id).delete(synchronize_session=False)
                
                for name in final_names:
                    transaction_db.add(StandardShippingTask(user_id=user.id, task_name=name))
                    
                transaction_db.commit()
                st.success("Shipping Tasks updated successfully!")
            except IntegrityError:
                transaction_db.rollback()
                st.error("Save failed. Task names must be unique. Please remove any duplicate entries.")
            except Exception as e:
                transaction_db.rollback()
                st.error(f"An unexpected error occurred: {e}")
        st.rerun()