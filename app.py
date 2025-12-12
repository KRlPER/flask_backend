# app.py
import os
import logging
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from pymongo.errors import DuplicateKeyError

from db import db, users_collection, locker_collection

# -------------------------
# LOGGING
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------
# FLASK APP CONFIG
# -------------------------
app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Raise upload size to 25MB
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

# Allowed file types
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
ALLOWED_FILE_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS.union(
    {"pdf", "txt", "doc", "docx", "xls", "xlsx", "ppt", "pptx"}
)

# -------------------------
# CORS (Netlify + Local)
# -------------------------
CORS(app, origins=[
    "https://kriper1.netlify.app",
    "http://localhost:3000",
    "http://localhost:5173"
], supports_credentials=True)


# -------------------------
# HELPERS
# -------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_FILE_EXTENSIONS


# -------------------------
# HEALTH CHECK
# -------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True}), 200


# -------------------------
# REGISTER
# -------------------------
@app.route("/register", methods=["POST"])
def register():
    try:
        data = request.get_json(force=True)

        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        if not name or not email or not password:
            return jsonify({"success": False, "error": "Missing fields"}), 400

        hashed = generate_password_hash(password, method="pbkdf2:sha256")

        user_doc = {
            "name": name,
            "email": email,
            "password": hashed,
            "photo": None,
            "created_at": datetime.utcnow(),
        }

        res = users_collection.insert_one(user_doc)

        return jsonify({
            "success": True,
            "message": "Registration successful!",
            "user": {"id": str(res.inserted_id), "name": name, "email": email}
        }), 201

    except DuplicateKeyError:
        return jsonify({"success": False, "error": "Email already registered"}), 409

    except Exception as e:
        logger.exception("Register failed")
        return jsonify({"success": False, "error": str(e)}), 500


# -------------------------
# LOGIN
# -------------------------
@app.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json(force=True)

        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        user = users_collection.find_one({"email": email})
        if not user:
            return jsonify({"success": False, "error": "Invalid credentials"}), 401

        if not check_password_hash(user["password"], password):
            return jsonify({"success": False, "error": "Invalid credentials"}), 401

        return jsonify({
            "success": True,
            "message": "Login successful",
            "user": {
                "id": str(user["_id"]),
                "name": user["name"],
                "email": user["email"],
                "photo": user.get("photo")
            }
        }), 200

    except Exception as e:
        logger.exception("Login failed")
        return jsonify({"success": False, "error": str(e)}), 500


# -------------------------
# SERVE UPLOADED FILES
# -------------------------
@app.route("/uploads/<path:filename>")
def serve_uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# -------------------------
# ADD LOCKER ITEM (FIXED)
# -------------------------
@app.route("/locker/<user_id>", methods=["POST"])
def add_locker_item(user_id):
    try:
        # ======== FILE UPLOAD ========
        if request.content_type and "multipart/form-data" in request.content_type:

            file = request.files.get("file")
            if not file or file.filename == "":
                return jsonify({"success": False, "error": "No file selected"}), 400

            if not allowed_file(file.filename):
                return jsonify({"success": False, "error": "Invalid file type"}), 400

            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

            # avoid file conflicts
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(save_path):
                filename = f"{base}_{counter}{ext}"
                save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                counter += 1

            file.save(save_path)

            item = {
                "user_id": user_id,
                "type": "file",
                "title": request.form.get("title") or filename,
                "file_path": f"/uploads/{filename}",
                "mime": file.mimetype,
                "tags": [],
                "created_at": datetime.utcnow()
            }

            res = locker_collection.insert_one(item)
            item["id"] = str(res.inserted_id)  # FIXED: always convert

            return jsonify({"success": True, "item": item}), 201

        # ======== NOTE ADD ========
        data = request.get_json(force=True)
        content = (data.get("content") or "").strip()

        if not content:
            return jsonify({"success": False, "error": "Content required"}), 400

        item = {
            "user_id": user_id,
            "type": "note",
            "title": data.get("title") or "",
            "content": content,
            "tags": [],
            "created_at": datetime.utcnow(),
        }

        res = locker_collection.insert_one(item)
        item["id"] = str(res.inserted_id)

        return jsonify({"success": True, "item": item}), 201

    except Exception as e:
        logger.exception("Add locker item failed")
        return jsonify({"success": False, "error": str(e)}), 500


# -------------------------
# LIST LOCKER ITEMS
# -------------------------
@app.route("/locker/<user_id>", methods=["GET"])
def get_locker_items(user_id):
    try:
        rows = locker_collection.find({"user_id": user_id}).sort("created_at", -1)

        items = []
        for r in rows:
            items.append({
                "id": str(r["_id"]),
                "user_id": r["user_id"],
                "type": r["type"],
                "title": r.get("title"),
                "content": r.get("content"),
                "file_path": r.get("file_path"),
                "mime": r.get("mime"),
                "tags": r.get("tags", []),
                "created_at": r["created_at"].isoformat()
            })

        return jsonify({"success": True, "items": items}), 200

    except Exception as e:
        logger.exception("Get locker items failed")
        return jsonify({"success": False, "error": str(e)}), 500


# -------------------------
# DELETE LOCKER ITEM
# -------------------------
@app.route("/locker/item/<item_id>", methods=["DELETE"])
def delete_locker_item(item_id):
    try:
        obj = locker_collection.find_one({"_id": ObjectId(item_id)})
        if not obj:
            return jsonify({"success": False, "error": "Not found"}), 404

        # delete file if applicable
        if obj["type"] == "file" and obj.get("file_path"):
            filename = obj["file_path"].replace("/uploads/", "")
            full_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            if os.path.exists(full_path):
                os.remove(full_path)

        locker_collection.delete_one({"_id": ObjectId(item_id)})
        return jsonify({"success": True}), 200

    except Exception as e:
        logger.exception("Delete locker item failed")
        return jsonify({"success": False, "error": str(e)}), 500


# -------------------------
# RUN SERVER
# -------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info("Flask running on port %s", port)
    app.run(host="0.0.0.0", port=port)
