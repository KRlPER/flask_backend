# backend/db.py
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import sys

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

# -----------------------------
# Get MongoDB URI
# -----------------------------
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError(
        "❌ ERROR: MONGO_URI not found. Add it to your .env file or Render environment variables."
    )

# -----------------------------
# Connect to MongoDB
# -----------------------------
try:
    # 5-second timeout to fail fast if DNS or URI is wrong
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)

    # Force connection
    client.admin.command("ping")

    # Use the database name defined inside your connection string OR fallback to "fullstack_app"
    db_name = MONGO_URI.split("/")[-1].split("?")[0] or "fullstack_app"
    db = client[db_name]

    print(f"✅ MongoDB connected successfully! Using database: {db_name}")

except Exception as e:
    print("\n❌ MongoDB connection failed!")
    print("Reason:", e)
    print("\n🔧 FIX SUGGESTIONS:")
    print("1️⃣ Ensure your MONGO_URI is EXACTLY copied from MongoDB Atlas.")
    print("2️⃣ Ensure username/password are correct and not URL-encoded incorrectly.")
    print("3️⃣ Ensure your IP is allowed in Atlas → Network Access → Allow IP.")
    print("4️⃣ Check SRV DNS works: nslookup -type=SRV _mongodb._tcp.<cluster>.mongodb.net")
    print("5️⃣ For Render: add MONGO_URI in Environment Variables.")
    print("\nApp cannot continue without database. Exiting...\n")

    sys.exit(1)  # <-- prevent the Flask app from running with db=None
