import aiohttp
import asyncio
import os
import random
import sys
import time
from aiodocker import Docker
from icecream import ic
from quart import Quart, request, jsonify
from colorama import Fore, Style
from ConsistentHashing import ConsistentHashMap
from asyncio import Lock

app = Quart(__name__)
mutexLock = Lock()  # Mutex for thread-safe operations on shared data

# Configuration parameters
HASH_NUM = int(os.environ.get('HASH_NUM', 0))
DEBUG = False
ic.configureOutput(prefix='[LB] | ')  # Configure icecream debugging output
ic.disable()  # Disable icecream debugging by default

# Global variables
Servers = ConsistentHashMap()  # Consistent hash map for server selection
heartbeat_fail_count: dict[str, int] = {}  # Track failed heartbeats for each server
serv_id = 3  # Server ID counter (starts at 3)

# Constants
MAX_FAIL_COUNT = 5  # Maximum number of heartbeat failures before server is considered down
HEARTBEAT_INTERVAL = 10  # Seconds between heartbeat checks
STOP_TIMEOUT = 5  # Timeout for stopping containers
REQUEST_TIMEOUT = 1  # Timeout for client requests
REQUEST_BATCH_SIZE = 10  # Number of concurrent requests to process
DOCKER_TASK_BATCH_SIZE = 10  # Number of concurrent Docker operations

def err_payload(err: Exception):
    """Create standardized error response payload"""
    return {
        'message': f'<Error> {err}',
        'status': 'failure'
    }

async def gather_with_concurrency(
    session: aiohttp.ClientSession,
    batch: int,
    *urls: str
):
    """Execute HTTP requests with limited concurrency
    
    Args:
        session: aiohttp session to use for requests
        batch: maximum number of concurrent requests
        urls: list of URLs to request
        
    Returns:
        List of responses or None for failed requests
    """
    await asyncio.sleep(0)  # Yield to event loop
    semaphore = asyncio.Semaphore(batch)
    
    async def fetch(url: str):
        await asyncio.sleep(0)  # Yield to event loop
        async with semaphore:  # Limit concurrent requests
            async with session.get(url) as response:
                await response.read()  # Ensure response body is read
                return response
    
    tasks = [fetch(url) for url in urls]
    return [None if isinstance(r, BaseException)
            else r for r in
            await asyncio.gather(*tasks, return_exceptions=True)]

# API Endpoints

@app.route('/rep', methods=['GET'])
async def rep():
    """Report the current state of the server cluster"""
    global Servers
    async with mutexLock:  # Ensure thread-safe access to Servers
        return jsonify(ic({
            'message': {
                'N': len(Servers),  # Number of servers
                'Servers': Servers.getServerList(),  # List of server hostnames
            },
            'status': 'successful',
        })), 200

@app.route('/add', methods=['POST'])
async def add():
    """Add new server instances to the cluster"""
    global Servers, heartbeat_fail_count, serv_id
    await asyncio.sleep(0)  # Yield to event loop
    try:
        # Parse request payload
        payload: dict = await request.get_json()
        ic(payload)  # Log payload for debugging
        if payload is None:
            raise Exception('Payload is empty')
            
        # Extract parameters
        n = int(payload.get('n', -1))  # Number of servers to add
        hostnames: list[str] = list(payload.get('hostnames', []))  # Optional predefined hostnames
        
        # Validate parameters
        if n <= 0:
            raise Exception('Number of servers to add must be greater than 0')
        if len(hostnames) > n:
            raise Exception('Length of hostname list is more than instances to add')
        if len(hostnames) != len(set(hostnames)):
            raise Exception('Hostname list contains duplicates')
            
        # Generate random hostnames if needed
        new_hostnames = set()
        while len(new_hostnames) < n - len(hostnames):
            new_hostnames.add(f'Server-{random.randrange(0, 1000):03}-{int(time.time()*1e3) % 1000:03}')
        hostnames.extend(new_hostnames)
        
        async with mutexLock:  # Ensure thread-safe access to shared data
            # Check if we have enough capacity
            if n > Servers.remaining():
                raise Exception(f'Insufficient slots. Only {Servers.remaining()} slots left')
            # Check for hostname collisions
            if not set(hostnames).isdisjoint(set(Servers.getServerList())):
                raise Exception(f'Hostnames {set(hostnames) & set(Servers.getServerList())} are already in Servers')
                
            ic("To add: ", hostnames)
            semaphore = asyncio.Semaphore(DOCKER_TASK_BATCH_SIZE)  # Limit concurrent Docker operations
            
            async def spawn_container(docker: Docker, serv_id: int, hostname: str):
                """Create and start a new Docker container for a server instance"""
                await asyncio.sleep(0)  # Yield to event loop
                async with semaphore:  # Limit concurrent Docker operations
                    try:
                        # Configure container
                        container_config = {
                            'image': 'server:v1',  # Docker image to use
                            'detach': True,  # Run in background
                            'env': [f'SERVER_ID={serv_id}', 'DEBUG=true'],  # Environment variables
                            'hostname': hostname,  # Container hostname
                            'tty': True,  # Allocate a terminal
                        }
                        # Create or replace container
                        container = await docker.containers.create_or_replace(
                            name=hostname,
                            config=container_config,
                        )
                        # Connect to network
                        LB = await docker.networks.get('LB')
                        await LB.connect({'Container': container.id, 'EndpointConfig': {'Aliases': [hostname]}})
                        
                        if DEBUG:
                            print(f'{Fore.LIGHTGREEN_EX}CREATE | Created container for {hostname}{Style.RESET_ALL}', file=sys.stderr)
                        
                        # Start container
                        await container.start()
                        
                        if DEBUG:
                            print(f'{Fore.MAGENTA}SPAWN | Started container for {hostname}{Style.RESET_ALL}', file=sys.stderr)
                    except Exception as e:
                        if DEBUG:
                            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)
                            
            async with Docker() as docker:  # Docker client context
                tasks = []
                for hostname in hostnames:
                    # Add server to hash map
                    Servers.add(hostname)
                    # Initialize heartbeat counter
                    heartbeat_fail_count[hostname] = 0
                    # Increment server ID
                    serv_id += 1
                    # Schedule container creation
                    tasks.append(spawn_container(docker, serv_id, hostname))
                    print(f"Added {hostname} to hash map. Current servers: {Servers.getServerList()}")
                    print(f"Server slots for {hostname}: {Servers.server_slots[hostname]}")
                    
                # Wait for all containers to be created
                await asyncio.gather(*tasks, return_exceptions=True)
                
            # Get final list of servers
            final_hostnames = Servers.getServerList()
            
        # Return success response
        return jsonify(ic({
            'message': {
                'N': len(Servers),
                'Servers': final_hostnames
            },
            'status': 'success'
        })), 200
    except Exception as e:
        if DEBUG:
            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)
        return jsonify(ic(err_payload(e))), 400

@app.route('/rm', methods=['DELETE'])
async def delete():
    """Remove server instances from the cluster"""
    global Servers, heartbeat_fail_count
    await asyncio.sleep(0)  # Yield to event loop
    try:
        # Parse request payload
        payload: dict = await request.get_json()
        ic(payload)  # Log payload for debugging
        if payload is None:
            raise Exception('Payload is empty')
            
        # Extract parameters
        n = int(payload.get('n', -1))  # Number of servers to remove
        hostnames: list[str] = list(payload.get('hostnames', []))  # Optional specific hostnames to remove
        
        # Validate parameters
        if n <= 0:
            raise Exception('Number of servers to delete must be greater than 0')
        if n > len(Servers):
            raise Exception('Number of servers to delete must be less than or equal to number of Servers')
        if len(hostnames) > n:
            raise Exception('Length of hostname list is more than instances to delete')
            
        async with mutexLock:  # Ensure thread-safe access to shared data
            # Check if specified hostnames exist
            choices = set(Servers.getServerList())
            if not set(hostnames).issubset(choices):
                raise Exception(f'Hostnames {set(hostnames) - choices} are not in Servers')
                
            # Select random servers to remove if needed
            choices = list(choices - set(hostnames))
            random_hostnames = random.sample(choices, k=n - len(hostnames))
            hostnames.extend(random_hostnames)
            
            ic("To delete: ", hostnames)
            semaphore = asyncio.Semaphore(DOCKER_TASK_BATCH_SIZE)  # Limit concurrent Docker operations
            
            async def remove_container(docker: Docker, hostname: str):
                """Stop and remove a Docker container"""
                await asyncio.sleep(0)  # Yield to event loop
                async with semaphore:  # Limit concurrent Docker operations
                    try:
                        # Get container
                        container = await docker.containers.get(hostname)
                        # Stop container with timeout
                        await container.stop(timeout=STOP_TIMEOUT)
                        # Delete container
                        await container.delete(force=True)
                        
                        if DEBUG:
                            print(f'{Fore.LIGHTYELLOW_EX}REMOVE | Deleted container for {hostname}{Style.RESET_ALL}', file=sys.stderr)
                    except Exception as e:
                        if DEBUG:
                            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)
                            
            async with Docker() as docker:  # Docker client context
                tasks = []
                for hostname in hostnames:
                    # Remove server from hash map
                    Servers.remove(hostname)
                    # Remove heartbeat counter
                    heartbeat_fail_count.pop(hostname, None)
                    # Schedule container removal
                    tasks.append(remove_container(docker, hostname))
                    
                # Wait for all containers to be removed
                await asyncio.gather(*tasks, return_exceptions=True)
                
            # Get final list of servers
            final_hostnames = Servers.getServerList()
            
        # Return success response
        return jsonify(ic({
            'message': {
                'N': len(Servers),
                'Servers': final_hostnames
            },
            'status': 'success'
        })), 200
    except Exception as e:
        if DEBUG:
            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)
        return jsonify(ic(err_payload(e))), 400

@app.route('/home', methods=['GET'])
async def home():
    """Handle client request - route to the appropriate server based on consistent hashing"""
    global Servers
    await asyncio.sleep(0)  # Yield to event loop
    try:
        # Generate random request ID for consistent hashing
        request_id = random.randint(100000, 999999)
        ic(request_id)
        
        # Find server using consistent hashing
        async with mutexLock:  # Thread-safe access to Servers
            server_name = Servers.find(request_id)
            
        if server_name is None:
            raise Exception('No servers are available')
            
        ic(server_name)
        
        # Forward request to selected server
        async def wrapper(session: aiohttp.ClientSession, server_name: str):
            """Forward request to server and get response"""
            await asyncio.sleep(0)  # Yield to event loop
            async with session.get(f'http://{server_name}:5000/home') as response:
                await response.read()  # Ensure response body is read
            return response
            
        # Set timeout for request
        timeout = aiohttp.ClientTimeout(connect=REQUEST_TIMEOUT)
        
        # Send request to server
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [asyncio.create_task(wrapper(session, server_name))]
            serv_response = await asyncio.gather(*tasks, return_exceptions=True)
            serv_response = serv_response[0] if not isinstance(serv_response[0], BaseException) else None
            
        if serv_response is None:
            raise Exception('Server did not respond')
            
        # Return server response
        return jsonify(ic(await serv_response.json())), 200
    except Exception as e:
        if DEBUG:
            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)
        return jsonify(ic(err_payload(e))), 400

@app.route('/<path:path>')
async def catch_all(path):
    """Catch-all route for undefined endpoints"""
    return jsonify(ic({
        'message': f'<Error> /{path} endpoint does not exist in server Servers',
        'status': 'failure'
    })), 400

# Application lifecycle hooks

@app.before_serving
async def my_startup():
    """Initialize background tasks before serving requests"""
    app.add_background_task(get_heartbeats)  # Start heartbeat monitoring

@app.after_serving
async def my_shutdown():
    """Clean up resources after serving requests"""
    # Cancel background tasks
    app.background_tasks.pop().cancel()
    
    # Clean up Docker containers
    semaphore = asyncio.Semaphore(DOCKER_TASK_BATCH_SIZE)
    async def wrapper(docker: Docker, server_name: str):
        """Stop and remove a Docker container"""
        await asyncio.sleep(0)  # Yield to event loop
        async with semaphore:  # Limit concurrent Docker operations
            try:
                container = await docker.containers.get(server_name)
                await container.stop(timeout=STOP_TIMEOUT)
                await container.delete(force=True)
                if DEBUG:
                    print(f'{Fore.LIGHTYELLOW_EX}REMOVE | Deleted container for {server_name}{Style.RESET_ALL}', file=sys.stderr)
            except Exception as e:
                if DEBUG:
                    print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)
                    
    async with Docker() as docker:  # Docker client context
        tasks = [wrapper(docker, server_name) for server_name in Servers.getServerList()]
        await asyncio.gather(*tasks, return_exceptions=True)

# Background tasks

async def get_heartbeats():
    """Background task to monitor server health via heartbeat requests"""
    global Servers, heartbeat_fail_count, serv_id
    if DEBUG:
        print(f'{Fore.CYAN}HEARTBEAT | Heartbeat background task started{Style.RESET_ALL}', file=sys.stderr)
    await asyncio.sleep(0)  # Yield to event loop
    try:
        while True:
            # Get current list of servers
            async with mutexLock:  # Thread-safe access to Servers
                if DEBUG:
                    print(f'{Fore.CYAN}HEARTBEAT | Checking heartbeat every {HEARTBEAT_INTERVAL} seconds{Style.RESET_ALL}', file=sys.stderr)
                else:
                    print('HEARTBEAT CHECK')
                hostnames = Servers.getServerList().copy()
                
            # Prepare heartbeat URLs
            heartbeat_urls = [f'http://{server_name}:5000/heartbeat' for server_name in hostnames]
            
            # Set timeout for heartbeat requests
            timeout = aiohttp.ClientTimeout(connect=REQUEST_TIMEOUT)
            
            # Send heartbeat requests to all servers
            async with aiohttp.ClientSession(timeout=timeout) as session:
                heartbeats = await gather_with_concurrency(session, REQUEST_BATCH_SIZE, *heartbeat_urls)
                
            await asyncio.sleep(0)  # Yield to event loop
            
            # Handle failed heartbeats
            semaphore = asyncio.Semaphore(DOCKER_TASK_BATCH_SIZE)
            async def flatline_wrapper(serv_id: int, server_name: str):
                """Wrapper for handling failed servers"""
                await asyncio.sleep(0)  # Yield to event loop
                async with semaphore:  # Limit concurrent Docker operations
                    try:
                        await handle_flatline(serv_id, server_name)
                    except Exception as e:
                        if DEBUG:
                            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)
                            
            flatlines = []
            async with mutexLock:  # Thread-safe access to shared data
                for i, response in enumerate(heartbeats):
                    if response is None or not response.status == 200:
                        # Increment fail count for server
                        heartbeat_fail_count[hostnames[i]] = heartbeat_fail_count.get(hostnames[i], 0) + 1
                        if heartbeat_fail_count[hostnames[i]] >= MAX_FAIL_COUNT:
                            # Server has failed too many times, restart it
                            serv_id += 1
                            flatlines.append(flatline_wrapper(serv_id, hostnames[i]))
                    else:
                        # Reset fail count for healthy server
                        heartbeat_fail_count[hostnames[i]] = 0
                        
                # Handle failed servers
                if flatlines:
                    await asyncio.gather(*flatlines, return_exceptions=True)
                    
            # Wait until next heartbeat check
            await asyncio.sleep(HEARTBEAT_INTERVAL)
    except asyncio.CancelledError:
        if DEBUG:
            print(f'{Fore.CYAN}HEARTBEAT | Heartbeat background task stopped{Style.RESET_ALL}', file=sys.stderr)

async def handle_flatline(serv_id: int, hostname: str):
    """Recreate and restart a failed server container"""
    await asyncio.sleep(0)  # Yield to event loop
    if DEBUG:
        print(f'{Fore.LIGHTRED_EX}FLATLINE | Flatline of server replica {hostname} detected{Style.RESET_ALL}', file=sys.stderr)
    try:
        async with Docker() as docker:  # Docker client context
            # Configure container
            container_config = {
                'image': 'server:v1',
                'detach': True,
                'env': [f'SERVER_ID={serv_id}', 'DEBUG=true'],
                'hostname': hostname,
                'tty': True,
            }
            
            # Create or replace container
            container = await docker.containers.create_or_replace(name=hostname, config=container_config)
            
            # Connect to network
            LB = await docker.networks.get('LB')
            connect_config = {
                'Container': container.id, 
                'EndpointConfig': {
                    'Aliases': [hostname]
                }
            }
            await LB.connect(connect_config)
            
            # Start container
            await container.start()
            
            if DEBUG:
                print(f'{Fore.MAGENTA}RESPAWN | Started container for {hostname}{Style.RESET_ALL}', file=sys.stderr)
    except Exception as e:
        if DEBUG:
            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)

if __name__ == '__main__':
    # Get port from command line argument or use default
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    # Start the application
    app.run(host='0.0.0.0', port=port, use_reloader=False, debug=DEBUG)