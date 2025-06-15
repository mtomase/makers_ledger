"""Initial database schema from models

Revision ID: 61ae13442253
Revises: 
Create Date: <the_date>

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
# IMPORTANT: Replace '<your_new_revision_id>' with the actual ID from your filename.
revision = '61ae13442253' 
down_revision = None
branch_labels = None
depends_on = None

# Define the ENUM types for clarity
inventoryitem_type_enum = sa.Enum('OIL_FAT_BUTTER', 'ADDITIVE', 'LYE', 'LIQUID', name='inventoryitem_type_enum')
safety_check_status_enum = sa.Enum('DONE', 'NOT_DONE', 'NOT_APPLICABLE', name='safety_check_status_enum')
user_layout_enum = sa.Enum('WIDE', 'CENTERED', name='user_layout_enum_def')


def upgrade() -> None:
    # ### Create all tables and types ###
    
    # NOTE: We are REMOVING the explicit op.create() calls from here.
    # SQLAlchemy's op.create_table will handle creating the ENUMs automatically
    # and will not fail if they already exist.

    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('layout_preference', user_layout_enum, nullable=False),
        sa.Column('role', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    op.create_table('employees',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('hourly_rate', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('role', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name', name='uq_user_employee_name')
    )
    op.create_index(op.f('ix_employees_id'), 'employees', ['id'], unique=False)

    op.create_table('global_costs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('monthly_rent', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('monthly_utilities', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_global_costs_id'), 'global_costs', ['id'], unique=False)

    op.create_table('inventoryitems',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('type', inventoryitem_type_enum, nullable=False),
        sa.Column('provider', sa.String(), nullable=True),
        sa.Column('price_per_unit', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('unit_quantity_kg', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('price_url', sa.Text(), nullable=True),
        sa.Column('current_stock_grams', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('reorder_threshold_grams', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name', 'provider', name='uq_user_inventoryitem_provider')
    )
    op.create_index(op.f('ix_inventoryitems_id'), 'inventoryitems', ['id'], unique=False)

    op.create_table('standard_production_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('task_name', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'task_name', name='uq_user_std_prod_task_name')
    )
    op.create_index(op.f('ix_standard_production_tasks_id'), 'standard_production_tasks', ['id'], unique=False)

    op.create_table('standard_shipping_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('task_name', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'task_name', name='uq_user_std_ship_task_name')
    )
    op.create_index(op.f('ix_standard_shipping_tasks_id'), 'standard_shipping_tasks', ['id'], unique=False)

    op.create_table('global_salaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('monthly_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'employee_id', name='uq_user_employee_global_salary')
    )
    op.create_index(op.f('ix_global_salaries_id'), 'global_salaries', ['id'], unique=False)

    op.create_table('products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('product_name', sa.String(), nullable=False),
        sa.Column('product_code', sa.String(length=10), nullable=True),
        sa.Column('batch_size_items', sa.Integer(), nullable=False),
        sa.Column('monthly_production_items', sa.Integer(), nullable=False),
        sa.Column('packaging_label_cost', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('packaging_material_cost', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('salary_allocation_employee_id', sa.Integer(), nullable=True),
        sa.Column('salary_allocation_items_per_month', sa.Integer(), nullable=True),
        sa.Column('rent_utilities_allocation_items_per_month', sa.Integer(), nullable=True),
        sa.Column('retail_avg_order_value', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('retail_cc_fee_percent', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('retail_platform_fee_percent', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('retail_shipping_cost_paid_by_you', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('wholesale_avg_order_value', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('wholesale_commission_percent', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('wholesale_processing_fee_percent', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('wholesale_flat_fee_per_order', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('wholesale_price_per_item', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('retail_price_per_item', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('buffer_percentage', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('distribution_wholesale_percentage', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['salary_allocation_employee_id'], ['employees.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'product_name', name='uq_user_product_name')
    )
    op.create_index(op.f('ix_products_id'), 'products', ['id'], unique=False)

    op.create_table('stock_additions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('inventoryitem_id', sa.Integer(), nullable=False),
        sa.Column('quantity_added_grams', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('purchase_date', sa.Date(), nullable=False),
        sa.Column('cost_of_addition', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('supplier_info', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['inventoryitem_id'], ['inventoryitems.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_stock_additions_id'), 'stock_additions', ['id'], unique=False)

    op.create_table('product_materials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('inventoryitem_id', sa.Integer(), nullable=False),
        sa.Column('quantity_grams', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.ForeignKeyConstraint(['inventoryitem_id'], ['inventoryitems.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'inventoryitem_id', name='uq_product_material_inventoryitem')
    )
    op.create_index(op.f('ix_product_materials_id'), 'product_materials', ['id'], unique=False)

    op.create_table('product_production_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=True),
        sa.Column('time_minutes', sa.Numeric(precision=10, scale=1), nullable=False),
        sa.Column('items_processed_in_task', sa.Integer(), nullable=False),
        sa.Column('standard_task_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['standard_task_id'], ['standard_production_tasks.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_product_production_tasks_id'), 'product_production_tasks', ['id'], unique=False)

    op.create_table('product_shipping_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=True),
        sa.Column('time_minutes', sa.Numeric(precision=10, scale=1), nullable=False),
        sa.Column('items_processed_in_task', sa.Integer(), nullable=False),
        sa.Column('standard_task_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['standard_task_id'], ['standard_shipping_tasks.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_product_shipping_tasks_id'), 'product_shipping_tasks', ['id'], unique=False)

    op.create_table('production_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('run_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('planned_batch_count', sa.Integer(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_production_runs_id'), 'production_runs', ['id'], unique=False)

    op.create_table('batch_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('production_run_id', sa.Integer(), nullable=False),
        sa.Column('batch_code', sa.String(), nullable=False),
        sa.Column('manufacturing_date', sa.Date(), nullable=True),
        sa.Column('cured_date', sa.Date(), nullable=True),
        sa.Column('expiration_date', sa.Date(), nullable=True),
        sa.Column('bars_in_batch', sa.Integer(), nullable=True),
        sa.Column('curing_time_days', sa.Integer(), nullable=True),
        sa.Column('manufacture_method', sa.String(), nullable=True),
        sa.Column('total_oil_weight_gr', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('water_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('superfat_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('final_cured_weight_gr', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('qc_fragrance_strength', sa.String(), nullable=True),
        sa.Column('qc_discoloration', sa.String(), nullable=True),
        sa.Column('qc_trace_speed', sa.String(), nullable=True),
        sa.Column('qc_gel_phase', sa.String(), nullable=True),
        sa.Column('qc_irregularities', sa.Text(), nullable=True),
        sa.Column('qc_ph_finished', sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column('qc_ph_cured', sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column('qc_final_quality_notes', sa.Text(), nullable=True),
        sa.Column('qc_packaging_notes', sa.Text(), nullable=True),
        sa.Column('qc_stability_notes', sa.Text(), nullable=True),
        sa.Column('qc_waste_notes', sa.Text(), nullable=True),
        sa.Column('person_responsible_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['person_responsible_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['production_run_id'], ['production_runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('batch_code')
    )
    op.create_index(op.f('ix_batch_records_id'), 'batch_records', ['id'], unique=False)

    op.create_table('batch_inventoryitem_usages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_record_id', sa.Integer(), nullable=False),
        sa.Column('inventoryitem_id', sa.Integer(), nullable=False),
        sa.Column('actual_weight_gr', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('inventoryitem_brand', sa.String(), nullable=True),
        sa.Column('supplier_lot_number', sa.String(), nullable=True),
        sa.Column('measured_by_initials', sa.String(length=5), nullable=True),
        sa.ForeignKeyConstraint(['batch_record_id'], ['batch_records.id'], ),
        sa.ForeignKeyConstraint(['inventoryitem_id'], ['inventoryitems.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_batch_inventoryitem_usages_id'), 'batch_inventoryitem_usages', ['id'], unique=False)

    op.create_table('batch_safety_checks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_record_id', sa.Integer(), nullable=False),
        sa.Column('check_name', sa.String(), nullable=False),
        sa.Column('status', safety_check_status_enum, nullable=False),
        sa.ForeignKeyConstraint(['batch_record_id'], ['batch_records.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('batch_record_id', 'check_name', name='uq_batch_safety_check')
    )
    op.create_index(op.f('ix_batch_safety_checks_id'), 'batch_safety_checks', ['id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_batch_safety_checks_id'), table_name='batch_safety_checks')
    op.drop_table('batch_safety_checks')
    op.drop_index(op.f('ix_batch_inventoryitem_usages_id'), table_name='batch_inventoryitem_usages')
    op.drop_table('batch_inventoryitem_usages')
    op.drop_index(op.f('ix_batch_records_id'), table_name='batch_records')
    op.drop_table('batch_records')
    op.drop_index(op.f('ix_production_runs_id'), table_name='production_runs')
    op.drop_table('production_runs')
    op.drop_index(op.f('ix_product_shipping_tasks_id'), table_name='product_shipping_tasks')
    op.drop_table('product_shipping_tasks')
    op.drop_index(op.f('ix_product_production_tasks_id'), table_name='product_production_tasks')
    op.drop_table('product_production_tasks')
    op.drop_index(op.f('ix_product_materials_id'), table_name='product_materials')
    op.drop_table('product_materials')
    op.drop_index(op.f('ix_stock_additions_id'), table_name='stock_additions')
    op.drop_table('stock_additions')
    op.drop_index(op.f('ix_products_id'), table_name='products')
    op.drop_table('products')
    op.drop_index(op.f('ix_global_salaries_id'), table_name='global_salaries')
    op.drop_table('global_salaries')
    op.drop_index(op.f('ix_standard_shipping_tasks_id'), table_name='standard_shipping_tasks')
    op.drop_table('standard_shipping_tasks')
    op.drop_index(op.f('ix_standard_production_tasks_id'), table_name='standard_production_tasks')
    op.drop_table('standard_production_tasks')
    op.drop_index(op.f('ix_inventoryitems_id'), table_name='inventoryitems')
    op.drop_table('inventoryitems')
    op.drop_index(op.f('ix_global_costs_id'), table_name='global_costs')
    op.drop_table('global_costs')
    op.drop_index(op.f('ix_employees_id'), table_name='employees')
    op.drop_table('employees')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')

    # Manually drop the ENUM types
    inventoryitem_type_enum.drop(op.get_bind(), checkfirst=True)
    safety_check_status_enum.drop(op.get_bind(), checkfirst=True)
    user_layout_enum.drop(op.get_bind(), checkfirst=True)
    # ### end Alembic commands ###