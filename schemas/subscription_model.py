from database import database
from sqlalchemy import Column, String, ForeignKey, Integer, UniqueConstraint, Boolean, TIMESTAMP, text

class SubscriptionsModel(database.Base):
    __tablename__ = "subscriptions"

    subscription_id = Column(String, primary_key=True, nullable=False)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    package_id = Column(Integer, ForeignKey("packages.package_id"), nullable=False)
    status = Column(String, nullable=False)
    start_date = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text('now()'))
    end_date = Column(TIMESTAMP(timezone=True), nullable=True)
    auto_renew = Column(Boolean, default=True)
    
    # Stripe-related fields
    stripe_customer_id = Column(String, nullable=True, index=True)
    stripe_subscription_id = Column(String, nullable=True, unique=True, index=True)
    stripe_price_id = Column(String, nullable=True)
    
    created_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'))
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text('now()'))

    __table_args__ = (
        UniqueConstraint("user_id", "package_id"),
    )