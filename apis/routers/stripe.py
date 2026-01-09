"""
Stripe Payment Integration Router

This module handles Stripe payment processing including:
- Checkout session creation
- Webhook event handling
- Subscription lifecycle management
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import uuid4
import stripe
import logging
import os

from database import database
from dependencies.auth import verify_firebase_token
from schemas.user_model import UserModel
from schemas.subscription_model import SubscriptionsModel
from schemas.packages_model import PackagesModel
from core.config import (
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
    STRIPE_PRICE_ID_ESSENTIAL,
    STRIPE_PRICE_ID_PRO,
    FRONTEND_URL
)

# Initialize Stripe
if not STRIPE_SECRET_KEY:
    raise ValueError("STRIPE_SECRET_KEY environment variable is required")

stripe.api_key = STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)
stripe_router = APIRouter()
security = HTTPBearer()

# Plan name to Stripe Price ID mapping
PLAN_TO_STRIPE_PRICE_ID: Dict[str, Optional[str]] = {
    "Essential": STRIPE_PRICE_ID_ESSENTIAL,
    "Pro": STRIPE_PRICE_ID_PRO,
}


@stripe_router.post(
    "/create-checkout-session",
    status_code=status.HTTP_200_OK,
    summary="Create Stripe Checkout Session",
    description="Creates a Stripe Checkout Session for subscription payment",
    responses={
        200: {"description": "Checkout session created successfully"},
        400: {"description": "Invalid request data"},
        401: {"description": "Unauthorized"},
        404: {"description": "User not found"},
        500: {"description": "Internal server error"},
    },
)
async def create_checkout_session(
    request: Dict[str, Any],
    decoded_token: dict = Depends(verify_firebase_token),
    db: Session = Depends(database.get_db),
) -> Dict[str, str]:
    """
    Creates a Stripe Checkout Session for subscription.
    
    Request body:
    - planName: str (e.g., "Essential", "Pro")
    - priceId: str (Stripe Price ID)
    - successUrl: str (optional, default from config)
    - cancelUrl: str (optional, default from config)
    """
    try:
        firebase_uid: Optional[str] = decoded_token.get("uid")
        if not firebase_uid:
            logger.warning("Firebase UID not found in decoded token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token: UID not found"
            )

        # Get user from database
        user: Optional[UserModel] = (
            db.query(UserModel)
            .filter(UserModel.firebase_uid == firebase_uid)
            .first()
        )

        if not user:
            logger.warning(f"User not found for firebase_uid: {firebase_uid}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found. Please create an account first."
            )

        # Extract request parameters
        plan_name: Optional[str] = request.get("planName")
        price_id: Optional[str] = request.get("priceId")

        if not plan_name or not price_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="planName and priceId are required"
            )

        # Resolve package_id from database using plan name
        package = (
            db.query(PackagesModel)
            .filter(PackagesModel.package_name.ilike(plan_name.lower()))
            .first()
        )
        if not package:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid plan name: {plan_name}"
            )
        package_id = package.id

        # Verify price_id matches plan
        expected_price_id = PLAN_TO_STRIPE_PRICE_ID.get(plan_name)
        if expected_price_id and price_id != expected_price_id:
            logger.warning(
                f"Price ID mismatch for plan {plan_name}. "
                f"Expected: {expected_price_id}, Got: {price_id}"
            )

        # Get or create Stripe Customer
        stripe_customer_id: Optional[str] = user.stripe_customer_id

        if not stripe_customer_id:
            try:
                # Create Stripe Customer
                customer = stripe.Customer.create(
                    email=user.email,
                    name=user.full_name,
                    metadata={
                        "user_id": str(user.id),
                        "firebase_uid": firebase_uid,
                    }
                )
                stripe_customer_id = customer.id

                # Store Stripe Customer ID in user record
                user.stripe_customer_id = stripe_customer_id
                db.commit()
                db.refresh(user)
                logger.info(f"Created Stripe customer {stripe_customer_id} for user {user.id}")
            except stripe.error.StripeError as e:
                logger.error(f"Stripe error creating customer: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to create Stripe customer: {str(e)}"
                )
            except SQLAlchemyError as e:
                logger.error(f"Database error saving Stripe customer ID: {e}")
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to save Stripe customer ID"
                )

        # Build success and cancel URLs
        # Default: redirect to chat page after success, home page on cancel
        success_url = request.get("successUrl", f"{FRONTEND_URL}/chat?success=true")
        cancel_url = request.get("cancelUrl", f"{FRONTEND_URL}")

        # Verify price exists and is in the correct mode before creating checkout
        try:
            price_obj = stripe.Price.retrieve(price_id)
            # Check if price is active
            if not price_obj.get('active', False):
                logger.warning(f"Price {price_id} is not active")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Price {price_id} is not active. Please check your Stripe dashboard."
                )
        except stripe.error.InvalidRequestError as e:
            error_msg = str(e)
            if "No such price" in error_msg or "test mode" in error_msg.lower() or "live mode" in error_msg.lower():
                logger.error(f"Price ID mode mismatch: {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Price ID '{price_id}' is not valid for the current Stripe mode. "
                        f"Error: {error_msg}. "
                        f"Please ensure you're using test mode price IDs with test mode keys, "
                        f"or live mode price IDs with live mode keys."
                    )
                )
            raise
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error verifying price: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to verify price: {str(e)}"
            )

        # Create Checkout Session
        try:
            checkout_session = stripe.checkout.Session.create(
                customer=stripe_customer_id,
                payment_method_types=['card'],
                line_items=[{
                    'price': price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "user_id": str(user.id),
                    "package_id": str(package_id),
                    "plan_name": plan_name,
                },
                subscription_data={
                    "metadata": {
                        "user_id": str(user.id),
                        "package_id": str(package_id),
                        "plan_name": plan_name,
                    }
                },
                allow_promotion_codes=True,
            )

            logger.info(
                f"Created checkout session {checkout_session.id} for user {user.id}, plan {plan_name}"
            )

            return {
                "sessionId": checkout_session.id,
                "url": checkout_session.url
            }

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating checkout session: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to create checkout session: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating checkout session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating checkout session"
        )


@stripe_router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Stripe Webhook Handler",
    description="Handles Stripe webhook events for subscription lifecycle management",
)
async def stripe_webhook(
    request: Request,
    db: Session = Depends(database.get_db),
) -> Dict[str, str]:
    """
    Handles Stripe webhook events.
    
    This endpoint must be publicly accessible (no authentication required).
    Stripe signature verification ensures the request is from Stripe.
    
    Supported events:
    - checkout.session.completed
    - customer.subscription.created
    - customer.subscription.updated
    - customer.subscription.deleted
    - invoice.payment_succeeded
    - invoice.payment_failed
    """
    if not STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured"
        )

    payload = await request.body()
    sig_header: Optional[str] = request.headers.get("stripe-signature")

    if not sig_header:
        logger.warning("Missing stripe-signature header")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header"
        )

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload"
        )
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature"
        )

    # Handle the event
    event_type = event['type']
    event_data = event['data']['object']
    
    # Log the event type and ID
    logger.info(f"Received Stripe webhook event: {event_type}")
    logger.info(f"Event ID: {event.get('id')}")

    try:
        if event_type == 'checkout.session.completed':
            await handle_checkout_completed(event_data, db)
        elif event_type == 'customer.subscription.created':
            await handle_subscription_created(event_data, db)
        elif event_type == 'customer.subscription.updated':
            await handle_subscription_updated(event_data, db)
        elif event_type == 'customer.subscription.deleted':
            await handle_subscription_deleted(event_data, db)
        elif event_type == 'invoice.payment_succeeded':
            await handle_payment_succeeded(event_data, db)
        elif event_type == 'invoice.payment_failed':
            await handle_payment_failed(event_data, db)
        else:
            logger.info(f"Unhandled event type: {event_type}")

        return {"status": "success"}

    except Exception as e:
        logger.error(f"Error processing webhook event {event_type}: {e}", exc_info=True)
        # Return 200 to prevent Stripe from retrying
        # Log the error for manual investigation
        return {"status": "error", "message": str(e)}


async def handle_checkout_completed(session: Dict[str, Any], db: Session) -> None:
    """Handle successful checkout completion"""
    try:
        metadata = session.get('metadata', {})
        user_id = metadata.get('user_id')
        package_id_str = metadata.get('package_id')
        plan_name = metadata.get('plan_name')

        if not user_id or not package_id_str:
            logger.error(f"Missing metadata in checkout session: {session.get('id')}")
            return
        # package_id is stored as a UUID string in metadata
        package_id = package_id_str
        subscription_id_stripe = session.get('subscription')

        if not subscription_id_stripe:
            logger.warning(f"No subscription ID in checkout session: {session.get('id')}")
            return

        # Retrieve subscription from Stripe to get full details
        try:
            subscription_obj = stripe.Subscription.retrieve(subscription_id_stripe)
        except stripe.error.StripeError as e:
            logger.error(f"Failed to retrieve Stripe subscription: {e}")
            return

        stripe_customer_id = subscription_obj.customer
        stripe_price_id = subscription_obj['items']['data'][0]['price']['id']

        existing_subscriptions = db.query(SubscriptionsModel).filter(
            SubscriptionsModel.user_id == user_id,
            SubscriptionsModel.status == "active"
        ).all()

        for existing_sub in existing_subscriptions:
                existing_sub.status = "cancelled"
                existing_sub.updated_at = datetime.now()

        # Check if subscription already exists
        existing_subscription = db.query(SubscriptionsModel).filter(
            SubscriptionsModel.user_id == user_id,
            SubscriptionsModel.package_id == package_id
        ).first()

        if existing_subscription:
            # Update existing subscription
            existing_subscription.status = "active"
            existing_subscription.stripe_customer_id = stripe_customer_id
            existing_subscription.stripe_subscription_id = subscription_id_stripe
            existing_subscription.stripe_price_id = stripe_price_id
            existing_subscription.start_date = datetime.fromtimestamp(
                subscription_obj.current_period_start
            )
            existing_subscription.end_date = datetime.fromtimestamp(
                subscription_obj.current_period_end
            )
            existing_subscription.auto_renew = True
            existing_subscription.updated_at = datetime.now()
            logger.info(f"Updated subscription for user {user_id}, plan {plan_name}")
        else:
            # Create new subscription record
            new_subscription = SubscriptionsModel(
                user_id=user_id,
                package_id=package_id,
                status="active",
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=subscription_id_stripe,
                stripe_price_id=stripe_price_id,
                start_date=datetime.fromtimestamp(subscription_obj.current_period_start),
                end_date=datetime.fromtimestamp(subscription_obj.current_period_end),
                auto_renew=True
            )
            db.add(new_subscription)
            logger.info(f"Created new subscription for user {user_id}, plan {plan_name}")

        db.commit()
        logger.info(f"Successfully processed checkout.completed for user {user_id}")

    except SQLAlchemyError as e:
        logger.error(f"Database error in handle_checkout_completed: {e}", exc_info=True)
        db.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error in handle_checkout_completed: {e}", exc_info=True)
        db.rollback()
        raise


async def handle_subscription_created(subscription: Dict[str, Any], db: Session) -> None:
    """Handle subscription creation event"""
    try:
        metadata = subscription.get('metadata', {})
        user_id = metadata.get('user_id')
        package_id_str = metadata.get('package_id')

        if not user_id or not package_id_str:
            logger.warning(f"Missing metadata in subscription: {subscription.get('id')}")
            return
        # package_id is stored as a UUID string in metadata
        package_id = package_id_str
        stripe_subscription_id = subscription['id']
        stripe_customer_id = subscription['customer']
        stripe_price_id = subscription['items']['data'][0]['price']['id']

        existing_active_subscriptions = db.query(SubscriptionsModel).filter(
            SubscriptionsModel.user_id == user_id,
            SubscriptionsModel.status == "active"
        ).all()

        for existing_sub in existing_active_subscriptions:
            existing_sub.status = "cancelled"
            existing_sub.updated_at = datetime.now()

        # Check if subscription already exists by stripe_subscription_id OR (user_id, package_id)
        existing_by_stripe_id = db.query(SubscriptionsModel).filter(
            SubscriptionsModel.stripe_subscription_id == stripe_subscription_id
        ).first()

        existing_by_user_package = db.query(SubscriptionsModel).filter(
            SubscriptionsModel.user_id == user_id,
            SubscriptionsModel.package_id == package_id
        ).first()

        if existing_by_stripe_id:
            # Subscription already exists, just update it
            existing_by_stripe_id.status = subscription['status']
            existing_by_stripe_id.stripe_customer_id = stripe_customer_id
            existing_by_stripe_id.stripe_price_id = stripe_price_id
            existing_by_stripe_id.start_date = datetime.fromtimestamp(subscription['current_period_start'])
            existing_by_stripe_id.end_date = datetime.fromtimestamp(subscription['current_period_end'])
            existing_by_stripe_id.auto_renew = not subscription.get('cancel_at_period_end', False)
            existing_by_stripe_id.updated_at = datetime.now()
            db.commit()
            logger.info(f"Updated existing subscription from subscription.created event: {stripe_subscription_id}")
        elif existing_by_user_package:
            # Subscription exists for this user/package but with different stripe_subscription_id
            # Update it with the new stripe_subscription_id
            existing_by_user_package.stripe_subscription_id = stripe_subscription_id
            existing_by_user_package.stripe_customer_id = stripe_customer_id
            existing_by_user_package.stripe_price_id = stripe_price_id
            existing_by_user_package.status = subscription['status']
            existing_by_user_package.start_date = datetime.fromtimestamp(subscription['current_period_start'])
            existing_by_user_package.end_date = datetime.fromtimestamp(subscription['current_period_end'])
            existing_by_user_package.auto_renew = not subscription.get('cancel_at_period_end', False)
            existing_by_user_package.updated_at = datetime.now()
            db.commit()
            logger.info(f"Updated existing subscription with new stripe_subscription_id: {stripe_subscription_id}")
        else:
            # Create subscription record if it doesn't exist
            new_subscription = SubscriptionsModel(
                user_id=user_id,
                package_id=package_id,
                status=subscription['status'],
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
                stripe_price_id=stripe_price_id,
                start_date=datetime.fromtimestamp(subscription['current_period_start']),
                end_date=datetime.fromtimestamp(subscription['current_period_end']),
                auto_renew=not subscription.get('cancel_at_period_end', False)
            )
            db.add(new_subscription)
            db.commit()
            logger.info(f"Created subscription record from subscription.created event: {stripe_subscription_id}")

    except SQLAlchemyError as e:
        logger.error(f"Database error in handle_subscription_created: {e}", exc_info=True)
        db.rollback()
    except Exception as e:
        logger.error(f"Unexpected error in handle_subscription_created: {e}", exc_info=True)
        db.rollback()


async def handle_subscription_updated(subscription: Dict[str, Any], db: Session) -> None:
    """
    Handle subscription updates (plan changes, status changes, etc.)
    
    This function handles:
    - Plan upgrades/downgrades (price changes)
    - Status updates (active, past_due, cancelled, etc.)
    - Period end date updates
    - Auto-renewal status changes
    
    When a plan change is detected, it automatically cancels other active subscriptions
    to ensure only one active subscription exists per user.
    """
    try:
        stripe_subscription_id = subscription['id']
        db_subscription = db.query(SubscriptionsModel).filter(
            SubscriptionsModel.stripe_subscription_id == stripe_subscription_id
        ).first()

        if not db_subscription:
            logger.warning(f"Subscription not found in database: {stripe_subscription_id}")
            return

        # Get the current price_id from subscription to determine package_id
        stripe_price_id = None
        new_package_id = None
        
        try:
            # Extract price_id from subscription items
            subscription_items = subscription.get('items', {})
            if isinstance(subscription_items, dict) and 'data' in subscription_items:
                items_data = subscription_items['data']
                if items_data and len(items_data) > 0:
                    price_obj = items_data[0].get('price', {})
                    if isinstance(price_obj, dict):
                        stripe_price_id = price_obj.get('id')
                    elif hasattr(price_obj, 'id'):
                        stripe_price_id = price_obj.id
        except (KeyError, IndexError, AttributeError) as e:
            logger.warning(f"Could not extract price_id from subscription {stripe_subscription_id}: {e}")

        # Determine new package_id from metadata (stored as UUID string)
            metadata = subscription.get('metadata', {})
            if 'package_id' in metadata:
            new_package_id = metadata['package_id']

        # Detect plan change (upgrade or downgrade)
        plan_changed = False
        if new_package_id and db_subscription.package_id != new_package_id:
            plan_changed = True
            logger.info(
                f"Plan change detected for subscription {stripe_subscription_id}: "
                f"package_id {db_subscription.package_id} -> {new_package_id}"
            )

            existing_subscriptions = db.query(SubscriptionsModel).filter(
                SubscriptionsModel.user_id == db_subscription.user_id,
                SubscriptionsModel.status == "active",
            SubscriptionsModel.id != db_subscription.id
            ).all()

            for existing_sub in existing_subscriptions:
                existing_sub.status = "cancelled"
                existing_sub.updated_at = datetime.now()

        # Update package_id if plan changed
        if plan_changed and new_package_id:
            db_subscription.package_id = new_package_id

        # Update subscription status
        db_subscription.status = subscription['status']
        
        # Update price_id if available
        if stripe_price_id:
            db_subscription.stripe_price_id = stripe_price_id
        
        # Update period end date
        if 'current_period_end' in subscription:
            db_subscription.end_date = datetime.fromtimestamp(subscription['current_period_end'])
        
        # Update auto-renewal status
        db_subscription.auto_renew = not subscription.get('cancel_at_period_end', False)
        db_subscription.updated_at = datetime.now()

        db.commit()
        logger.info(
            f"Updated subscription {stripe_subscription_id} "
            f"(status: {subscription['status']}, package_id: {db_subscription.package_id})"
        )

    except SQLAlchemyError as e:
        logger.error(f"Database error in handle_subscription_updated: {e}", exc_info=True)
        db.rollback()
    except Exception as e:
        logger.error(f"Unexpected error in handle_subscription_updated: {e}", exc_info=True)
        db.rollback()


async def handle_subscription_deleted(subscription: Dict[str, Any], db: Session) -> None:
    """
    Handle subscription cancellation/deletion
    
    When a paid subscription is cancelled:
    - Marks the subscription as cancelled
    - Automatically reactivates the free plan to ensure user always has an active subscription
    """
    try:
        stripe_subscription_id = subscription['id']
        db_subscription = db.query(SubscriptionsModel).filter(
            SubscriptionsModel.stripe_subscription_id == stripe_subscription_id
        ).first()

        if not db_subscription:
            logger.warning(f"Subscription not found in database: {stripe_subscription_id}")
            return

        user_id = db_subscription.user_id
        
        # Get free package to check if this is a paid plan
        free_package = db.query(PackagesModel).filter(PackagesModel.package_name == "free").first()
        if not free_package:
            logger.error("Free package not found in database. Cannot reactivate free plan.")
            return
        
        was_paid_plan = db_subscription.package_id != free_package.id

        # Cancel the subscription
        db_subscription.status = "cancelled"
        db_subscription.auto_renew = False
        db_subscription.updated_at = datetime.now()

        logger.info(
            f"Cancelling subscription {stripe_subscription_id} "
            f"(package_id: {db_subscription.package_id}, user_id: {user_id})"
        )

        # If this was a paid subscription, reactivate free plan
        if was_paid_plan:
            # Check if free plan subscription already exists for this user
            free_subscription = db.query(SubscriptionsModel).filter(
                SubscriptionsModel.user_id == user_id,
                SubscriptionsModel.package_id == free_package.id  # Free plan
            ).first()

            if free_subscription:
                # Reactivate existing free subscription if it's not already active
                if free_subscription.status != "active":
                    free_subscription.status = "active"
                    free_subscription.auto_renew = True
                    free_subscription.updated_at = datetime.now()
                    logger.info(
                        f"Reactivated existing free plan subscription "
                        f"({free_subscription.id}) for user {user_id}"
                    )
                else:
                    logger.info(
                        f"Free plan subscription already active for user {user_id}"
                    )
            else:
                # Create new free subscription if it doesn't exist
                new_free_subscription = SubscriptionsModel(
                    user_id=user_id,
                    package_id=free_package.id,  # Free plan
                    status="active",
                    auto_renew=True
                )
                db.add(new_free_subscription)
                logger.info(
                    f"Created new free plan subscription for user {user_id} "
                    f"after cancelling paid subscription"
                )

            # Also cancel any other active paid subscriptions (edge case: multiple active subscriptions)
            other_active_subscriptions = db.query(SubscriptionsModel).filter(
                SubscriptionsModel.user_id == user_id,
                SubscriptionsModel.status == "active",
                SubscriptionsModel.package_id != free_package.id,  # Paid plans only
                SubscriptionsModel.id != db_subscription.id
            ).all()

            for other_sub in other_active_subscriptions:
                other_sub.status = "cancelled"
                other_sub.updated_at = datetime.now()
                logger.info(
                    f"Cancelled additional active subscription {other_sub.id} "
                    f"(package_id: {other_sub.package_id}) for user {user_id}"
                )

        db.commit()
        logger.info(
            f"Successfully processed cancellation for subscription {stripe_subscription_id}. "
            f"Free plan {'reactivated' if was_paid_plan else 'unchanged'} for user {user_id}"
        )

    except SQLAlchemyError as e:
        logger.error(f"Database error in handle_subscription_deleted: {e}", exc_info=True)
        db.rollback()
    except Exception as e:
        logger.error(f"Unexpected error in handle_subscription_deleted: {e}", exc_info=True)
        db.rollback()


async def handle_payment_succeeded(invoice: Dict[str, Any], db: Session) -> None:
    """Handle successful payment"""
    try:
        subscription_id_stripe = invoice.get('subscription')
        if not subscription_id_stripe:
            # One-time payment, not a subscription
            return

        db_subscription = db.query(SubscriptionsModel).filter(
            SubscriptionsModel.stripe_subscription_id == subscription_id_stripe
        ).first()

        if db_subscription:
            # Update subscription end date
            try:
                subscription_obj = stripe.Subscription.retrieve(subscription_id_stripe)
                
                # Convert Stripe object to dict if needed, or use dict access
                if hasattr(subscription_obj, 'to_dict'):
                    subscription_dict = subscription_obj.to_dict()
                elif isinstance(subscription_obj, dict):
                    subscription_dict = subscription_obj
                else:
                    # Try to access as dict
                    subscription_dict = dict(subscription_obj) if hasattr(subscription_obj, '__dict__') else {}
                
                # Use dictionary access for safety
                if 'current_period_end' in subscription_dict:
                    db_subscription.end_date = datetime.fromtimestamp(
                        subscription_dict['current_period_end']
                    )
                elif hasattr(subscription_obj, 'current_period_end'):
                    # Fallback to attribute access if dict access fails
                    db_subscription.end_date = datetime.fromtimestamp(
                        subscription_obj.current_period_end
                    )
                
                if 'status' in subscription_dict:
                    db_subscription.status = subscription_dict['status']
                elif hasattr(subscription_obj, 'status'):
                    db_subscription.status = subscription_obj.status
                
                db_subscription.updated_at = datetime.now()
                db.commit()
                logger.info(f"Updated subscription after successful payment: {subscription_id_stripe}")
            except stripe.error.StripeError as e:
                logger.error(f"Failed to retrieve subscription for payment update: {e}")
            except (KeyError, AttributeError) as e:
                logger.warning(f"Missing expected field in subscription object: {e}")
                # Still update the timestamp even if we can't update the end_date
                db_subscription.updated_at = datetime.now()
                db.commit()

    except SQLAlchemyError as e:
        logger.error(f"Database error in handle_payment_succeeded: {e}", exc_info=True)
        db.rollback()
    except Exception as e:
        logger.error(f"Unexpected error in handle_payment_succeeded: {e}", exc_info=True)
        db.rollback()


async def handle_payment_failed(invoice: Dict[str, Any], db: Session) -> None:
    """Handle failed payment"""
    try:
        subscription_id_stripe = invoice.get('subscription')
        if not subscription_id_stripe:
            return

        db_subscription = db.query(SubscriptionsModel).filter(
            SubscriptionsModel.stripe_subscription_id == subscription_id_stripe
        ).first()

        if db_subscription:
            # Mark subscription as past_due
            db_subscription.status = "past_due"
            db_subscription.updated_at = datetime.now()
            db.commit()
            logger.warning(f"Payment failed for subscription {subscription_id_stripe}")

    except SQLAlchemyError as e:
        logger.error(f"Database error in handle_payment_failed: {e}", exc_info=True)
        db.rollback()
    except Exception as e:
        logger.error(f"Unexpected error in handle_payment_failed: {e}", exc_info=True)
        db.rollback()

