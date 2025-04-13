import logging
import asyncpg
import aiohttp
import os
import random
import sys
import time
from aiodocker import Docker
from quart import Quart, request, jsonify
from colorama import Fore, Style
from ConsistentHashing import ConsistentHashMap
from asyncio import Lock
import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO)

DEBUG = True

mutexLock = Lock()

schema = {}

MAX_FAIL_COUNT = 5  # Maximum number of heartbeat failures before server is considered down
HEARTBEAT_INTERVAL = 10  # Seconds between heartbeat checks
STOP_TIMEOUT = 5  # Timeout for stopping containers
REQUEST_TIMEOUT = 1  # Timeout for client requests
REQUEST_BATCH_SIZE = 10  # Number of concurrent requests to process
DOCKER_TASK_BATCH_SIZE = 10  # Number of concurrent Docker operations
MAX_CONFIG_FAIL_COUNT = 15

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

@app.route('/rep', methods=['GET'])
async def rep():
    """Report the current state of the server cluster"""
    global Servers
    async with mutexLock:  # Ensure thread-safe access to Servers
        return jsonify({
            'message': {
                'N': len(Servers),  # Number of servers
                'Servers': Servers.getServerList(),  # List of server hostnames
            },
            'status': 'successful',
        }), 200

@app.route('/init',method=['POST'])
async def init():
    global Servers, heartbeat_fail_count, serv_ids,shard_map,schema

    await asyncio.sleep(0)

    try:
        payload = await request.get_json()
        
        if payload is None:
            raise Exception("No Payload")
        
        N = int(payload.get('N', -1))
        schema = payload.get('schema', {})
        shards:List[Dict[str,Any]] = list(payload.get('shards', []))
        servers:Dict[str,List[str]] = dict(payload.get('servers', {}))

        server_name = list(servers.keys())

        if N <= 0 or not schema or not shards or not servers:
            raise Exception("Missing or invalid fields in payload")

        if not isinstance(schema, dict) or 'columns' not in schema or 'dtypes' not in schema:
            raise Exception("Invalid schema provided; must include 'columns' and 'dtypes' keys.")
        
        if len(schema['columns']) != len(schema['dtypes']):
            raise Exception("Schema mismatch: 'columns' and 'dtypes' must have the same number of elements.")
        
        if len(server_name)!=N:
            raise Exception("Number of Servers not same")

        print(f"Schema columns: {schema['columns']}")
        print(f"Schema dtypes: {schema['dtypes']}")
        
        for shard in shards:
            if not all(k in shard.keys()
                for k in ['stud_id_low', 'shard_id', 'shard_size']):
                raise Exception('Invalid shard description')
        
        async with mutexLock:
            Servers.clear()
            heartbeat_fail_count.clear()
            serv_ids.clear()
            shard_map.clear()

            shard_ids: Set[str] = set(shard['shard_id'] for shard in shards)
            miss_shards = set()
            for server_shards in servers.values():
                miss_shards |= set(server_shards) - shard_ids

            
            if(len(miss_shards)):
                raise Exception(f"Missing Shard Definations : `{miss_shards}` ")

            for server in servers:
                Servers.add(server)
                heartbeat_fail_count[server] = 0

            for shard in shards:
                shard_id = shard['shard_id']
                shard_map[shard_id] = ConsistentHashMap()
            
            docker_semaphore = asyncio.Semaphore(DOCKER_TASK_BATCH_SIZE)

            async def spawn_container(docker: Docker, serv_id: int, hostname: str):
                """Create and start a new Docker container for a server instance"""
                await asyncio.sleep(0)  # Yield to event loop
                async with docker_semaphore:  # Limit concurrent Docker operations
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

            async def post_config_wrapper(semaphore: asyncio.Semaphore,session: aiohttp.ClientSession,server: str,payload: Dict):
                await asyncio.sleep(0)

                async with semaphore:
                    for _ in range(MAX_CONFIG_FAIL_COUNT):
                        try:
                            async with session.get(f'http://{server}:5000/heartbeat') as response:
                                if response.status == 200:
                                    break
                        except Exception:
                            pass
                        await asyncio.sleep(2)
                    else:
                        raise Exception()

                    async with session.post(f'http://{server}:5000/config',json=payload) as response:
                        await response.read()

                    return response

            async with Docker() as docker:
                
                new_tasks = []
                for server in server_name:

                    Servers.add(server)  
                    heartbeat_fail_count[server] = 0
                    
                    for shards in servers[server]:
                        shard_map[shards].add(server)

                    new_tasks.append(spawn_container(docker, serv_id, server))

                res = await asyncio.gather(*new_tasks, return_exceptions=True)

                if any(res):
                    raise Exception('Failed to spawn containers')

            await asyncio.sleep(0)
            
            req_semaphore = asyncio.Semaphore(REQUEST_BATCH_SIZE)
            timeout = aiohttp.ClientTimeout(connect=REQUEST_TIMEOUT)
            

            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Define tasks
                new_tasks = [asyncio.create_task(post_config_wrapper(semaphore=req_semaphore,session=session,server=server,payload={"shards": servers[hostname]})) for server in server_name]

                # Wait for all tasks to complete
                config_responses = await asyncio.gather(*new_tasks, return_exceptions=True)
                config_responses = [None if isinstance(response, BaseException)
                                    else response
                                    for response in config_responses]

                for (hostname, response) in zip(server_name, config_responses):
                    if response is None or response.status != 200:
                        raise Exception(f'Failed to add shards to {hostname}')

            async with app.db_pool.acquire() as conn:
                async with conn.transaction():
                    stmt = await conn.prepare(
                        '''--sql
                        INSERT INTO shardT (
                            stud_id_low,
                            shard_id,
                            shard_size)
                        VALUES (
                            $1::INTEGER,
                            $2::TEXT,
                            $3::INTEGER);
                        ''')

                    await stmt.executemany(
                        [(shard['stud_id_low'],
                          shard['shard_id'],
                          shard['shard_size'])
                         for shard in shards])
                    
        return jsonify({
            'message': 'Configured Database',
            'status': 'success'
        }), 200

    except Exception as e:
        if DEBUG:
            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)
        return jsonify(err_payload(e)), 400

@app.route('/status',method=["GET"])
async def status():
    global Servers, heartbeat_fail_count, serv_ids,shard_map,schema

    await asyncio.sleep(0)

    try:
        async with mutexLock:
            shards: List[Dict[str, Any]] = []

            async with app.db_pool.acquire() as conn:
                async with conn.transaction(readonly=True):
                    stmt = await conn.prepare(
                        '''--sql
                            SELECT
                                stud_id_low,
                                shard_id,
                                shard_size
                            FROM
                                shardT;
                        ''')

                    async for record in stmt.cursor():
                        shards.append(dict(record))
                        
            servers_to_shards: Dict[str, List[str]] = {}
            _shard_map = {k: v.getServerList() for k, v in shard_map.items()}

            for shard, servers in _shard_map.items():
                for server in servers:
                    if server not in servers_to_shards.keys():
                        servers_to_shards[server] = []
                    servers_to_shards[server].append(shard)
                        
            return jsonify({
                'message': {
                    "N": len(Servers),
                    "schema" : schema,
                    "shards" : shards,
                    "servers": 
                    {
                        server: 
                        {
                            'id': serv_ids[server],
                            'shards': shards
                        } for server, shards in servers_to_shards.items()
                    }
                },
                'status': 'successful',
            }), 200

    except Exception as err:
        return jsonify(err_payload(err)), 400

@app.route('/add',method=['POST'])
async def add():
    """Add new server instances to the cluster"""
    global Servers, heartbeat_fail_count, serv_ids,shard_map
    await asyncio.sleep(0)  # Yield to event loop

    try:
        # Parse request payload
        payload: dict = await request.get_json()
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

            miss_shards = set()
            for shard in servers.values():
                miss_shards |= set(shard)-new_shards-shard_map.keys() 

            if(len(miss_shards)):
                raise Exception(f'Shard {miss_shards} are already in Servers')

            for s in new_shards:
                shard_map[s] = ConsistentHashMap()
                
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


            async def copy_shards_to_container(
                hostname: str,
                shards: List[str],
                semaphore: asyncio.Semaphore,
                servers_flatlined: Optional[List[str]]=None
            ):
                """
                1. Call /config endpoint on the server S with the hostname
                1. For each shard K in `shards`:
                    1. Get server A from `shard_map` for the shard K
                    1. Call /copy on server A to copy the shard K
                    1. Call /write on server S to write the shard K

                Args:
                    - hostname: hostname of the server
                    - shards: list of shard names to copy
                    - semaphore: asyncio.Semaphore
                """

                if servers_flatlined is None:
                    servers_flatlined = []

                global shard_map

                # Allow other tasks to run
                await asyncio.sleep(0)

                async def post_config_wrapper(
                    session: aiohttp.ClientSession,
                    hostname: str,
                    payload: dict,
                ):
                    # Allow other tasks to run
                    await asyncio.sleep(0)

                    async with semaphore:
                        # Wait for the server to be up
                        for _ in range(50):
                            try:
                                async with session.get(f'http://{hostname}:5000/heartbeat') as response:
                                    if response.status == 200:
                                        break
                            except Exception:
                                pass
                            await asyncio.sleep(2)
                        else:
                            raise Exception()
                        # END for _ in range(MAX_CONFIG_FAIL_COUNT)

                        async with session.post(f'http://{hostname}:5000/config',
                                                json=payload) as response:
                            await response.read()

                        return response
                    # END async with semaphore
                # END post_config_wrapper

                async def get_copy_wrapper(
                    session: aiohttp.ClientSession,
                    hostname: str,
                    payload: dict,
                ):
                    # Allow other tasks to run
                    await asyncio.sleep(0)

                    async with semaphore:
                        async with session.get(f'http://{hostname}:5000/copy',
                                            json=payload) as response:
                            await response.read()

                        return response
                    # END async with semaphore
                # END get_copy_wrapper

                async def post_write_wrapper(
                    session: aiohttp.ClientSession,
                    hostname: str,
                    payload: dict,
                ):
                    # Allow other tasks to run
                    await asyncio.sleep(0)

                    async with semaphore:
                        async with session.post(f'http://{hostname}:5000/write',
                                                json=payload) as response:
                            await response.read()

                        return response
                    # END async with semaphore

                # List of shards to copy from each server A [server -> list of [shard_id, valid_at]]
                call_server_shards: dict[str, list[tuple[str, int]]] = {}

                # For each shard K in `shards`:
                async with app.db_pool.acquire() as conn:
                    async with conn.transaction():
                        stmt = await conn.prepare(
                            '''--sql
                            SELECT
                                valid_at
                            FROM
                                ShardT
                            WHERE
                                shard_id = $1::TEXT;
                            ''')

                        for shard in shards:
                            if len(shard_map[shard]) == 0:
                                continue

                            # Get server A from `shard_map` for the shard K
                            # TODO: Chage to ConsistentHashMap

                            server = shard_map[shard].find(random.randint(100000, 999999))
                            if len(servers_flatlined) > 0:
                                while server in servers_flatlined:
                                    server = shard_map[shard].find(random.randint(100000, 999999))

                            shard_valid_at: int = await stmt.fetchval(shard)

                            if server not in call_server_shards:
                                call_server_shards[server] = []

                            call_server_shards[server].append((shard, shard_valid_at))

                timeout = aiohttp.ClientTimeout(connect=REQUEST_TIMEOUT)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    # Call /config endpoint on the server S with the hostname
                    config_task = asyncio.create_task(
                        post_config_wrapper(
                            session,
                            hostname,
                            payload={
                                "shards": shards
                            }
                        )
                    )
                    config_response = await asyncio.gather(*[config_task], return_exceptions=True)
                    config_response = (None if isinstance(config_response[0], BaseException)
                                    else config_response[0])

                    if config_response is None or config_response.status != 200:
                        raise Exception(f'Failed to add shards to {hostname}')

                    # Call /copy on server A to copy the shard K
                    # Define tasks
                    tasks = [asyncio.create_task(
                        get_copy_wrapper(
                            session,
                            server,
                            payload={
                                "shards": [shard[0] for shard in shards],
                                "valid_at": [shard[1] for shard in shards],
                            }
                        )
                    ) for server, shards in call_server_shards.items()]

                    # Wait for all tasks to complete
                    copy_responses = await asyncio.gather(*tasks, return_exceptions=True)
                    copy_responses = [None if isinstance(response, BaseException)
                                    else response
                                    for response in copy_responses]

                    # Get the data from the copy_responses [shard_id -> (list of data, valid_at)]
                    all_data: dict[str, tuple[list, int]] = {}

                    for (response, server_shards) in zip(copy_responses,
                                                        call_server_shards.values()):
                        if response is None or response.status != 200:
                            raise Exception(f'Failed to copy shards to {hostname}')

                        data: dict = await response.json()

                        for shard_id, valid_at in server_shards:
                            all_data[shard_id] = (data[shard_id], valid_at)

                    # Call /write on server S to write the shard K
                    # Define tasks
                    tasks = [asyncio.create_task(
                        post_write_wrapper(
                            session,
                            hostname,
                            payload={
                                'shard': shard,
                                'data': data,
                                'admin': True,
                                'valid_at': valid_at,
                            }
                        )
                    ) for shard, (data, valid_at) in all_data.items()]

                    # Wait for all tasks to complete
                    write_responses = await asyncio.gather(*tasks, return_exceptions=True)
                    write_responses = [None if isinstance(response, BaseException)
                                    else response
                                    for response in write_responses]

                    if any(response is None or response.status != 200
                            for response in write_responses):
                        raise Exception(f'Failed to write shards to {hostname}')

            

            # Get final list of servers
            final_hostnames = Servers.getServerList()
            
        # Return success response
        return jsonify({
            'message': {
                'N': len(Servers),
                'Servers': final_hostnames
            },
            'status': 'success'
        }), 200
    except Exception as e:
        if DEBUG:
            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)
        return jsonify(err_payload(e)), 400




if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, use_reloader=False)
