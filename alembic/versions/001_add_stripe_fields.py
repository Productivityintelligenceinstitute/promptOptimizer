"""add stripe fields to subscriptions and users

Revision ID: 001_add_stripe_fields
Revises: 
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_add_stripe_fields'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add Stripe fields to subscriptions table
    op.add_column('subscriptions', sa.Column('stripe_customer_id', sa.String(), nullable=True))
    op.add_column('subscriptions', sa.Column('stripe_subscription_id', sa.String(), nullable=True))
    op.add_column('subscriptions', sa.Column('stripe_price_id', sa.String(), nullable=True))
    
    # Add indexes for better query performance
    op.create_index('idx_subscriptions_stripe_customer_id', 'subscriptions', ['stripe_customer_id'], unique=False)
    op.create_index('idx_subscriptions_stripe_subscription_id', 'subscriptions', ['stripe_subscription_id'], unique=False)
    
    # Add unique constraint on stripe_subscription_id
    op.create_unique_constraint('subscriptions_stripe_subscription_id_key', 'subscriptions', ['stripe_subscription_id'])
    
    # Add Stripe customer ID to users table
    op.add_column('users', sa.Column('stripe_customer_id', sa.String(), nullable=True))
    
    # Add unique constraint and index on users.stripe_customer_id
    op.create_index('idx_users_stripe_customer_id', 'users', ['stripe_customer_id'], unique=False)
    # Create partial unique index (only for non-null values)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_stripe_customer_id_unique 
        ON users(stripe_customer_id) 
        WHERE stripe_customer_id IS NOT NULL
    """)


def downgrade() -> None:
    # Remove indexes and constraints
    op.drop_index('idx_users_stripe_customer_id_unique', table_name='users')
    op.drop_index('idx_users_stripe_customer_id', table_name='users')
    op.drop_constraint('subscriptions_stripe_subscription_id_key', 'subscriptions', type_='unique')
    op.drop_index('idx_subscriptions_stripe_subscription_id', table_name='subscriptions')
    op.drop_index('idx_subscriptions_stripe_customer_id', table_name='subscriptions')
    
    # Remove columns
    op.drop_column('users', 'stripe_customer_id')
    op.drop_column('subscriptions', 'stripe_price_id')
    op.drop_column('subscriptions', 'stripe_subscription_id')
    op.drop_column('subscriptions', 'stripe_customer_id')

