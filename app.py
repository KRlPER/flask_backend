from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from db import db
from datetime import datetime
from dotenv import load_dotenv
import os

# -----------------------------------------------------
# Load environment variables
# -----------------------------------------------------
load_dotenv()

app = Flask(__name__)
CORS(app)

# -----------------------------------------------------
# Configuration
# -----------------------------------------------------
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Allowed extensions for profile photos (images) and for locker files (images + docs)
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
ALLOWED_FILE_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS.union({"pdf", "txt", "doc", "docx", "xls", "xlsx", "ppt", "pptx"})

users_collection = db.users
locker_collection = db.locker_items  # will be created when first inserted


def allowed_image(filename):
    """Check if uploaded file has an allowed image extension"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def allowed_file(filename):
    """Check if uploaded file has an allowed general extension (locker)"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_FILE_EXTENSIONS


# -----------------------------------------------------
# REGISTER USER
# -----------------------------------------------------
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    if not all([name, email, password]):
        return jsonify({"success": False, "error": "All fields are required"}), 400

    if users_collection.find_one({"email": email}):
        return jsonify({"success": False, "error": "Email already registered"}), 400

    hashed_password = generate_password_hash(password)
    user = {
        "name": name,
        "email": email,
        "password": hashed_password,
        "photo": None,
        "created_at": datetime.utcnow()
    }
    users_collection.insert_one(user)
    return jsonify({"success": True, "message": "Registration successful!"}), 201


# -----------------------------------------------------
# LOGIN USER
# -----------------------------------------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not all([email, password]):
        return jsonify({"success": False, "error": "Email and password are required"}), 400

    user = users_collection.find_one({"email": email})
    if not user or not check_password_hash(user["password"], password):
        return jsonify({"success": False, "error": "Invalid credentials"}), 401

    return jsonify({
        "success": True,
        "message": "Login successful!",
        "user": {
            "id": str(user["_id"]),
            "name": user["name"],
            "email": user["email"],
            "photo": user.get("photo")
        }
    }), 200


# -----------------------------------------------------
# GET PROFILE INFO
# -----------------------------------------------------
@app.route("/profile/<user_id>", methods=["GET"])
def get_profile(user_id):
    try:
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404

        return jsonify({
            "success": True,
            "user": {
                "id": str(user["_id"]),
                "name": user["name"],
                "email": user["email"],
                "photo": user.get("photo")
            }
        }), 200
    except Exception:
        return jsonify({"success": False, "error": "Invalid user ID"}), 400


# -----------------------------------------------------
# UPLOAD PROFILE PHOTO
# -----------------------------------------------------
@app.route("/upload-photo/<user_id>", methods=["POST"])
def upload_photo(user_id):
    """Handles image upload for user profiles"""
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

        # Update MongoDB record with new photo path
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"photo": f"/uploads/{filename}"}}
        )

        return jsonify({
            "success": True,
            "message": "Photo uploaded successfully!",
            "photo": f"/uploads/{filename}"
        }), 200

    return jsonify({"success": False, "error": "Invalid file type"}), 400


# -----------------------------------------------------
# SERVE UPLOADED FILES
# -----------------------------------------------------
@app.route("/uploads/<filename>")
def serve_uploaded_file(filename):
    """Serves uploaded images/files"""
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# -----------------------------------------------------
# Digital Locker routes
# -----------------------------------------------------
# POST /locker/<user_id>  -> add note (JSON) or upload file (multipart)
@app.route("/locker/<user_id>", methods=["POST"])
def add_locker_item(user_id):
    try:
        # File upload (multipart/form-data)
        if request.content_type and "multipart/form-data" in request.content_type:
            if "file" not in request.files:
                return jsonify({"success": False, "error": "No file uploaded"}), 400
            file = request.files["file"]
            if file.filename == "":
                return jsonify({"success": False, "error": "No file selected"}), 400
            if not allowed_file(file.filename):
                return jsonify({"success": False, "error": "Invalid file type"}), 400

            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            # if file exists, rename to avoid collision
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(filepath):
                filename = f"{base}_{counter}{ext}"
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                counter += 1

            file.save(filepath)
            mime = file.mimetype
            title = request.form.get("title") or filename
            tags_raw = request.form.get("tags") or ""
            tags = [t.strip() for t in tags_raw.split(",")] if tags_raw else []

            item = {
                "user_id": user_id,
                "type": "file",
                "title": title,
                "file_path": f"/uploads/{filename}",
                "mime": mime,
                "tags": tags,
                "created_at": datetime.utcnow()
            }
            res = locker_collection.insert_one(item)
            item["id"] = str(res.inserted_id)
            return jsonify({"success": True, "item": item}), 201

        # JSON (note)
        data = request.get_json() or {}
        content = (data.get("content") or "").strip()
        title = data.get("title") or ""
        tags = data.get("tags", []) or []
        if not content:
            return jsonify({"success": False, "error": "content required"}), 400

        item = {
            "user_id": user_id,
            "type": "note",
            "title": title,
            "content": content,
            "tags": tags,
            "created_at": datetime.utcnow()
        }
        res = locker_collection.insert_one(item)
        item["id"] = str(res.inserted_id)
        return jsonify({"success": True, "item": item}), 201

    except Exception as e:
        print("Error in add_locker_item:", e)
        return jsonify({"success": False, "error": "internal error"}), 500


# GET /locker/<user_id> -> list items for user
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
                "created_at": r.get("created_at").isoformat() if r.get("created_at") else None
            }
            items.append(item)
        return jsonify({"success": True, "items": items}), 200
    except Exception as e:
        print("Error in get_locker_items:", e)
        return jsonify({"success": False, "error": "internal error"}), 500


# DELETE /locker/item/<item_id> -> delete item (and file if present)
@app.route("/locker/item/<item_id>", methods=["DELETE"])
def delete_locker_item(item_id):
    try:
        obj = locker_collection.find_one({"_id": ObjectId(item_id)})
        if not obj:
            return jsonify({"success": False, "error": "Not found"}), 404

        # remove file from disk if record is a file
        if obj.get("type") == "file" and obj.get("file_path"):
            filename = os.path.basename(obj.get("file_path"))
            path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                print("Warning: could not remove file:", e)

        locker_collection.delete_one({"_id": ObjectId(item_id)})
        return jsonify({"success": True}), 200
    except Exception as e:
        print("Error in delete_locker_item:", e)
        return jsonify({"success": False, "error": "invalid id"}), 400


# -----------------------------------------------------
# MAIN APP RUNNER
# -----------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
