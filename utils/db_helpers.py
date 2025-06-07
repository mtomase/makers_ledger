# utils/db_helpers.py
import re
from sqlalchemy.orm import Session
from models import Ingredient, Employee, StandardProductionTask, StandardShippingTask

def create_ingredient_display_string(name, provider):
    if provider: return f"{name} (Provider: {provider})"
    return name

def parse_ingredient_display_string(display_string):
    if display_string is None: return None, None
    match = re.match(r"^(.*?) \(Provider: (.*?)\)$", display_string)
    if match: return match.group(1), match.group(2)
    return display_string, None

def get_ingredient_id_from_display(db_session: Session, display_string: str, user_id: int):
    name, provider = parse_ingredient_display_string(display_string)
    if not name: return None
    filters = [Ingredient.user_id == user_id, Ingredient.name == name]
    if provider is not None:
        filters.append(Ingredient.provider == provider)
    else:
        filters.append(Ingredient.provider.is_(None))
    ing = db_session.query(Ingredient).filter(*filters).first()
    return ing.id if ing else None

def get_employee_id_from_name(db_session: Session, name_val: str, user_id: int):
    if not name_val: return None
    emp = db_session.query(Employee).filter(Employee.user_id == user_id, Employee.name == name_val).first()
    return emp.id if emp else None

def get_std_prod_task_id_from_name(db_session: Session, name_val: str, user_id: int):
    if not name_val: return None
    task = db_session.query(StandardProductionTask).filter(StandardProductionTask.user_id == user_id, StandardProductionTask.task_name == name_val).first()
    return task.id if task else None

def get_std_ship_task_id_from_name(db_session: Session, name_val: str, user_id: int):
    if not name_val: return None
    task = db_session.query(StandardShippingTask).filter(StandardShippingTask.user_id == user_id, StandardShippingTask.task_name == name_val).first()
    return task.id if task else None