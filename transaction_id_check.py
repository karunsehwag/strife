import os
import json

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "transactions.log")

def is_transaction_replay(transaction_id):
    """Check if the transaction ID exists in logs and was successful before."""
    if not os.path.exists(LOG_FILE):
        return False  # No logs exist yet

    with open(LOG_FILE, "r") as f:
        for line in f:
            try:
                txn = json.loads(line.strip())
                if txn["transaction_id"] == transaction_id and txn["status"].startswith("SUCCESS"):
                    return True  # Replay attack detected
            except json.JSONDecodeError:
                continue  # Skip corrupted log lines
    
    return False  # Transaction ID is not a replay
