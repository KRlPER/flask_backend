from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from db import db
from datetime import datetime
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# -----------------------------
# Configuration
# -----------------------------
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

users_collection = db.users


def allowed_file(filename):
    """Check if uploaded file has an allowed extension"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# -----------------------------
# REGISTER USER
# -----------------------------
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


# -----------------------------
# LOGIN USER
# -----------------------------
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


# -----------------------------
# GET PROFILE INFO
# -----------------------------
@app.route("/profile/<user_id>", methods=["GET"])
def get_profile(user_id):
    try:
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"error": "User not found"}), 404

        return jsonify({
            "id": str(user["_id"]),
            "name": user["name"],
            "email": user["email"],
            "photo": user.get("photo")
        }), 200
    except Exception:
        return jsonify({"error": "Invalid user ID"}), 400


# -----------------------------
# UPLOAD PROFILE PHOTO
# -----------------------------
@app.route("/upload-photo/<user_id>", methods=["POST"])
def upload_photo(user_id):
    """Handles image upload for user profiles"""
    if "photo" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["photo"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        # Store relative path in MongoDB
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"photo": f"/uploads/{filename}"}}
        )

        return jsonify({
            "message": "Photo uploaded successfully!",
            "photo": f"/uploads/{filename}"
        }), 200

    return jsonify({"error": "Invalid file type"}), 400


# -----------------------------
# SERVE UPLOADED FILES
# -----------------------------
@app.route("/uploads/<filename>")
def serve_uploaded_file(filename):
    """Serves uploaded images"""
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# -----------------------------
# MAIN APP RUNNER
# -----------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
