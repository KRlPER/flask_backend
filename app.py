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

# import db handles connection and exposes `db`, `users_collection`, `locker_collection`
from db import db, users_collection, locker_collection

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------
# App init & config
# -------------------------
app = Flask(__name__)

# Upload folder config
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Limit uploads to 8 MB (adjust if needed)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB

# Allowed extensions
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
ALLOWED_FILE_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS.union(
    {"pdf", "txt", "doc", "docx", "xls", "xlsx", "ppt", "pptx"}
)

# -------------------------
# CORS: restrict to your frontend(s)
# -------------------------
# Provide FRONTEND_URLS as a comma-separated env var, e.g.
# FRONTEND_URLS="https://your-frontend.onrender.com,http://localhost:5173"
frontend_env = os.getenv("FRONTEND_URLS", "")
if frontend_env:
    origins = [u.strip() for u in frontend_env.split(",") if u.strip()]
else:
    # Fallback for dev convenience - tighten in production
    origins = ["http://localhost:3000", "http://localhost:5173"]

logger.info("CORS origins: %s", origins)
# -------------------------
# CORS — allow Netlify + Localhost
# -------------------------
CORS(app, origins=[
    "https://kriper1.netlify.app",
    "http://localhost:3000"
], supports_credentials=True)


# -------------------------
# Helpers
# -------------------------
def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_FILE_EXTENSIONS


# -------------------------
# Health check
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
        logger.info("Register payload: %s", {k: (v if k != "password" else "***") for k, v in (data or {}).items()})

        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        if not name or not email or not password:
            return jsonify({"success": False, "error": "Missing name/email/password"}), 400

        if "@" not in email:
            return jsonify({"success": False, "error": "Invalid email"}), 400

        if len(password) < 6:
            return jsonify({"success": False, "error": "Password must be at least 6 characters"}), 400

        hashed_password = generate_password_hash(password, method="pbkdf2:sha256")


        user_doc = {
            "name": name,
            "email": email,
            "password": hashed_password,
            "photo": None,
            "created_at": datetime.utcnow(),
        }

        try:
            res = users_collection.insert_one(user_doc)
        except DuplicateKeyError:
            logger.warning("Duplicate registration attempt for email: %s", email)
            return jsonify({"success": False, "error": "Email already registered"}), 409

        inserted_id = str(res.inserted_id)
        logger.info("User created: %s", inserted_id)

        safe_user = {"id": inserted_id, "name": name, "email": email}
        return jsonify({"success": True, "message": "Registration successful!", "user": safe_user}), 201

    except Exception as e:
        logger.exception("Register failed")
        return jsonify({"success": False, "error": "Internal server error", "details": str(e)}), 500


# -------------------------
# LOGIN
# -------------------------
@app.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json(force=True)
        logger.info("Login payload: %s", {k: (v if k != "password" else "***") for k, v in (data or {}).items()})

        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        if not email or not password:
            return jsonify({"success": False, "error": "Missing email/password"}), 400

        user = users_collection.find_one({"email": email})
        if not user:
            return jsonify({"success": False, "error": "Invalid credentials"}), 401

        if not check_password_hash(user.get("password", ""), password):
            return jsonify({"success": False, "error": "Invalid credentials"}), 401

        safe_user = {"id": str(user["_id"]), "name": user.get("name"), "email": user.get("email"), "photo": user.get("photo")}
        return jsonify({"success": True, "message": "Login successful", "user": safe_user}), 200

    except Exception as e:
        logger.exception("Login failed")
        return jsonify({"success": False, "error": "Internal server error", "details": str(e)}), 500


# -------------------------
# PROFILE
# -------------------------
@app.route("/profile/<user_id>", methods=["GET"])
def get_profile(user_id):
    try:
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404

        safe_user = {"id": str(user["_id"]), "name": user.get("name"), "email": user.get("email"), "photo": user.get("photo")}
        return jsonify({"success": True, "user": safe_user}), 200
    except Exception as e:
        logger.exception("Get profile failed")
        return jsonify({"success": False, "error": "Invalid user ID", "details": str(e)}), 400


# -------------------------
# UPLOAD PROFILE PHOTO
# -------------------------
@app.route("/upload-photo/<user_id>", methods=["POST"])
def upload_photo(user_id):
    try:
        if "photo" not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        file = request.files["photo"]
        if file.filename == "":
            return jsonify({"success": False, "error": "No file selected"}), 400

        if file and allowed_image(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

            # avoid filename collisions
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(filepath):
                filename = f"{base}_{counter}{ext}"
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                counter += 1

            file.save(filepath)

            users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": {"photo": f"/uploads/{filename}"}})

            return jsonify({"success": True, "message": "Photo uploaded successfully!", "photo": f"/uploads/{filename}"}), 200

        return jsonify({"success": False, "error": "Invalid file type"}), 400
    except Exception as e:
        logger.exception("Upload photo failed")
        return jsonify({"success": False, "error": "Internal server error", "details": str(e)}), 500


# -------------------------
# SERVE UPLOADED FILES
# -------------------------
@app.route("/uploads/<filename>")
def serve_uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)



# -------------------------
# LOCKER: add item (file or note) — FIXED VERSION
# -------------------------
@app.route("/locker/<user_id>", methods=["POST"])
def add_locker_item(user_id):
    try:
        # --- FILE UPLOAD HANDLING ---
        if request.content_type and "multipart/form-data" in request.content_type:

            # check file field
            if "file" not in request.files:
                return jsonify({"success": False, "error": "No file uploaded"}), 400

            file = request.files["file"]

            if file.filename == "":
                return jsonify({"success": False, "error": "Empty filename"}), 400

            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

            # avoid filename conflicts
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(filepath):
                filename = f"{base}_{counter}{ext}"
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                counter += 1

            # save file
            file.save(filepath)

            item = {
                "user_id": user_id,
                "type": "file",
                "title": request.form.get("title") or filename,
                "file_path": f"/uploads/{filename}",
                "mime": file.mimetype,
                "tags": [],
                "created_at": datetime.utcnow(),
            }

            res = locker_collection.insert_one(item)

            # convert ObjectId to string BEFORE sending JSON
            item["id"] = str(res.inserted_id)

            return jsonify({"success": True, "item": item}), 201

        # --- NOTE HANDLING ---
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
        return jsonify({"success": False, "error": "Internal error", "details": str(e)}), 500

# -------------------------
# LOCKER: list items
# -------------------------
@app.route("/locker/<user_id>", methods=["GET"])
def get_locker_items(user_id):
    try:
        rows = list(locker_collection.find({"user_id": user_id}).sort("created_at", -1))
        items = []
        for r in rows:
            item = {
                "id": str(r.get("_id")),
                "user_id": r.get("user_id"),
                "type": r.get("type"),
                "title": r.get("title"),
                "content": r.get("content"),
                "file_path": r.get("file_path"),
                "mime": r.get("mime"),
                "tags": r.get("tags", []),
                "created_at": r.get("created_at").isoformat() if r.get("created_at") else None,
            }
            items.append(item)
        return jsonify({"success": True, "items": items}), 200
    except Exception as e:
        logger.exception("Get locker items failed")
        return jsonify({"success": False, "error": "internal error", "details": str(e)}), 500


# -------------------------
# LOCKER: delete item
# -------------------------
@app.route("/locker/item/<item_id>", methods=["DELETE"])
def delete_locker_item(item_id):
    try:
        obj = locker_collection.find_one({"_id": ObjectId(item_id)})
        if not obj:
            return jsonify({"success": False, "error": "Not found"}), 404

        if obj.get("type") == "file" and obj.get("file_path"):
            filename = os.path.basename(obj.get("file_path"))
            path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning("Could not remove file: %s", e)

        locker_collection.delete_one({"_id": ObjectId(item_id)})
        return jsonify({"success": True}), 200
    except Exception as e:
        logger.exception("Delete locker item failed")
        return jsonify({"success": False, "error": "invalid id", "details": str(e)}), 400


# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    # DO NOT set debug=True in production
    port = int(os.getenv("PORT", 5000))
    logger.info("Starting Flask app on port %s", port)
    app.run(host="0.0.0.0", port=port)
