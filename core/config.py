from dotenv import load_dotenv
import os
from openai import OpenAI
from pinecone import Pinecone
from pathlib import Path

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

client = OpenAI(api_key=OPENAI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)

KB_DIR = Path("uploaded_kb")
KB_DIR.mkdir(exist_ok=True)

EMBED_MODEL = "text-embedding-3-large"
GEN_MODEL = "gpt-4.1-mini"

# Stripe Configuration
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_ID_ESSENTIAL = os.getenv("STRIPE_PRICE_ID_ESSENTIAL")
STRIPE_PRICE_ID_PRO = os.getenv("STRIPE_PRICE_ID_PRO")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Comma-separated list of allowed affiliate tracking codes
AFFILIATE_CODES = {
    code.strip().lower()
    for code in os.getenv("AFFILIATE_CODES", "").split(",")
    if code and code.strip()
}