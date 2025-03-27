import grpc
import time
import uuid
import random
from concurrent import futures
import payment_pb2
import payment_pb2_grpc
from utils import load_users, save_users, generate_token, verify_token, log_transaction
from google.protobuf import empty_pb2  # ✅ Import Empty
import socket  # ✅ Import socket to get sender's IP address
from transaction_id_generator import TransactionIDGenerator  # ✅ Import the generator
from transaction_id_check import is_transaction_replay

TRANSACTION_TIMEOUT = 5
# Define known banks and their gRPC addresses
BANKS = {
    "BankA": "localhost:50052",
    "BankB": "localhost:50053",
    "BankC": "localhost:50054",
    "BankD": "localhost:50055",
    "BankE": "localhost:50056",
    "BankF": "localhost:50057",
    "BankG": "localhost:50058",
    "BankH": "localhost:50059"
}

# Track online banks (Assume all banks are online at startup)
ONLINE_BANKS = set(BANKS.keys())

def generate_account_number(existing_accounts):
    """Generates a unique 10-digit account number."""
    while True:
        account_no = str(random.randint(10**9, 10**10 - 1))
        if account_no not in existing_accounts:
            return account_no

class PaymentGatewayServicer(payment_pb2_grpc.PaymentGatewayServicer):
    def __init__(self):
        self.users = load_users()
        self.transactions = {}  # Track completed transactions to prevent duplicates
        self.transaction_id_generator = TransactionIDGenerator(datacenter_id=1, machine_id=1)  # ✅ Initialize generator

    
    def AuthenticateClient(self, request, context):
        """Authenticates a client and returns a JWT token if the user's bank is online."""
        user = self.users.get(request.username)

        if not user or user["password"] != request.password:
            return payment_pb2.AuthResponse(success=False, token="Invalid credentials")

        user_bank = user["bank_name"]

        # 🚫 Reject authentication if the user's bank is offline
        if user_bank not in ONLINE_BANKS:
            print(f"🚫 Login blocked: {request.username} (Bank: {user_bank} is OFFLINE)")
            return payment_pb2.AuthResponse(success=False, token="Bank is offline")

        print(f"✅ Login successful: {request.username} (Bank: {user_bank} is ONLINE)")
        token = generate_token(request.username)
        return payment_pb2.AuthResponse(success=True, token=token)

    def GenerateTransactionID(self, request, context):
        """Generates a globally unique transaction ID."""
        transaction_id = self.transaction_id_generator.generate_transaction_id()
        return payment_pb2.TransactionResponse(transaction_id=str(transaction_id))  # ✅ Ensure ID is string


    def ProcessPayment(self, request, context):
        """Processes a payment from sender to receiver, ensuring idempotency."""
        sender = verify_token(request.sender)
        receiver = request.receiver
        amount = request.amount
        transaction_id = request.transaction_id or str(uuid.uuid4())  # ✅ Generate if empty

        # ✅ Check if the transaction has already been processed
        # ✅ Check if the transaction has already been processed (cached response)
        if transaction_id in self.transactions:
            log_transaction(sender, "transfer", amount, "FAILED: Duplicate Transaction", transaction_id,
                            receiver=receiver, sender_bank=self.users[sender]["bank_name"] if sender in self.users else "UNKNOWN",
                            receiver_bank=self.users[receiver]["bank_name"] if receiver in self.users else "UNKNOWN")

            print(f"🔁 Duplicate transaction detected: {transaction_id}. Returning cached response.")
            return payment_pb2.PaymentResponse(
                success=True,
                message="DUPLICATE TRANSACTION - This payment has already been processed.",
                transaction_id=transaction_id,
                receiver=receiver
            )

        # 🚨 Check for replay attacks
        if is_transaction_replay(transaction_id):
            log_transaction(sender, "transfer", amount, "FAILED: Replay Attack Detected", transaction_id,
                            receiver=receiver, sender_bank=self.users[sender]["bank_name"] if sender in self.users else "UNKNOWN",
                            receiver_bank=self.users[receiver]["bank_name"] if receiver in self.users else "UNKNOWN")

            print(f"⚠️ Replay Attack Detected: Transaction ID {transaction_id} already processed successfully.")
            return payment_pb2.PaymentResponse(success=False, message="Duplicate transaction detected!", transaction_id=transaction_id)

        if not sender:
            log_transaction("UNKNOWN", "transfer", amount, "FAILED: Invalid Token", transaction_id, 
                            receiver=receiver)
            return payment_pb2.PaymentResponse(success=False, message="Invalid or expired token",
                                            transaction_id=transaction_id, receiver=receiver)

        if sender not in self.users or receiver not in self.users:
            log_transaction(sender, "transfer", amount, "FAILED: Invalid Account", transaction_id,
                            receiver=receiver)
            return payment_pb2.PaymentResponse(success=False, message="Invalid account(s)",
                                            transaction_id=transaction_id, receiver=receiver)

        sender_bank = self.users[sender]["bank_name"]
        receiver_bank = self.users[receiver]["bank_name"]
        # ✅ Ensure the sender has enough balance
        if self.users[sender]["balance"] < amount:
            log_transaction(sender, "transfer", amount, "FAILED: Insufficient Funds", transaction_id, receiver=receiver, sender_bank=sender_bank, receiver_bank=receiver_bank)
            return payment_pb2.PaymentResponse(success=False, message="Insufficient funds", transaction_id=transaction_id, receiver=receiver, sender_bank=sender_bank, receiver_bank=receiver_bank)

        # ✅ Ensure the receiver's bank is online
        if receiver_bank not in ONLINE_BANKS:
            log_transaction(sender, "transfer", amount, f"FAILED: {receiver_bank} is offline", transaction_id,
                            receiver=receiver, sender_bank=sender_bank, receiver_bank=receiver_bank)
            return payment_pb2.PaymentResponse(success=False, message=f"{receiver_bank} is offline",
                                            transaction_id=transaction_id, receiver=receiver, 
                                            sender_bank=sender_bank, receiver_bank=receiver_bank)

        if receiver_bank not in BANKS:
            log_transaction(sender, "transfer", amount, "FAILED: Unknown Bank", transaction_id,
                            receiver=receiver, sender_bank=sender_bank)
            return payment_pb2.PaymentResponse(success=False, message="Unknown bank",
                                            transaction_id=transaction_id, receiver=receiver, 
                                            sender_bank=sender_bank, receiver_bank=receiver_bank)

        receiver_bank_address = BANKS[receiver_bank]

        # ✅ Load CA certificate for SSL verification
        with open("ca.crt", "rb") as f:
            ca_cert = f.read()

        credentials = grpc.ssl_channel_credentials(root_certificates=ca_cert)

        print(f"🔍 Debug: Connecting to {receiver_bank_address}")

        try:
            with grpc.secure_channel(receiver_bank_address, credentials) as channel:
                stub = payment_pb2_grpc.BankServiceStub(channel)

                # **🔹 PHASE 1: PREPARE PHASE**
                print("⏳ Phase 1: Sending Prepare Request...")
                prepare_response = stub.PrepareTransaction(
                    payment_pb2.PrepareRequest(transaction_id=transaction_id, sender=sender, receiver=receiver, amount=amount)
                )

                if not prepare_response.success:
                    log_transaction(sender, "interbank_transfer", amount, "FAILED: Prepare phase failed", transaction_id,
                                    receiver=receiver, sender_bank=sender_bank, receiver_bank=receiver_bank)
                    
                    return payment_pb2.PaymentResponse(
                        success=False,
                        message="Prepare phase failed",
                        transaction_id=transaction_id
                    )

                # **🔹 PHASE 2: COMMIT PHASE**
                print("✅ Phase 2: Committing Transaction...")
                commit_response = stub.CommitTransaction(
                    payment_pb2.CommitRequest(transaction_id=transaction_id)
                )

                if commit_response.success:
                    self.users[sender]["balance"] -= amount
                    
           
                    # ✅ Ensure funds are credited to the receiver
                    interbank_response = stub.InterbankTransfer(
                        payment_pb2.BankTransferRequest(sender=sender, receiver=receiver, amount=amount, transaction_id=transaction_id)
                    )

                    if not interbank_response.success:
                        print(f"❌ Interbank Transfer Failed: {interbank_response.message}")
                        log_transaction(sender, "interbank_transfer", amount, "FAILED: Receiver Bank Issue", transaction_id, receiver=receiver)
                        return payment_pb2.PaymentResponse(success=False, message="Interbank transfer failed", transaction_id=transaction_id)
                    
                    self.users[receiver]["balance"] += amount
                    save_users(self.users)

                    transaction_type = "interbank_transfer" if sender_bank != receiver_bank else "transfer"

                    log_transaction(sender, transaction_type, amount, "SUCCESS", transaction_id,
                                    receiver=receiver, sender_bank=sender_bank, receiver_bank=receiver_bank)

                    print(f"✅ Payment of ${amount} to {receiver} successful!")
                    payment_response = payment_pb2.PaymentResponse(success=True, message="Payment successful", transaction_id=transaction_id, receiver=receiver, sender_bank=sender_bank, receiver_bank=receiver_bank)
                    self.transactions[transaction_id] = payment_response
                    return payment_response
                
                log_transaction(sender, "interbank_transfer", amount, "FAILED: Commit phase failed", transaction_id,
                receiver=receiver, sender_bank=sender_bank, receiver_bank=receiver_bank)

                return payment_pb2.PaymentResponse(success=False, message="Commit phase failed", transaction_id=transaction_id)

        except grpc.RpcError as e:
            error_message = f"Timeout in transaction: {e.details()}"
            log_transaction(sender, "interbank_transfer", amount, "FAILED: Timeout in transaction", transaction_id,
                            receiver=receiver, sender_bank=sender_bank, receiver_bank=receiver_bank)

            return payment_pb2.PaymentResponse(success=False, message=error_message, transaction_id=transaction_id)


    def ViewBalance(self, request, context):
        """Retrieves account balance using token authentication."""
        user = verify_token(request.token)
        if not user or user not in self.users:
            return payment_pb2.BalanceResponse(balance=-1)
        return payment_pb2.BalanceResponse(balance=self.users[user]["balance"])

    def CheckBankStatus(self, request, context):
        """Checks if a bank is online."""
        bank_name = request.bank_name
        return payment_pb2.BankStatusResponse(online=bank_name in ONLINE_BANKS)

    def UpdateBankStatus(self, request, context):
        """Updates the bank's online/offline status."""
        bank_name = request.bank_name
        if request.online:
            ONLINE_BANKS.add(bank_name)
        else:
            ONLINE_BANKS.discard(bank_name)
        return payment_pb2.StatusResponse(success=True, message="Bank status updated")
    def prepare_transaction(self, bank_name, user, amount, transaction_id, stub=None):
        """Sends a prepare request to a bank and waits for a response."""
        if bank_name == self.users[user]["bank_name"]:  # If sender's bank is local
            print(f"🔹 {bank_name}: Approved transaction.")
            return True

        try:
            print(f"🔹 Sending Prepare request to {bank_name} for {amount}...")
            response = stub.PrepareTransaction(payment_pb2.PrepareRequest(transaction_id=transaction_id, amount=amount))
            return response.success
        except grpc.RpcError as e:
            print(f"❌ {bank_name}: PREPARE FAILED! ({e.details()})")
            return False

def abort_transaction(self, bank_name, user, amount, transaction_id):
    """Handles rollback for a failed 2PC transaction."""
    if user in self.users:
        self.users[user]["balance"] += amount  # Refund sender if rollback needed
        save_users(self.users)
        print(f"🔄 {bank_name}: Rolled back {amount} due to failed transaction {transaction_id}.")

def serve():
    """Starts the gRPC payment gateway server with SSL/TLS."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # Load TLS credentials (Server Certificate, Private Key, CA Certificate)
    with open("server.crt", "rb") as f:
        server_cert = f.read()
    with open("server.key", "rb") as f:
        server_key = f.read()
    with open("ca.crt", "rb") as f:
        ca_cert = f.read()

    # ✅ Ensure root_certificates is included
    credentials = grpc.ssl_server_credentials([(server_key, server_cert)], root_certificates=ca_cert)

    # Add PaymentGateway service
    payment_pb2_grpc.add_PaymentGatewayServicer_to_server(PaymentGatewayServicer(), server)

    # Secure gRPC server with TLS
    server.add_secure_port("[::]:50051", credentials)
    server.start()
    print("🚀 Payment Gateway Server running securely on port 50051...")
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
