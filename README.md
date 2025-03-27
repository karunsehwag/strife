# Strife - A Miniature Payment Gateway

## Overview
Strife is a secure and idempotent payment gateway that ensures reliable transaction processing with support for offline payments and Two-Phase Commit (2PC) protocols. This document outlines the design choices, idempotency proof, and failure handling mechanisms implemented in the system.

## 1. Design Choices for Each Requirement

### 1.1 Secure Authentication and Authorization
**Design Choices:**
- **Mutual TLS (mTLS):** Ensures secure communication between clients, the payment gateway, and banks.
- **JWT-based Authentication:** Issues session-based tokens after a user logs in.
- **Role-based Authorization:** Restricts access based on user roles:
  - View balance
  - Initiate payments
  - View transaction history (optional)
- **gRPC Interceptors:** Enforce authentication and authorization at the gateway.

**Justification:**
- **mTLS** prevents man-in-the-middle (MITM) attacks.
- **JWT** provides stateless authentication, avoiding session management overhead.

---

### 1.2 Idempotent Payments
**Design Choices:**
- **Unique Transaction IDs** generated using a scalable, timestamp-free ID generator (inspired by Snowflake IDs).
- **Persistent Transaction Logs** prevent duplicate transaction processing.
- **Replay Attack Detection** ensures duplicate transaction attempts are rejected.

**Justification:**
- Prevents double deductions by verifying whether a transaction ID already exists before processing.

**Correctness Proof:**
1. Each transaction is assigned a unique transaction ID.
2. Transactions are processed only once, even if retried due to a timeout.
3. Successful transactions are logged.

**Proof Steps:**
- If a transaction **T1** succeeds, a retry **T2** with the same ID is rejected.
- If **T1** fails and is rolled back, **T2** is processed as a fresh attempt.
- Ensures **exactly-once** execution.

---

### 1.3 Offline Payments
**Design Choices:**
- **Pending Payments Queue:** Transactions are stored in `pending_payments.json`.
- **Automatic Retry Mechanism:** Periodically resends pending payments when online.
- **Unique Transaction IDs:** Prevents duplicate processing upon reconnection.

**Failure Handling:**
1. If the client is offline, payments are **queued locally**.
2. When back online, only unprocessed transactions are retried.
3. If the payment gateway is online but the bank is down, transactions are held for retry.

---

### 1.4 Two-Phase Commit (2PC)
**Design Choices:**
- The **Payment Gateway** acts as the **coordinator**.
- **Banks (sender & receiver)** act as **participants**.
- **Prepare Phase:**
  - Sender bank verifies available funds.
  - Receiver bank checks if the account exists.
  - Both banks vote to **commit or abort**.
- **Commit Phase:**
  - If both banks vote commit, the transaction is finalized.
  - If any bank aborts, the transaction is **rolled back**.

**Failure Handling:**
1. **Handling 2PC Timeouts:**
   - If any bank **does not respond** in the prepare phase, the transaction is aborted.
   - If one bank commits but the other does not, the gateway **initiates a rollback**.
2. **Ensuring Atomicity:**
   - Transactions are **logged** to restore state after a crash.
   - If the gateway crashes before commit, banks detect the incomplete transaction and rollback.

---

## 2. How to Run

### Install Dependencies
Ensure **Python 3** is installed, then run:
```sh
pip install grpcio grpcio-tools protobuf
```

### Generate Proto Buffers
```sh
python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. payment.proto
```

### Start Bank Servers
Run each bank server in separate terminals:
```sh
python3 bank_server.py BankA 50052
python3 bank_server.py BankB 50053
python3 bank_server.py BankC 50054
```

### Start Payment Gateway
```sh
python3 payment_gateway.py
```

### Start Client
```sh
python3 client.py
```

### Use the Client Menu
- **1️⃣ Check Balance**
- **2️⃣ Make a Payment**
- **3️⃣ Retry Pending Payments**
- **4️⃣ Logout & Exit**

### Handle Offline Payments
If the payment gateway is down, payments are **queued and retried automatically** when connectivity is restored.

---



