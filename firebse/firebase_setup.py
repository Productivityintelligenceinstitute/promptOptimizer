import firebase_admin
from firebase_admin import credentials
import os
import json

# Load Firebase credentials from environment variable or file
firebase_creds_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

if firebase_creds_json:
    # Load from environment variable (production)
    cred_dict = json.loads(firebase_creds_json)
    # Fix escaped newlines in private_key (replace \\n with actual newlines)
    if "private_key" in cred_dict:
        cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
    cred = credentials.Certificate(cred_dict)
else:
    # Load from file (local development)
    cred = credentials.Certificate("firebase-service-account.json")

firebase_admin.initialize_app(cred)
