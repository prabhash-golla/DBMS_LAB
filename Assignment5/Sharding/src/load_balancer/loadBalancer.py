import logging
import asyncpg
import aiohttp
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
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)

DEBUG = True

mutexLock = Lock()

MAX_FAIL_COUNT = 5  # Maximum number of heartbeat failures before server is considered down
HEARTBEAT_INTERVAL = 10  # Seconds between heartbeat checks
STOP_TIMEOUT = 5  # Timeout for stopping containers
REQUEST_TIMEOUT = 1  # Timeout for client requests
REQUEST_BATCH_SIZE = 10  # Number of concurrent requests to process
DOCKER_TASK_BATCH_SIZE = 10  # Number of concurrent Docker operations

Servers = ConsistentHashMap()  # Consistent hash map for server selection
heartbeat_fail_count: dict[str, int] = {}  # Track failed heartbeats for each server
serv_ids: dict[str,int] = {}
shard_map: dict[str, ConsistentHashMap] = {}

app = Quart(__name__)

def err_payload(err: Exception):
    """Create standardized error response payload"""
    return {
        'message': f'<Error> {err}',
        'status': 'failure'
    }

async def create_db_pool():
    try:
        # Corrected DSN with the proper username "postgres" and your password.
        pool = await asyncpg.create_pool(dsn="postgresql://postgres:5243y6!J@localhost:5432/postgres")
        return pool
    except Exception as e:
        logging.error("Failed to create db pool: %s", e)
        return None

@app.before_serving
async def startup():

    try:
        app.db_pool = await create_db_pool()
        if app.db_pool:
            app.add_background_task(get_heartbeats)
            logging.info("Database connection pool created.")
        else:
            logging.warning("Database connection pool was not created.")

    except Exception as e:
        print("Error")

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


@app.after_serving
async def shutdown_db(exception):
    if hasattr(app, 'db_pool') and app.db_pool:
        await app.db_pool.close()
        logging.info("Database connection pool closed.")
    else:
        logging.info("No database connection pool to close.")

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

@app.route('/add',method=['POST'])
async def add():
    """Add new server instances to the cluster"""
    global Servers, heartbeat_fail_count, serv_ids,shard_map
    await asyncio.sleep(0)  # Yield to event loop

    try:
        # Parse request payload
        payload: dict = await request.get_json()
        ic(payload)  # Log payload for debugging
        if payload is None:
            raise Exception('Payload is empty')
            
        # Extract parameters
        n = int(payload.get("n",-1))

        new_shards: list[dict[str, any]] = list(payload.get('new_shards', []))

        servers: dict[str, list[str]] = dict(payload.get('servers', {}))
        hostnames = list(servers.keys())

        # Validate parameters
        if n <= 0:
            raise Exception('Number of servers to add must be greater than 0')
        if len(hostnames) != n:
            raise Exception('Length of hostname list is more than instances to add')
        if len(hostnames) != len(set(hostnames)):
            raise Exception('Hostname list contains duplicates')
            
        for shard in new_shards:
            if not all(k in shard.keys()
                       for k in
                       ('stud_id_low', 'shard_id', 'shard_size')):
                raise Exception('Invalid shard description')
        
        async with mutexLock:  # Ensure thread-safe access to shared data
            # Check if we have enough capacity
            if n > Servers.remaining():
                raise Exception(f'Insufficient slots. Only {Servers.remaining()} slots left')
            # Check for hostname collisions
            if not set(hostnames).isdisjoint(set(Servers.getServerList())):
                raise Exception(f'Hostnames {set(hostnames) & set(Servers.getServerList())} are already in Servers')
            
            if not set(new_shards).isdisjoint(set(shard_map.keys())):
                raise Exception(f'Shards {set(new_shards) & set(shard_map.keys())} are already in Shards')
            
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
                            'env': [f'SERVER_ID={serv_id}', 
                                    'DEBUG=true',
                                    'POSTGRES_HOST=localhost',
                                    'POSTGRES_PORT= 5432',
                                    'POSTGRES_USER=postgres',
                                    'POSTGRES_PASSWORD=5243y6!J',
                                    'POSTGRES_DB_NAME=postgres'  
                                ],  # Environment variables
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



if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, use_reloader=False)
