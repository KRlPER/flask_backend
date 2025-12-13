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

# Upload folder
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Upload limit: 8 MB
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  

# Allowed extensions
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
ALLOWED_FILE_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS.union(
    {"pdf", "txt", "doc", "docx", "xls", "xlsx", "ppt", "pptx"}
)

# -------------------------
# CORS for Netlify + Localhost
# -------------------------
CORS(app, origins=[
    "https://kriper1.netlify.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000"
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
        logger.info("Register payload: %s", {k: "***" if k=="password" else v for k,v in data.items()})

        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        if not name or not email or not password:
            return jsonify({"success": False, "error": "Missing fields"}), 400

        if "@" not in email:
            return jsonify({"success": False, "error": "Invalid email"}), 400

        if len(password) < 6:
            return jsonify({"success": False, "error": "Password too short"}), 400

        hashed = generate_password_hash(password, method="pbkdf2:sha256")

        user_doc = {
            "name": name,
            "email": email,
            "password": hashed,
            "photo": None,
            "created_at": datetime.utcnow(),
        }

        try:
            result = users_collection.insert_one(user_doc)
        except DuplicateKeyError:
            return jsonify({"success": False, "error": "Email already registered"}), 409

        safe_user = {
            "id": str(result.inserted_id),
            "name": name,
            "email": email
        }

        return jsonify({"success": True, "message": "Registered successfully", "user": safe_user}), 201

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
        logger.info("Login payload: %s", {"email": data.get("email"), "password": "***"})

        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        user = users_collection.find_one({"email": email})
        if not user:
            return jsonify({"success": False, "error": "Invalid credentials"}), 401

        if not check_password_hash(user.get("password", ""), password):
            return jsonify({"success": False, "error": "Invalid credentials"}), 401

        safe_user = {
            "id": str(user["_id"]),
            "name": user.get("name"),
            "email": user.get("email"),
            "photo": user.get("photo")
        }

        return jsonify({"success": True, "message": "Login successful", "user": safe_user}), 200

    except Exception as e:
        logger.exception("Login failed")
        return jsonify({"success": False, "error": str(e)}), 500



# -------------------------
# PROFILE
# -------------------------
@app.route("/profile/<user_id>", methods=["GET"])
def get_profile(user_id):
    try:
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404

        safe_user = {
            "id": str(user["_id"]),
            "name": user.get("name"),
            "email": user.get("email"),
            "photo": user.get("photo")
        }
        return jsonify({"success": True, "user": safe_user}), 200

    except Exception as e:
        logger.exception("Profile fetch failed")
        return jsonify({"success": False, "error": str(e)}), 500



# -------------------------
# UPLOAD PROFILE PHOTO
# -------------------------
@app.route("/upload-photo/<user_id>", methods=["POST"])
def upload_photo(user_id):
    try:
        if "photo" not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        file = request.files["photo"]
        if not allowed_image(file.filename):
            return jsonify({"success": False, "error": "Invalid image type"}), 400

        filename = secure_filename(file.filename)
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(path):
            filename = f"{base}_{counter}{ext}"
            path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            counter += 1

        file.save(path)

        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"photo": f"/uploads/{filename}"}}
        )

        return jsonify({"success": True, "photo": f"/uploads/{filename}"}), 200

    except Exception as e:
        logger.exception("Photo upload failed")
        return jsonify({"success": False, "error": str(e)}), 500


# -------------------------
# SERVE UPLOADED FILES
# -------------------------
@app.route("/uploads/<filename>")
def serve_uploaded(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)



# ------------------------------------------------------
# LOCKER: ADD ITEM (NOTE or FILE) — FIXED COMPLETELY
# ------------------------------------------------------
@app.route("/locker/<user_id>", methods=["POST"])
def add_locker_item(user_id):
    try:
        # -----------------------------
        # FILE UPLOAD
        # -----------------------------
        if request.content_type and "multipart/form-data" in request.content_type:

            file = request.files.get("file")
            if not file or file.filename == "":
                return jsonify({"success": False, "error": "No file selected"}), 400

            if not allowed_file(file.filename):
                return jsonify({"success": False, "error": "Invalid file type"}), 400

            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

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

            item_return = item.copy()
            item_return["id"] = str(res.inserted_id)

            return jsonify({"success": True, "item": item_return}), 201


        # -----------------------------
        # NOTE CREATION
        # -----------------------------
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
            "created_at": datetime.utcnow()
        }

        res = locker_collection.insert_one(item)

        item_return = item.copy()
        item_return["id"] = str(res.inserted_id)

        return jsonify({"success": True, "item": item_return}), 201

    except Exception as e:
        logger.exception("Add item failed")
        return jsonify({"success": False, "error": str(e)}), 500



# -------------------------
# LIST ITEMS
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
                "created_at": r.get("created_at").isoformat()
            })

        return jsonify({"success": True, "items": items}), 200

    except Exception as e:
        logger.exception("Get items failed")
        return jsonify({"success": False, "error": str(e)}), 500



# -------------------------
# DELETE ITEM
# -------------------------
@app.route("/locker/item/<item_id>", methods=["DELETE"])
def delete_locker_item(item_id):
    try:
        doc = locker_collection.find_one({"_id": ObjectId(item_id)})
        if not doc:
            return jsonify({"success": False, "error": "Not found"}), 404

        # delete file from disk
        if doc.get("type") == "file" and doc.get("file_path"):
            filename = os.path.basename(doc["file_path"])
            path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            if os.path.exists(path):
                os.remove(path)

        locker_collection.delete_one({"_id": ObjectId(item_id)})
        return jsonify({"success": True}), 200

    except Exception as e:
        logger.exception("Delete failed")
        return jsonify({"success": False, "error": str(e)}), 500


# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info("Starting Flask app on %s", port)
    app.run(host="0.0.0.0", port=port)
