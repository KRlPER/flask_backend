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
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

CORS(app, origins=[
    "https://lockerbox.netlify.app",
    "https://kriper1.netlify.app",
    "http://localhost:3000"
], supports_credentials=True)

ALLOWED_EXTENSIONS = {
    "png","jpg","jpeg","gif",
    "pdf","txt","doc","docx","xls","xlsx","ppt","pptx"
}

# -------------------------
# Helpers (CRITICAL)
# -------------------------
def serialize(doc):
    """Convert Mongo document to JSON-safe dict"""
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc.pop("_id", None)
    return doc

def allowed_file(filename):
    return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXTENSIONS

# -------------------------
# Health
# -------------------------
@app.route("/health")
def health():
    return jsonify({"ok": True})

# -------------------------
# Register
# -------------------------
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    email = data.get("email","").lower()
    password = data.get("password","")
    name = data.get("name","")

    if not email or not password or not name:
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
            "user": {"id": str(res.inserted_id), "name": name, "email": email}
        }), 201
    except DuplicateKeyError:
        return jsonify({"success": False, "error": "Email exists"}), 409

# -------------------------
# Login
# -------------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    user = users_collection.find_one({"email": data.get("email","").lower()})

    if not user or not check_password_hash(user["password"], data.get("password","")):
        return jsonify({"success": False, "error": "Invalid credentials"}), 401

    user = serialize(user)
    return jsonify({"success": True, "user": user})

# -------------------------
# Uploads
# -------------------------
@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# -------------------------
# Add locker item (NOTE OR FILE)
# -------------------------
@app.route("/locker/<user_id>", methods=["POST"])
def add_locker(user_id):

    # FILE
    if request.files:
        file = request.files.get("file")
        if not file or not allowed_file(file.filename):
            return jsonify({"success": False, "error": "Invalid file"}), 400

        filename = secure_filename(file.filename)
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
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

    # NOTE
    data = request.get_json()
    if not data.get("content"):
        return jsonify({"success": False, "error": "Content required"}), 400

    item = {
        "user_id": user_id,
        "type": "note",
        "title": data.get("title",""),
        "content": data["content"],
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
    items = locker_collection.find({"user_id": user_id}).sort("created_at",-1)
    return jsonify({
        "success": True,
        "items": [serialize(i) for i in items]
    })

# -------------------------
# Delete item
# -------------------------
@app.route("/locker/item/<item_id>", methods=["DELETE"])
def delete_item(item_id):
    locker_collection.delete_one({"_id": ObjectId(item_id)})
    return jsonify({"success": True})

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",5000)))
