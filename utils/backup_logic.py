# backup_logic.py

import os
import sys
import subprocess
import datetime
import streamlit as st
from sqlalchemy.orm import Session
from models import User  # Assuming models.py is in the same directory
from upload_to_onedrive import upload_file_to_onedrive # Assuming this function exists

def run_backup(db_session: Session, user: User, database_url: str):
    """
    Performs a database backup, uploads it to OneDrive, and cleans up.
    This is the Python equivalent of backup.sh.
    """
    st.info("Starting database backup process...")
    
    # --- Setup ---
    backup_dir = "database_backups" # Use a local folder
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_filename = f"backup-{user.username}-{timestamp}.sqlc"
    backup_file_path = os.path.join(backup_dir, backup_filename)

    # --- Fetch Retention Policy ---
    retention_days = user.backup_retention_days
    if not isinstance(retention_days, int) or retention_days <= 0:
        retention_days = 7 # Default fallback
    
    st.write(f"Backup retention policy: {retention_days} days.")

    # --- Database Dump Logic ---
    st.write(f"Creating database dump...")
    try:
        # IMPORTANT: This requires pg_dump to be in the system's PATH on the PC running the app.
        command = [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            database_url
        ]
        
        with open(backup_file_path, "wb") as f:
            process = subprocess.Popen(command, stdout=f, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()

        if process.returncode != 0:
            error_message = stderr.decode('utf-8')
            st.error(f"Error during pg_dump: {error_message}")
            return False
        
        st.write(f"Database backup created: {backup_filename}")

    except FileNotFoundError:
        st.error("Error: 'pg_dump' command not found. Please ensure PostgreSQL client tools are installed and in your system's PATH.")
        return False
    except Exception as e:
        st.error(f"An unexpected error occurred during backup: {e}")
        return False

    # --- Upload to OneDrive ---
    st.write("Uploading to OneDrive...")
    try:
        # We pass the retention days to the upload function
        upload_success = upload_file_to_onedrive(backup_file_path, retention_days)
        if not upload_success:
            st.error("Failed to upload backup to OneDrive.")
            return False
    except Exception as e:
        st.error(f"An error occurred during OneDrive upload: {e}")
        return False

    # --- Cleanup ---
    try:
        os.remove(backup_file_path)
        st.success("Backup complete and local file cleaned up!")
        return True
    except Exception as e:
        st.warning(f"Could not remove local backup file: {e}")
        return True # The backup itself was successful