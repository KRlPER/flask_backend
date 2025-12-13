import os
import logging
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from pymongo.errors import DuplicateKeyError

from db import users_collection, locker_collection

# -------------------------
# App setup
# -------------------------
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8MB

CORS(
    app,
    origins=[
        "https://kriper1.netlify.app",
        "http://localhost:3000"
    ],
    supports_credentials=True
)

ALLOWED_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif",
    "pdf", "txt", "doc", "docx",
    "xls", "xlsx", "ppt", "pptx"
}

# -------------------------
# Helpers
# -------------------------
def serialize(doc):
    """Convert Mongo document to JSON-safe dict"""
    if not doc:
        return None
    doc = dict(doc)
    doc["id"] = str(doc["_id"])
    doc.pop("_id", None)

    if "created_at" in doc and doc["created_at"]:
        doc["created_at"] = doc["created_at"].isoformat()

    return doc

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# -------------------------
# Health
# -------------------------
@app.route("/health")
def health():
    return jsonify({"ok": True}), 200

# -------------------------
# Register
# -------------------------
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(force=True)

    name = data.get("name", "").strip()
    email = data.get("email", "").lower().strip()
    password = data.get("password", "")

    if not name or not email or not password:
        return jsonify({"success": False, "error": "Missing fields"}), 400

    try:
        user = {
            "name": name,
            "email": email,
            "password": generate_password_hash(password),
            "photo": None,
            "created_at": datetime.utcnow()
        }

        res = users_collection.insert_one(user)

        return jsonify({
            "success": True,
            "user": {
                "id": str(res.inserted_id),
                "name": name,
                "email": email
            }
        }), 201

    except DuplicateKeyError:
        return jsonify({"success": False, "error": "Email already exists"}), 409

# -------------------------
# Login
# -------------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    email = data.get("email", "").lower()
    password = data.get("password", "")

    user = users_collection.find_one({"email": email})

    if not user or not check_password_hash(user["password"], password):
        return jsonify({"success": False, "error": "Invalid credentials"}), 401

    return jsonify({
        "success": True,
        "user": serialize(user)
    }), 200

# -------------------------
# Serve uploads
# -------------------------
@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# -------------------------
# Add locker item (NOTE or FILE)
# -------------------------
@app.route("/locker/<user_id>", methods=["POST"])
def add_locker(user_id):

    # ---------- FILE ----------
    if request.files and "file" in request.files:
        file = request.files["file"]

        if file.filename == "" or not allowed_file(file.filename):
            return jsonify({"success": False, "error": "Invalid file"}), 400

        filename = secure_filename(file.filename)
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        # prevent overwrite
        base, ext = os.path.splitext(filename)
        count = 1
        while os.path.exists(path):
            filename = f"{base}_{count}{ext}"
            path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            count += 1

        file.save(path)

        item = {
            "user_id": user_id,
            "type": "file",
            "title": request.form.get("title") or filename,
            "file_path": f"/uploads/{filename}",
            "mime": file.mimetype,
            "created_at": datetime.utcnow()
        }

        res = locker_collection.insert_one(item)
        item["_id"] = res.inserted_id

        return jsonify({"success": True, "item": serialize(item)}), 201

    # ---------- NOTE ----------
    data = request.get_json(force=True)
    content = data.get("content", "").strip()

    if not content:
        return jsonify({"success": False, "error": "Content required"}), 400

    item = {
        "user_id": user_id,
        "type": "note",
        "title": data.get("title", ""),
        "content": content,
        "created_at": datetime.utcnow()
    }

    res = locker_collection.insert_one(item)
    item["_id"] = res.inserted_id

    return jsonify({"success": True, "item": serialize(item)}), 201

# -------------------------
# Get locker items
# -------------------------
@app.route("/locker/<user_id>", methods=["GET"])
def get_locker(user_id):
    items = locker_collection.find({"user_id": user_id}).sort("created_at", -1)
    return jsonify({
        "success": True,
        "items": [serialize(i) for i in items]
    }), 200

# -------------------------
# Delete locker item
# -------------------------
@app.route("/locker/item/<item_id>", methods=["DELETE"])
def delete_item(item_id):
    locker_collection.delete_one({"_id": ObjectId(item_id)})
    return jsonify({"success": True}), 200

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
