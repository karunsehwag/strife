import json
import jwt
import logging
import os
from datetime import datetime, timedelta
import uuid

# Load SECRET_KEY from environment or use a fallback (Avoid hardcoding in production)
SECRET_KEY = os.getenv("SECRET_KEY", "fallback_secret_key")

# Directory and file paths
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "transactions.log")
USER_DATA_FILE = "data.json"

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Configure logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s | %(message)s")

def load_users():
    """Load user data from JSON file safely and ensure all users have a bank_name."""
    try:
        with open(USER_DATA_FILE, "r") as file:
            users = json.load(file)

        # Ensure all users have a bank_name
        for username, data in users.items():
            if "bank_name" not in data or not data["bank_name"]:
                data["bank_name"] = "UnknownBank"  # Assign a default bank name
            
        return users
    except (FileNotFoundError, json.JSONDecodeError):
        return {}  # Return an empty dictionary if file doesn't exist or has errors

def save_users(data):
    """Save user data to JSON file safely with error handling."""
    try:
        with open(USER_DATA_FILE, "w") as file:
            json.dump(data, file, indent=4)
    except Exception as e:
        logging.error(f"❌ Failed to save users: {e}")

def generate_token(username):
    """Generate a JWT token for authentication."""
    payload = {
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=1)  # Token expires in 1 hour
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token):
    """Verify JWT token and return username if valid."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload["username"]
    except jwt.ExpiredSignatureError:
        logging.warning("⚠️ Token expired! Please log in again.")
        return None
    except jwt.InvalidTokenError:
        logging.warning("⚠️ Invalid token! Authentication failed.")
        return None

import socket  # ✅ Import for getting IP

def log_transaction(username, transaction_type, amount, status, transaction_id=None, receiver=None, sender_bank=None, receiver_bank=None):
    """Logs transaction details including sender IP and receiver."""
    
    # Get sender's IP Address
    sender_ip = socket.gethostbyname(socket.gethostname())  # ✅ Gets machine's local IP
    
    # Ensure transaction_id is valid
    transaction_id = transaction_id or str(uuid.uuid4())

    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "transaction_id": transaction_id,
        "username": username,  # ✅ Sender
        "receiver": receiver,  # ✅ Receiver (new)
        "sender_ip": sender_ip,  # ✅ Sender's IP (new)
        "transaction_type": transaction_type,
        "amount": amount,
        "status": status,
        "sender_bank": sender_bank if sender_bank else "N/A",
        "receiver_bank": receiver_bank if receiver_bank else "N/A",
    }

    try:
        with open(LOG_FILE, "a") as file:
            file.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        logging.error(f"❌ Failed to write to log file: {e}")

    # Print log to console for debugging
    print(json.dumps(log_entry, indent=4))  # ✅ Pretty print log
