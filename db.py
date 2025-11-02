# backend/db.py
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

# -----------------------------
# MongoDB Configuration
# -----------------------------
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise ValueError("❌ ERROR: MONGO_URI not found in environment variables!")

try:
    client = MongoClient(MONGO_URI)
    db = client["fullstack_app"]  # name of your database
    client.admin.command("ping")
    print("✅ MongoDB connection successful!")
except Exception as e:
    print("❌ MongoDB connection failed:", e)
    db = None
