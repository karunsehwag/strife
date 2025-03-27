import grpc
import json
import os
import time
import payment_pb2
import payment_pb2_grpc
from google.protobuf import empty_pb2  # ✅ Import Empty from protobuf
import threading
from pending_payments import save_pending_payment, get_user_pending_payments, remove_successful_payments

# ✅ Secure gRPC connection
def get_secure_stub():
    """Creates a secure gRPC client connection with SSL/TLS."""
    with open("ca.crt", "rb") as f:
        ca_cert = f.read()
    credentials = grpc.ssl_channel_credentials(root_certificates=ca_cert)
    channel = grpc.secure_channel("localhost:50051", credentials)
    return payment_pb2_grpc.PaymentGatewayStub(channel)

# ✅ Generate a new transaction ID
def generate_transaction_id(stub):
    """Requests a new transaction ID from the server."""
    try:
        response = stub.GenerateTransactionID(empty_pb2.Empty())  
        return response.transaction_id
    except grpc.RpcError as e:
        print(f"❌ Failed to generate Transaction ID: {e.details()}")
        return None

# ✅ Retry pending payments for a specific user
def retry_pending_payments(stub, token, username):
    """Retries only the logged-in user's pending payments."""
    pending_payments = get_user_pending_payments(username)
    
    if not pending_payments:
        print(f"✅ No pending payments for {username}.")
        return

    print(f"🔄 Retrying {len(pending_payments)} pending payments for {username}...")

    successful_transactions = set()  

    for payment_data in pending_payments:
        transaction_id = payment_data.get("transaction_id")

        if not transaction_id:
            print(f"⚠️ Missing transaction_id for payment to {payment_data['receiver']}. Generating new one.")
            transaction_id = generate_transaction_id(stub)
            if not transaction_id:
                print("❌ Could not generate transaction ID. Skipping this payment.")
                continue
            payment_data["transaction_id"] = transaction_id

        try:
            payment_response = stub.ProcessPayment(payment_pb2.PaymentRequest(
                sender=token,
                receiver=payment_data["receiver"],
                amount=payment_data["amount"],
                transaction_id=transaction_id
            ))

            if payment_response.success:
                print(f"✅ Payment Successful! (Transaction ID: {payment_response.transaction_id})")
                successful_transactions.add(transaction_id)

            else:
                print(f"❌ Payment Failed: {payment_response.message}")

        except grpc.RpcError as e:
            print(f"❌ gRPC Error: {e.details()}")

    # ✅ Remove successfully processed transactions
    remove_successful_payments(username, successful_transactions)
    print("✅ Pending payments retry complete.")

# ✅ Check balance before processing payment
def check_balance(stub, token):
    """Fetches and displays account balance using a valid authentication token."""
    try:
        balance_response = stub.ViewBalance(payment_pb2.BalanceRequest(token=token))
        if balance_response.balance == -1:
            print("❌ Authentication failed.")
            return None
        else:
            print(f"💵 Your Current Balance: ${balance_response.balance:.2f}")
            return balance_response.balance
    except grpc.RpcError as e:
        print(f"❌ gRPC Error: {e.details()}")
        return None

# ✅ Process a payment and queue failed transactions
def process_payment(stub, token, username):
    """Handles user payments securely with balance checks and offline queuing."""
    receiver = input("Enter Receiver's Username: ").strip()
    amount = input("Enter Amount: ").strip()

    try:
        amount = float(amount)
        if amount <= 0:
            print("❌ Amount must be greater than zero.")
            return
    except ValueError:
        print("❌ Invalid amount! Please enter a valid number.")
        return


    # ✅ Generate a unique transaction ID
    transaction_id = generate_transaction_id(stub)
    if not transaction_id:
        print("❌ Could not generate a Transaction ID. Saving for retry.")
        save_pending_payment(username, {"receiver": receiver, "amount": amount, "transaction_id": None})
        return
    
    # ✅ Check user balance before proceeding
    balance = check_balance(stub, token)
    if balance is None or balance < amount:
        print("❌ Error: Insufficient funds. Transaction aborted.")
        return

    print(f"🔍 Debug: Sending payment request with Token → {token}")
    print(f"🔄 Generated Transaction ID: {transaction_id}")

    try:
        # ✅ Call the Payment Gateway
        payment_response = stub.ProcessPayment(payment_pb2.PaymentRequest(
            sender=token,
            receiver=receiver,
            amount=amount,
            transaction_id=transaction_id
        ))

        if payment_response.success:
            print(f"✅ Payment Successful! (Transaction ID: {payment_response.transaction_id})")
        else:
            print(f"❌ Payment Failed: {payment_response.message}")
            save_pending_payment(username, {"receiver": receiver, "amount": amount, "transaction_id": transaction_id})  # ✅ Secure retry queue

    except grpc.RpcError as e:
        print(f"❌ gRPC Error: {e.details()}")
        save_pending_payment(username, {"receiver": receiver, "amount": amount, "transaction_id": transaction_id})  # ✅ Secure retry queue

# ✅ User Authentication
def authenticate_client(stub):
    """Handles user login and returns an authentication token."""
    while True:
        username = input("Enter Username: ").strip()
        password = input("Enter Password: ").strip()

        try:
            auth_response = stub.AuthenticateClient(payment_pb2.UserCredentials(
                username=username, 
                password=password
            ))

            if auth_response.success:
                print(f"✅ Authenticated Successfully! Token: {auth_response.token}")
                return auth_response.token, username
            else:
                print("❌ Authentication failed.")

        except grpc.RpcError as e:
            print(f"❌ gRPC Error: {e.details()}")

        if input("Retry? (yes/no): ").strip().lower() != "yes":
            return None, None  

# ✅ Background thread for auto-retrying failed transactions
def auto_retry_loop(stub, token, username):
    """Retries pending payments every 60 seconds in a background thread."""
    while True:
        retry_pending_payments(stub, token, username) 
        time.sleep(60)

# ✅ Start the client
def main():
    stub = get_secure_stub()

    token, username = authenticate_client(stub)
    if not token:
        print("❌ Exiting due to authentication failure.")
        return

    # ✅ Start auto-retry loop
    retry_thread = threading.Thread(target=auto_retry_loop, args=(stub, token, username), daemon=True)
    retry_thread.start()

    # ✅ Check and retry payments immediately on login
    retry_pending_payments(stub, token, username)

    while True:
        print("\n📌 Main Menu:")
        print("1️⃣ Check Balance")
        print("2️⃣ Make a Payment")
        print("3️⃣ Retry Pending Payments")
        print("4️⃣ Logout & Exit")

        user_choice = input("Enter your choice (1-4): ").strip()

        if user_choice == "1":
            check_balance(stub, token)
        elif user_choice == "2":
            process_payment(stub, token, username)  # ✅ Pass username
        elif user_choice == "3":
            retry_pending_payments(stub, token, username) 
        elif user_choice == "4":
            print("👋 Logging out... Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please enter 1, 2, 3, or 4.")

if __name__ == "__main__":
    main()
