# utils/db_helpers.py

from sqlalchemy.orm import Session
from typing import Type, List, TypeVar
from models import Base

# Define a TypeVar for generic model types
T = TypeVar('T', bound=Base)

def create_ingredient_display_string(name: str, provider: str = None) -> str:
    """
    Creates a standardized display string for an ingredient, including the provider if available.
    Example: "Flour (King Arthur)" or "Sugar"
    """
    if provider:
        return f"{name} ({provider})"
    return name

# --- NEW FUNCTION ---
def get_all_for_user(
    db: Session, 
    model: Type[T], 
    user_id: int, 
    order_by_col=None
) -> List[T]:
    """
    Generic function to retrieve all records of a given model for a specific user.

    Args:
        db (Session): The database session.
        model (Type[T]): The SQLAlchemy model class to query (e.g., Product, Ingredient).
        user_id (int): The ID of the user whose records are to be fetched.
        order_by_col: The model's column to order the results by (e.g., Product.product_name).

    Returns:
        List[T]: A list of model instances.
    """
    query = db.query(model).filter(model.user_id == user_id)
    if order_by_col is not None:
        query = query.order_by(order_by_col)
    return query.all()
# --- END NEW FUNCTION ---