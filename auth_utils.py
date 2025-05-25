# auth_utils.py
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from models import User # Assuming User model is in models.py

def get_or_create_db_user(db: Session, username: str, email: str, name: str) -> User:
    """
    Retrieves a user from the database by username or email,
    or creates a new one if not found.
    Updates name if the user exists.
    """
    try:
        # Try to find user by username first, then by email as a fallback
        db_user = db.query(User).filter(User.username == username).first()
        if not db_user:
            db_user = db.query(User).filter(User.email == email).first()
            if db_user and db_user.username != username:
                # Email exists but with a different username, update username if appropriate
                # Or handle as a conflict. For now, let's assume username from authenticator is king.
                db_user.username = username # Or log a warning/error

        if db_user:
            # User exists, update name if it has changed
            if db_user.name != name:
                db_user.name = name
        else:
            # User does not exist, create a new one
            print(f"Creating new database user: {username} ({email})")
            db_user = User(username=username, email=email, name=name)
            db.add(db_user)
        
        db.commit()
        db.refresh(db_user) # To get any default values like ID, layout_preference
        return db_user
    except SQLAlchemyError as e:
        db.rollback()
        print(f"Database error in get_or_create_db_user for {username}: {e}")
        raise # Re-raise the exception to be handled by the caller
    except Exception as e:
        db.rollback()
        print(f"Unexpected error in get_or_create_db_user for {username}: {e}")
        raise