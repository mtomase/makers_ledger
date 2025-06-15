# utils/db_helpers.py

from sqlalchemy.orm import Session, Mapped
from typing import Type, List, TypeVar, Protocol

# --- NEW: Define a Protocol for type safety ---
# This tells the type checker that any model used with get_all_for_user
# MUST have a 'user_id' attribute that is an integer.
class UserBoundModel(Protocol):
    user_id: Mapped[int]

# --- UPDATED: Bind the TypeVar to the new Protocol ---
# Now, T is not just any model based on Base, but one that specifically
# fulfills the UserBoundModel contract.
T = TypeVar('T', bound=UserBoundModel)

def create_inventoryitem_display_string(name: str, provider: str = None) -> str:
    """
    Creates a standardized display string for an inventoryitem, including the provider if available.
    Example: "Flour (King Arthur)" or "Sugar"
    """
    if provider:
        return f"{name} ({provider})"
    return name

def get_all_for_user(
    db: Session, 
    model: Type[T], 
    user_id: int, 
    order_by_col=None
) -> List[T]:
    """
    Generic function to retrieve all records of a given model for a specific user.
    The model must have a `user_id` attribute.

    Args:
        db (Session): The database session.
        model (Type[T]): The SQLAlchemy model class to query (e.g., Product, Ingredient).
        user_id (int): The ID of the user whose records are to be fetched.
        order_by_col: The model's column to order the results by (e.g., Product.product_name).

    Returns:
        List[T]: A list of model instances.
    """
    # The type checker is now happy because it knows `model` is guaranteed
    # to have the .user_id attribute due to the TypeVar's bound Protocol.
    query = db.query(model).filter(model.user_id == user_id)
    if order_by_col is not None:
        query = query.order_by(order_by_col)
    return query.all()