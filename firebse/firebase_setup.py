import json
import logging
import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials

logger = logging.getLogger(__name__)

DEFAULT_CREDENTIALS_PATH = "firebase-service-account.json"


def _load_credentials():
    firebase_creds_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if firebase_creds_json:
        cred_dict = json.loads(firebase_creds_json)
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
        return credentials.Certificate(cred_dict)

    credentials_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", DEFAULT_CREDENTIALS_PATH).strip()
    path = Path(credentials_path)
    if not path.is_file():
        if path.exists() and path.is_dir():
            raise FileNotFoundError(
                f"Firebase credentials path '{credentials_path}' is a directory, not a file. "
                "Remove the Docker bind mount folder or set FIREBASE_SERVICE_ACCOUNT_JSON in .env."
            )
        raise FileNotFoundError(
            f"Firebase credentials file not found at '{credentials_path}'. "
            "Set FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_SERVICE_ACCOUNT_PATH."
        )

    return credentials.Certificate(str(path))


try:
    cred = _load_credentials()
    firebase_admin.initialize_app(cred)
    logger.info("Firebase Admin SDK initialized")
except FileNotFoundError as exc:
    logger.warning("Firebase Admin SDK not initialized: %s", exc)
except json.JSONDecodeError as exc:
    logger.error("Invalid FIREBASE_SERVICE_ACCOUNT_JSON: %s", exc)
    raise
except Exception:
    logger.exception("Failed to initialize Firebase Admin SDK")
    raise
