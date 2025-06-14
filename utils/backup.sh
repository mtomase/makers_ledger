#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration from Render Environment Variables ---
# This MUST be set in your Render Cron Job environment variables.
APP_USERNAME=${APP_USERNAME}
# This is automatically provided by Render when you link a database.
DATABASE_URL=${DATABASE_URL}

# --- Script Setup ---
BACKUP_DIR="/tmp/backups"
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILENAME="backup-$TIMESTAMP.sqlc"
BACKUP_FILE="$BACKUP_DIR/$BACKUP_FILENAME"

echo "--- Starting PostgreSQL Backup ---"

if [ -z "$APP_USERNAME" ]; then
    echo "Error: APP_USERNAME environment variable is not set. Cannot determine backup retention policy."
    exit 1
fi

# --- Fetch Backup Retention Days from Database ---
echo "Fetching backup retention policy for user: $APP_USERNAME"
# Use psql to query the database. -t for tuples only, -A for unaligned output.
RETENTION_DAYS_QUERY="SELECT backup_retention_days FROM users WHERE username = '$APP_USERNAME';"

# Note: psql uses the PGPASSWORD env var if set, or prompts otherwise.
# Render's environment should handle this seamlessly with the DATABASE_URL.
FETCHED_DAYS=$(psql "$DATABASE_URL" -tA -c "$RETENTION_DAYS_QUERY")

# Validate the fetched value, default to 7 if invalid or empty
if [[ "$FETCHED_DAYS" =~ ^[0-9]+$ ]]; then
    export ONEDRIVE_DAYS_TO_KEEP=$FETCHED_DAYS
    echo "Retention policy found in database: $ONEDRIVE_DAYS_TO_KEEP days."
else
    export ONEDRIVE_DAYS_TO_KEEP=7
    echo "Warning: Could not fetch a valid retention policy for user '$APP_USERNAME'. Defaulting to $ONEDRIVE_DAYS_TO_KEEP days."
fi

# --- Database Backup Logic ---
echo "Dumping PostgreSQL database to $BACKUP_FILE"
# pg_dump uses the DATABASE_URL. The custom format is compressed and robust.
pg_dump --format=custom --no-owner --no-privileges "$DATABASE_URL" > "$BACKUP_FILE"

echo "Database backup created successfully: $BACKUP_FILE"

# --- Upload to OneDrive ---
echo "Uploading backup to OneDrive..."
# The python script will automatically read ONEDRIVE_DAYS_TO_KEEP from the environment
python3 upload_to_onedrive.py "$BACKUP_FILE"

# --- Cleanup ---
rm "$BACKUP_FILE"
echo "Local backup file cleaned up. Process complete."