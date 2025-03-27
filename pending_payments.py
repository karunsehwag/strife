import os
import json

PENDING_PAYMENTS_FILE = "pending_payments.json"

def load_pending_payments():
    """Loads pending payments from file, returning a dict of {username: [transactions]}."""
    if not os.path.exists(PENDING_PAYMENTS_FILE):
        with open(PENDING_PAYMENTS_FILE, "w") as f:
            json.dump({}, f)  # ✅ Store transactions per user
    try:
        with open(PENDING_PAYMENTS_FILE, "r") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}  # ✅ Ensure data is a dictionary
    except json.JSONDecodeError:
        return {}  # If file is corrupted, reset it

def save_pending_payments(pending_payments):
    """Saves pending transactions to the file."""
    with open(PENDING_PAYMENTS_FILE, "w") as f:
        json.dump(pending_payments, f, indent=4)

def save_pending_payment(username, payment_data):
    """Save a pending payment under the specific username."""
    pending_payments = load_pending_payments()

    if username not in pending_payments:
        pending_payments[username] = []  # ✅ Ensure user has a queue

    pending_payments[username].append(payment_data)
    save_pending_payments(pending_payments)

def get_user_pending_payments(username):
    """Returns the pending payments for a specific user."""
    pending_payments = load_pending_payments()
    return pending_payments.get(username, [])  


def remove_successful_payments(username, successful_transactions):
    """Removes successfully processed transactions and transactions with `null` IDs for a specific user."""
    pending_payments = load_pending_payments()
    
    if username in pending_payments:
        # ✅ Remove transactions that were successfully processed OR have `null` transaction IDs
        pending_payments[username] = [
            p for p in pending_payments[username] if p["transaction_id"] not in successful_transactions and p["transaction_id"] is not None
        ]

        # ✅ If the user has no more pending transactions, remove their entry
        if not pending_payments[username]:
            del pending_payments[username]

    save_pending_payments(pending_payments)
    print(f"✅ Cleaned up {len(successful_transactions)} successful transactions and removed `null` IDs for {username}.")