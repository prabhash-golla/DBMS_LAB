import hashlib
from typing import List, Dict, Optional, Union, Callable
import logging
import hashlib

class ConsistentHashMap:
    """
    A consistent hash map implementation for distributing requests across servers.
    
    This implementation maintains the original polynomial hash functions while
    improving other aspects of the implementation.
    
    Attributes:
        n_slots (int): Number of slots in the hash ring
        n_virtual (int): Number of virtual nodes per server
        probing (str): Method for handling collisions ('linear' or 'quadratic')
    """
    
    def __init__(self,hostnames: Optional[List[str]] = None,n_slots: int = 512,n_virtual: int = 9,probing: str = 'linear'):
        """
        Initialize the consistent hash map.
        
        Args:
            hostnames: List of server hostnames to add initially
            n_slots: Number of slots in the hash ring
            n_virtual: Number of virtual nodes per server
            probing: Method for handling collisions ('linear' or 'quadratic')
            
        Raises:
            ValueError: If invalid parameters are provided
        """
        # Validate input parameters
        if n_slots <= 0:
            raise ValueError("Number of slots must be positive")
        if n_virtual <= 0:
            raise ValueError("Number of virtual nodes must be positive")
        if probing.lower() not in ['linear', 'quadratic']:
            raise ValueError("Probing must be either 'linear' or 'quadratic'")
            
        # Given Hash Functions
        def requestHash(i):
            return i**2 + 2*i + 17 # H(i) = i^2 + 2*i + 17

        def serverHash(i, j):
            return i**2 + j**2 + 2*j + 25 # Φ(i, j) = i^2 + j^2 + 2*j + 25


        # MD5-Based Hash Functions
        def MD5requestHash(i):
            return int(hashlib.md5(str(i).encode()).hexdigest(),16)

        def MD5serverHash(i, j):
            return int(hashlib.md5(f"{i}-{j}".encode()).hexdigest(),16)
        
        # Assign the hash functions
        self.requestHash = requestHash
        self.serverHash = serverHash
        
        # Map: server-hostname -> server-index
        self.servers: Dict[str, int] = {}
        
        # Map: server-hostname -> list of slot indices for faster removal
        self.server_slots: Dict[str, List[int]] = {}
        
        # Slots array
        self.slots: List[Optional[str]] = [None] * n_slots
        self.n_slots = n_slots
        
        # Configuration
        self.probing = probing.lower()
        self.n_virtual = n_virtual
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        
        if hostnames is None:
            hostnames = []
        
        for hostname in hostnames:
            try:
                # Populate slots
                self.add(hostname)
            except (IndexError, KeyError) as e:
                self.logger.warning(f"Failed to add server {hostname}: {e}")
    
    def getServerList(self) -> List[str]:
        """
        Return a list of all server hostnames.
        
        Returns:
            List[str]: List of server hostnames
        """
        return list(self.servers.keys())
    
    def remaining(self) -> int:
        """
        Return the maximum number of additional servers that can be added.
        
        Returns:
            int: Number of additional servers that can be added
        """
        return self.slots.count(None) // self.n_virtual
    
    def __len__(self) -> int:
        """
        Return the number of servers in the hash map.
        
        Returns:
            int: Number of servers
        """
        return len(self.servers)
    
    def probe(self, hashval: int, i: int) -> int:
        """
        Calculate the next slot to check based on the probing method.
        
        Args:
            hashval: The initial hash value
            i: The probe iteration
            
        Returns:
            int: The next slot to check
        """
        if self.probing == 'quadratic':
            return hashval + i**2
        # Default to linear probing
        return hashval + i
    
    def _get_next_server_idx(self) -> int:
        """
        Find the next available server index.
        
        Returns:
            int: The next available server index
        """
        server_idx = 0
        for value in sorted(list(self.servers.values())):
            if server_idx != value:
                break
            server_idx += 1
        return server_idx
    
    def _find_empty_slot(self, initial_hash: int) -> int:
        """
        Find an available slot starting from the initial hash value.
        
        Args:
            initial_hash: The initial hash value
            
        Returns:
            int: The index of an empty slot
            
        Raises:
            IndexError: If no empty slot can be found after a reasonable number of probes
        """
        i = 1
        idx = initial_hash % self.n_slots
        max_probes = min(self.n_slots, 1000)  # Limit probing to avoid infinite loops
        probes = 0
        
        while self.slots[idx] is not None:
            idx = self.probe(initial_hash, i) % self.n_slots
            i += 1
            probes += 1
            
            if probes >= max_probes:
                raise IndexError(f"Could not find empty slot after {max_probes} probes")
            
        return idx
    
    def add(self, hostname: str) -> None:
        """
        Add a server to the hash map.
        
        Args:
            hostname: The hostname of the server to add
            
        Raises:
            IndexError: If there are insufficient slots to add the server
            KeyError: If the hostname already exists
        """
        # Check if there are enough empty slots
        if self.slots.count(None) < self.n_virtual:
            raise IndexError(f"Insufficient slots to add new server {hostname}. Need {self.n_virtual} empty slots.")
        
        # Check if the hostname already exists

        # print(self.servers)
        if hostname in self.servers:
            raise KeyError(f"Hostname '{hostname}' already present in the hash map")
        
        # Assign a server index
        server_idx = self._get_next_server_idx()
        self.servers[hostname] = server_idx
        self.server_slots[hostname] = []
        
        # Add virtual nodes to the slots
        for virtual_idx in range(self.n_virtual):
            server_hash = self.serverHash(server_idx + 1, virtual_idx + 1)
            slot_idx = self._find_empty_slot(server_hash)
            self.slots[slot_idx] = hostname
            self.server_slots[hostname].append(slot_idx)
    
    def remove(self, hostname: str) -> None:
        """
        Remove a server from the hash map.
        
        Args:
            hostname: The hostname of the server to remove
            
        Raises:
            KeyError: If the hostname is not found
        """
        if hostname not in self.servers:
            raise KeyError(f"Hostname '{hostname}' not found in the hash map")
        
        # Get the server index
        server_idx = self.servers[hostname]
        
        # Remove the server from the dictionaries
        self.servers.pop(hostname)
        
        # Remove all virtual nodes from the slots using the stored slot indices
        for slot_idx in self.server_slots[hostname]:
            self.slots[slot_idx] = None
            
        self.server_slots.pop(hostname)
    
    def find(self, request_id: int) -> str:
        """
        Find the server to which a request should be routed.
        
        Args:
            request_id: The ID of the request
            
        Returns:
            str: The hostname of the server to route the request to
            
        Raises:
            KeyError: If no servers are available
        """
        if not self.servers:
            raise KeyError("No servers available to handle the request")
        
        request_hash = self.requestHash(request_id) % self.n_slots
        
        # Find the next available server slot
        original_hash = request_hash
        while self.slots[request_hash] is None:
            request_hash = (request_hash + 1) % self.n_slots
            
            # If we've gone all the way around the ring, raise an error
            if request_hash == original_hash:
                raise KeyError("No servers available in the hash ring")
            
        return self.slots[request_hash]
    
    def get_distribution(self) -> Dict[str, int]:
        """
        Get the distribution of slots among servers.
        
        Returns:
            Dict[str, int]: A dictionary mapping server hostnames to slot counts
        """
        distribution = {}
        for hostname in self.servers:
            distribution[hostname] = self.slots.count(hostname)
        return distribution
    
    def rebalance(self) -> None:
        """
        Rebalance the hash map by redistributing virtual nodes.
        
        This is useful after adding or removing servers to ensure a more even distribution.
        """
        # Save the current servers
        current_servers = list(self.servers.keys())
        
        # Clear the hash map
        self.slots = [None] * self.n_slots
        self.servers = {}
        self.server_slots = {}
        
        # Re-add all servers
        for hostname in current_servers:
            self.add(hostname)