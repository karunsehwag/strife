import time
import threading

class TransactionIDGenerator:
    """A scalable unique Transaction ID generator (Inspired by Twitter Snowflake)."""
    
    # Constants (Bit allocations)
    EPOCH = 1640995200000  # Custom epoch (e.g., 2022-01-01 00:00:00 UTC)
    DATACENTER_BITS = 5
    MACHINE_BITS = 5
    SEQUENCE_BITS = 12

    MAX_DATACENTER_ID = (1 << DATACENTER_BITS) - 1
    MAX_MACHINE_ID = (1 << MACHINE_BITS) - 1
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1

    def __init__(self, datacenter_id: int, machine_id: int):
        """Initialize with Datacenter ID & Machine ID."""
        if datacenter_id > self.MAX_DATACENTER_ID or datacenter_id < 0:
            raise ValueError(f"Datacenter ID must be between 0 and {self.MAX_DATACENTER_ID}")
        if machine_id > self.MAX_MACHINE_ID or machine_id < 0:
            raise ValueError(f"Machine ID must be between 0 and {self.MAX_MACHINE_ID}")
        
        self.datacenter_id = datacenter_id
        self.machine_id = machine_id
        self.last_timestamp = -1
        self.sequence = 0
        self.lock = threading.Lock()  # Ensure thread safety

    def _current_millis(self) -> int:
        """Returns current timestamp in milliseconds."""
        return int(time.time() * 1000)

    def _wait_for_next_millis(self, last_timestamp: int) -> int:
        """Waits for the next millisecond if needed."""
        timestamp = self._current_millis()
        while timestamp <= last_timestamp:
            timestamp = self._current_millis()
        return timestamp

    def generate_transaction_id(self) -> int:
        """Generates a unique transaction ID."""
        with self.lock:
            timestamp = self._current_millis()

            # Ensure unique timestamp
            if timestamp < self.last_timestamp:
                raise Exception("Clock moved backwards. Refusing to generate ID.")

            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.MAX_SEQUENCE
                if self.sequence == 0:
                    timestamp = self._wait_for_next_millis(self.last_timestamp)
            else:
                self.sequence = 0  # Reset sequence if timestamp is new

            self.last_timestamp = timestamp

            # Construct 64-bit ID
            transaction_id = ((timestamp - self.EPOCH) << (self.DATACENTER_BITS + self.MACHINE_BITS + self.SEQUENCE_BITS)) | \
                             (self.datacenter_id << (self.MACHINE_BITS + self.SEQUENCE_BITS)) | \
                             (self.machine_id << self.SEQUENCE_BITS) | \
                             self.sequence
            return transaction_id
