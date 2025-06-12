# reset_alembic.py
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

print("--- Starting Alembic History Reset ---")

# Load environment variables from .env file
load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    print("❌ DATABASE_URL not found in .env file. Aborting.")
    exit()

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as connection:
        print("Connecting to the database to reset Alembic history...")
        # Start a transaction
        with connection.begin() as transaction:
            try:
                # Delete all records from the alembic_version table
                connection.execute(text("DELETE FROM alembic_version;"))
                print("✅ Successfully cleared the 'alembic_version' table.")
                transaction.commit()
            except Exception as e:
                # This will happen if the table doesn't exist yet, which is fine.
                if "does not exist" in str(e):
                     print("ℹ️  'alembic_version' table does not exist, which is okay. Nothing to clear.")
                     transaction.commit() # Still commit to close the transaction block
                else:
                    print(f"❌ An error occurred: {e}")
                    transaction.rollback()

except Exception as e:
    print(f"❌ Failed to connect to the database. Please check your DATABASE_URL in the .env file.")
    print(f"   Error: {e}")

print("--- Alembic History Reset Finished ---")