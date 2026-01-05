#!/usr/bin/env python3
"""
Script to list all Stripe prices in the current mode (test/live)
This helps identify the correct price IDs for your environment.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import stripe

# Load environment variables
load_dotenv()

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")

if not STRIPE_SECRET_KEY:
    print("ERROR: STRIPE_SECRET_KEY not found in .env file")
    sys.exit(1)

# Determine mode
mode = "LIVE" if STRIPE_SECRET_KEY.startswith("sk_live_") else "TEST"
print(f"\n{'='*60}")
print(f"Stripe Mode: {mode}")
print(f"Using Key: {STRIPE_SECRET_KEY[:20]}...")
print(f"{'='*60}\n")

# Initialize Stripe
stripe.api_key = STRIPE_SECRET_KEY

try:
    # List all products
    print("Fetching products and prices...\n")
    products = stripe.Product.list(limit=100, active=True)
    
    if not products.data:
        print("No active products found in this mode.")
        sys.exit(0)
    
    print(f"Found {len(products.data)} product(s):\n")
    
    for product in products.data:
        print(f"Product: {product.name}")
        print(f"  Product ID: {product.id}")
        print(f"  Description: {product.description or 'N/A'}")
        print(f"  Active: {product.active}")
        print(f"\n  Prices:")
        
        # Get prices for this product
        prices = stripe.Price.list(product=product.id, limit=100, active=True)
        
        if not prices.data:
            print("    No active prices found for this product.\n")
            continue
        
        for price in prices.data:
            amount = price.unit_amount / 100 if price.unit_amount else 0
            currency = price.currency.upper()
            interval = price.recurring.interval if price.recurring else "one-time"
            
            print(f"    - Price ID: {price.id}")
            print(f"      Amount: ${amount:.2f} {currency}")
            print(f"      Type: {interval}")
            if price.recurring:
                print(f"      Interval: {price.recurring.interval_count} {interval}(s)")
            print(f"      Active: {price.active}")
            print()
        
        print("-" * 60)
        print()
    
    print("\n" + "="*60)
    print("RECOMMENDATION:")
    print("="*60)
    print("Copy the Price IDs from above and update your .env file:")
    print("  STRIPE_PRICE_ID_ESSENTIAL=price_XXXXX")
    print("  STRIPE_PRICE_ID_PRO=price_XXXXX")
    print("="*60 + "\n")

except stripe.error.AuthenticationError:
    print("ERROR: Invalid Stripe API key. Please check your STRIPE_SECRET_KEY in .env")
    sys.exit(1)
except stripe.error.StripeError as e:
    print(f"ERROR: Stripe API error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: Unexpected error: {e}")
    sys.exit(1)

