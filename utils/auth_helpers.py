# utils/auth_helpers.py
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from models import User

def sync_stauth_user_to_db(db: Session, username: str, email: str, name: str) -> User:
    """
    Ensures a user from streamlit-authenticator has a corresponding record
    in the application's database. Creates or updates as needed.
    """
    try:
        db_user = db.query(User).filter(User.username == username).first()

        if db_user:
            # User exists, update name if it has changed from the authenticator config
            if db_user.name != name:
                db_user.name = name
        else:
            # User does not exist, create a new one
            print(f"Creating new database user record for: {username}")
            db_user = User(username=username, email=email, name=name)
            db.add(db_user)
        
        db.commit()
        db.refresh(db_user)
        return db_user
    except SQLAlchemyError as e:
        db.rollback()
        print(f"Database error in sync_stauth_user_to_db for {username}: {e}")
        raise
    except Exception as e:
        db.rollback()
        print(f"Unexpected error in sync_stauth_user_to_db for {username}: {e}")
        raise