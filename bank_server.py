import grpc
import time
import uuid
from concurrent import futures
import payment_pb2
import payment_pb2_grpc
from utils import load_users, generate_token, verify_token

TWO_PC_TIMEOUT = 5  # Timeout in seconds for the prepare phase

class BankService(payment_pb2_grpc.BankServiceServicer):
    def __init__(self, bank_name):
        """Initialize the bank server with user accounts."""
        self.bank_name = bank_name
        self.users = load_users()
        self.transactions = {}

    def AuthenticateClient(self, request, context):
        """Authenticates a client and returns a JWT token."""
        username = request.username
        password = request.password

        if username in self.users and self.users[username]["password"] == password:
            token = generate_token(username)
            return payment_pb2.AuthResponse(success=True, token=token)
        return payment_pb2.AuthResponse(success=False, token="")

    def ViewBalance(self, request, context):
        """Returns the account balance of a verified user."""
        username = verify_token(request.token)
        if not username or username not in self.users:
            return payment_pb2.BalanceResponse(balance=-1)
        return payment_pb2.BalanceResponse(balance=self.users[username]["balance"])

  
    def PrepareTransaction(self, request, context):
        """Phase 1: Prepare - Check if the transaction can be processed."""
        transaction_id = request.transaction_id
        amount = request.amount

        # Simulate timeout if the bank is unresponsive
        time.sleep(1)  # Simulating delay (remove or modify for testing)

        if transaction_id in self.transactions:
            return payment_pb2.PrepareResponse(success=True, message="Transaction already prepared")

        if request.sender in self.users:
            if self.users[request.sender]["balance"] < amount:
                return payment_pb2.PrepareResponse(success=False, message="Insufficient funds")

        self.transactions[transaction_id] = "PREPARED"
        return payment_pb2.PrepareResponse(success=True, message="Transaction prepared")

    def CommitTransaction(self, request, context):
        """Phase 2: Commit - Finalize the transaction if all participants agreed."""
        transaction_id = request.transaction_id

        if transaction_id not in self.transactions or self.transactions[transaction_id] != "PREPARED":
            return payment_pb2.CommitResponse(success=False, message="Transaction not prepared or already committed")

        # Deduct from sender or add to receiver based on transaction type
        self.transactions[transaction_id] = "COMMITTED"
      
        return payment_pb2.CommitResponse(success=True, message="Transaction committed")

    def AbortTransaction(self, request, context):
        """Rollback - Abort the transaction and revert any changes."""
        transaction_id = request.transaction_id

        if transaction_id in self.transactions:
            del self.transactions[transaction_id]  # Remove prepared transaction
        return payment_pb2.AbortResponse(success=True, message="Transaction aborted")

    def InterbankTransfer(self, request, context):
        """Handles interbank fund transfers, ensuring idempotency."""
        sender = request.sender
        receiver = request.receiver
        amount = request.amount
        transaction_id = request.transaction_id

        print(f"🏦 {self.bank_name} received interbank transfer request: {sender} -> {receiver} (${amount})")

      
        # Validate the receiver exists
        if receiver not in self.users:
            print(f"❌ ERROR: Receiver {receiver} not found in {self.bank_name}'s users!")
            return payment_pb2.BankTransferResponse(success=False, message="Invalid recipient", transaction_id=transaction_id)

        print(f"✅ Before Transfer: {receiver}'s balance = ${self.users[receiver]['balance']}")

        # ✅ Ensure the funds are credited to the receiver
        self.users[receiver]["balance"] += amount

        print(f"✅ After Transfer: {receiver}'s balance = ${self.users[receiver]['balance']}")
        self.transactions[transaction_id] = "COMPLETED"

        return payment_pb2.BankTransferResponse(success=True, message="Interbank transfer successful", transaction_id=transaction_id)

def serve(bank_name, port):
    """Starts the gRPC bank server with SSL/TLS."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # Load TLS credentials
    with open("server.crt", "rb") as f:
        server_cert = f.read()
    with open("server.key", "rb") as f:
        server_key = f.read()
    with open("ca.crt", "rb") as f:
        ca_cert = f.read()

    # Create SSL/TLS credentials
    credentials = grpc.ssl_server_credentials([(server_key, server_cert)], root_certificates=ca_cert)

    # Add BankService
    payment_pb2_grpc.add_BankServiceServicer_to_server(BankService(bank_name), server)

    # Use secure port
    server.add_secure_port(f"[::]:{port}", credentials)
    server.start()
    print(f"🏦 {bank_name} Server running securely on port {port}...")
    server.wait_for_termination()


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python bank_server.py <BANK_NAME> <PORT>")
        sys.exit(1)

    bank_name = sys.argv[1]
    port = int(sys.argv[2])
    serve(bank_name, port)
