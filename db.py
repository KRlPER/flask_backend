# db.py
import os
import sys
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable not set")

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # force a connection to detect problems early
    client.admin.command("ping")

    # determine DB name from URI if present otherwise fallback
    db_name = MONGO_URI.split("/")[-1].split("?")[0] or "fullstack_app"
    db = client[db_name]
    print(f"✅ MongoDB connected successfully! Using database: {db_name}")

    # Collections
    users_collection = db["users"]
    locker_collection = db["locker_items"]

    # Ensure unique index on email
    try:
        users_collection.create_index("email", unique=True)
        print("✅ Ensured unique index on users.email")
    except Exception as ie:
        # Don't crash if index already exists or something else; log instead
        print("⚠️ Could not create unique index on users.email:", ie)

except ServerSelectionTimeoutError as err:
    print("\n❌ MongoDB connection failed (timeout)!")
    print("Reason:", err)
    print("\n🔧 FIX SUGGESTIONS:")
    print("1) Ensure MONGO_URI is correct.")
    print("2) Check network/IP allowlist for Atlas.")
    print("3) Ensure credentials in URI are correct.")
    sys.exit(1)
except Exception as e:
    print("\n❌ MongoDB connection failed!")
    print("Reason:", e)
    sys.exit(1)
