# pages/page_03_tasks.py
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from models import StandardProductionTask, StandardShippingTask, User

def render(db: Session, user: User):
    st.header("🏭 Manage Standard Tasks")
    st.write("Define reusable tasks for production and shipping. These will be available in dropdowns when managing specific products.")

    # --- Production Tasks ---
    st.subheader("Production Tasks")
    tasks_db = db.query(StandardProductionTask).filter(StandardProductionTask.user_id == user.id).order_by(StandardProductionTask.id).all()
    data_for_editor_ptask = [{"ID": task.id, "Task Name": task.task_name} for task in tasks_db]
    df_ptask_cols = ["ID", "Task Name"]
    df_ptasks_for_editor = pd.DataFrame(data_for_editor_ptask, columns=df_ptask_cols)
    if df_ptasks_for_editor.empty:
        df_ptasks_for_editor = pd.DataFrame(columns=df_ptask_cols).astype({"ID": "float64", "Task Name": "object"})
    
    snapshot_key_ptask = 'df_ptasks_snapshot'
    if snapshot_key_ptask not in st.session_state or not isinstance(st.session_state.get(snapshot_key_ptask), pd.DataFrame) or not st.session_state[snapshot_key_ptask].columns.equals(df_ptasks_for_editor.columns):
        st.session_state[snapshot_key_ptask] = df_ptasks_for_editor.copy()
    
    ptask_display_columns = ("Task Name",)
    edited_df_ptask = st.data_editor(
        st.session_state[snapshot_key_ptask], num_rows="dynamic", key="prod_tasks_editor",
        column_order=ptask_display_columns, column_config={"Task Name": st.column_config.TextColumn("Task Name*", required=True)},
        use_container_width=True, hide_index=True
    )

    if st.button("Save Production Task Changes", type="primary"):
        try:
            original_df_snapshot_ptask = st.session_state[snapshot_key_ptask]
            original_snapshot_ids_ptask = set(original_df_snapshot_ptask['ID'].dropna().astype(int))
            edited_df_ids_ptask = set(edited_df_ptask['ID'].dropna().astype(int))
            ids_to_delete_from_db_ptask = original_snapshot_ids_ptask - edited_df_ids_ptask

            for task_id_del in ids_to_delete_from_db_ptask:
                task_to_del = db.query(StandardProductionTask).filter(StandardProductionTask.id == task_id_del, StandardProductionTask.user_id == user.id).first()
                if task_to_del: db.delete(task_to_del); st.toast(f"Deleted production task ID: {task_id_del}", icon="➖")

            for index, row in edited_df_ptask.iterrows():
                task_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                name_val = row.get("Task Name")
                if not name_val:
                    if task_id is None and not name_val: continue
                    st.error(f"Row {index+1} (Production): Task Name is required. Skipping."); continue
                if task_id: 
                    item_to_update = db.query(StandardProductionTask).filter(StandardProductionTask.id == task_id, StandardProductionTask.user_id == user.id).first()
                    if item_to_update and item_to_update.task_name != name_val:
                        item_to_update.task_name = name_val; st.toast(f"Updated production task ID: {task_id}", icon="🔄")
            
            new_rows_df_ptask = edited_df_ptask[edited_df_ptask['ID'].isna()]
            for index, row in new_rows_df_ptask.iterrows():
                name_val = row.get("Task Name")
                if not name_val:
                    if not name_val: continue
                    st.error(f"New Row (Production - approx index {index+1}): Task Name is required. Skipping."); continue
                db.add(StandardProductionTask(user_id=user.id, task_name=name_val))
                st.toast(f"Added production task: {name_val}", icon="➕")
            
            db.commit()
            st.success("Production Task changes saved!")
            st.session_state[snapshot_key_ptask] = edited_df_ptask.copy()
            st.rerun()
        except Exception as e:
            db.rollback()
            st.error(f"Error saving production tasks: {e}")
            st.exception(e)

    st.markdown("---")

    # --- Shipping Tasks ---
    st.subheader("Shipping Tasks")
    tasks_db_ship = db.query(StandardShippingTask).filter(StandardShippingTask.user_id == user.id).order_by(StandardShippingTask.id).all()
    data_for_editor_stask = [{"ID": task.id, "Task Name": task.task_name} for task in tasks_db_ship]
    df_stask_cols = ["ID", "Task Name"]
    df_stasks_for_editor = pd.DataFrame(data_for_editor_stask, columns=df_stask_cols)
    if df_stasks_for_editor.empty:
        df_stasks_for_editor = pd.DataFrame(columns=df_stask_cols).astype({"ID": "float64", "Task Name": "object"})

    snapshot_key_stask = 'df_stasks_snapshot'
    if snapshot_key_stask not in st.session_state or not isinstance(st.session_state.get(snapshot_key_stask), pd.DataFrame) or not st.session_state[snapshot_key_stask].columns.equals(df_stasks_for_editor.columns):
        st.session_state[snapshot_key_stask] = df_stasks_for_editor.copy()

    stask_display_columns = ("Task Name",)
    edited_df_stask = st.data_editor(
        st.session_state[snapshot_key_stask], num_rows="dynamic", key="ship_tasks_editor",
        column_order=stask_display_columns, column_config={"Task Name": st.column_config.TextColumn("Task Name*", required=True)},
        use_container_width=True, hide_index=True
    )

    if st.button("Save Shipping Task Changes", type="primary"):
        try:
            original_df_snapshot_stask = st.session_state[snapshot_key_stask]
            original_snapshot_ids_stask = set(original_df_snapshot_stask['ID'].dropna().astype(int))
            edited_df_ids_stask = set(edited_df_stask['ID'].dropna().astype(int))
            ids_to_delete_from_db_stask = original_snapshot_ids_stask - edited_df_ids_stask

            for task_id_del in ids_to_delete_from_db_stask:
                task_to_del = db.query(StandardShippingTask).filter(StandardShippingTask.id == task_id_del, StandardShippingTask.user_id == user.id).first()
                if task_to_del: db.delete(task_to_del); st.toast(f"Deleted shipping task ID: {task_id_del}", icon="➖")
            
            for index, row in edited_df_stask.iterrows():
                task_id = int(row.get('ID')) if pd.notna(row.get('ID')) else None
                name_val = row.get("Task Name")
                if not name_val:
                    if task_id is None and not name_val: continue
                    st.error(f"Row {index+1} (Shipping): Task Name is required. Skipping."); continue
                if task_id:
                    item_to_update = db.query(StandardShippingTask).filter(StandardShippingTask.id == task_id, StandardShippingTask.user_id == user.id).first()
                    if item_to_update and item_to_update.task_name != name_val:
                         item_to_update.task_name = name_val; st.toast(f"Updated shipping task ID: {task_id}", icon="🔄")
            
            new_rows_df_stask = edited_df_stask[edited_df_stask['ID'].isna()]
            for index, row in new_rows_df_stask.iterrows():
                name_val = row.get("Task Name")
                if not name_val:
                    if not name_val: continue
                    st.error(f"New Row (Shipping - approx index {index+1}): Task Name is required. Skipping."); continue
                db.add(StandardShippingTask(user_id=user.id, task_name=name_val))
                st.toast(f"Added shipping task: {name_val}", icon="➕")

            db.commit()
            st.success("Shipping Task changes saved!")
            st.session_state[snapshot_key_stask] = edited_df_stask.copy()
            st.rerun()
        except Exception as e:
            db.rollback()
            st.error(f"Error saving shipping tasks: {e}")
            st.exception(e)