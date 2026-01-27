import firebase_admin
from firebase_admin import credentials
import os
import json

# Load Firebase credentials from environment variable or file
firebase_creds_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

if firebase_creds_json:
    # Load from environment variable (production)
    cred_dict = json.loads(firebase_creds_json)
    cred = credentials.Certificate(cred_dict)
else:
    # Load from file (local development)
    cred = credentials.Certificate("firebase-service-account.json")

firebase_admin.initialize_app(cred)
