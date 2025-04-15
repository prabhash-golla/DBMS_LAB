import logging
import asyncpg
import aiohttp
import os
import random
import sys
import time
from aiodocker import Docker
from quart import Quart, request, jsonify
from quart_cors import cors
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
serv_id = 0
shard_map: dict[str, ConsistentHashMap] = {}


def err_payload(err: Exception):
    """Create standardized error response payload"""
    return {
        'message': f'<Error> {err}',
        'status': 'failure'
    }

SERVER_ID = os.environ.get('SERVER_ID', '0')
HOSTNAME = os.environ.get('HOSTNAME', 'localhost')
DB_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
DB_PORT = int(os.environ.get('POSTGRES_PORT', 5432))
DB_USER = os.environ.get('POSTGRES_USER', 'postgres')
DB_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'postgres')
DB_NAME = os.environ.get('POSTGRES_DB_NAME', 'postgres')

pool: asyncpg.Pool

async def gather_with_concurrency(
    session: aiohttp.ClientSession,
    batch: int,
    *urls: str
):
    
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
    """Recreate and restart a failed server container with its previous shards"""
    global shard_map, serv_ids
    
    await asyncio.sleep(0)  
    
    if DEBUG:
        print(f'{Fore.LIGHTRED_EX}FLATLINE | Flatline of server replica {hostname} detected{Style.RESET_ALL}', file=sys.stderr)
    
    # Store the shards that the flatlined server had
    server_shards = []
    for shard_id, servers in shard_map.items():
        if hostname in servers.getServerList():
            server_shards.append(shard_id)
    
    try:
        async with Docker() as docker:
            container_config = {
                'image': 'server:v2',
                'detach': True,
                'env': [
                    f'SERVER_ID={serv_id}', 
                    'DEBUG=true',
                    'POSTGRES_HOST=localhost',
                    'POSTGRES_PORT=5432',
                    'POSTGRES_USER=postgres',
                    'POSTGRES_PASSWORD=postgres',
                    'POSTGRES_DB_NAME=postgres'
                ],
                'hostname': hostname,
                'tty': True,
            }
            
            container = await docker.containers.create_or_replace(name=hostname, config=container_config)
            
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
            
            # Restore the shards configuration once the container is running
            if server_shards:
                # Wait for the server to be ready
                semaphore = asyncio.Semaphore(REQUEST_BATCH_SIZE)
                timeout = aiohttp.ClientTimeout(connect=REQUEST_TIMEOUT)
                
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    # Configure the server with its previous shards
                    async def post_config_wrapper():
                        for _ in range(MAX_CONFIG_FAIL_COUNT):
                            try:
                                async with session.get(f'http://{hostname}:5000/heartbeat') as response:
                                    if response.status == 200:
                                        break
                            except Exception:
                                pass
                            await asyncio.sleep(2)
                        else:
                            if DEBUG:
                                print(f'{Fore.RED}ERROR | Failed to establish connection to respawned server {hostname}{Style.RESET_ALL}', file=sys.stderr)
                            return None

                        try:
                            async with session.post(f'http://{hostname}:5000/config', json={"shards": server_shards}) as response:
                                await response.read()
                                return response
                        except Exception as e:
                            if DEBUG:
                                print(f'{Fore.RED}ERROR | Failed to configure shards on respawned server {hostname}: {e}{Style.RESET_ALL}', file=sys.stderr)
                            return None
                
                    # Restore data for each shard
                    async def restore_shards():
                        # Process each shard
                        for shard_id in server_shards:
                            other_servers = []
                            # Find other servers that have this shard
                            for server in shard_map[shard_id].getServerList():
                                if server != hostname and server in Servers.getServerList():
                                    other_servers.append(server)
                            
                            if not other_servers:
                                # No other server has this shard - data loss may occur
                                if DEBUG:
                                    print(f'{Fore.YELLOW}WARNING | Potential data loss: No other server has shard {shard_id} previously on {hostname}{Style.RESET_ALL}', file=sys.stderr)
                                continue
                            
                            # Get shard data from another server
                            try:
                                source_server = random.choice(other_servers)
                                async with pool.acquire() as conn:
                                    async with conn.transaction(readonly=True):
                                        shard_valid_at = await conn.fetchval(
                                            'SELECT valid_at FROM ShardT WHERE shard_id = $1::TEXT', 
                                            shard_id
                                        )
                                
                                # Get data from source server
                                async with session.get(
                                    f'http://{source_server}:5000/copy',
                                    json={"shards": [shard_id], "valid_at": [shard_valid_at]}
                                ) as response:
                                    if response.status == 200:
                                        data = await response.json()
                                        # Write data to respawned server
                                        async with session.post(
                                            f'http://{hostname}:5000/write',
                                            json={
                                                'shard': shard_id,
                                                'data': data[shard_id],
                                                'admin': True,
                                                'valid_at': shard_valid_at,
                                            }
                                        ) as write_response:
                                            if write_response.status == 200:
                                                if DEBUG:
                                                    print(f'{Fore.GREEN}INFO | Successfully restored shard {shard_id} on {hostname}{Style.RESET_ALL}', file=sys.stderr)
                                            else:
                                                if DEBUG:
                                                    print(f'{Fore.YELLOW}WARNING | Failed to write data to shard {shard_id} on {hostname}{Style.RESET_ALL}', file=sys.stderr)
                                    else:
                                        if DEBUG:
                                            print(f'{Fore.YELLOW}WARNING | Failed to copy data for shard {shard_id} from {source_server}{Style.RESET_ALL}', file=sys.stderr)
                            except Exception as e:
                                if DEBUG:
                                    print(f'{Fore.YELLOW}WARNING | Failed to restore shard {shard_id} on {hostname}: {e}{Style.RESET_ALL}', file=sys.stderr)
                
                    # Execute both operations
                    config_response = await post_config_wrapper()
                    if config_response and config_response.status == 200:
                        await restore_shards()
                        if DEBUG:
                            print(f'{Fore.GREEN}INFO | Successfully configured respawned server {hostname} with its previous shards{Style.RESET_ALL}', file=sys.stderr)
                    else:
                        if DEBUG:
                            print(f'{Fore.YELLOW}WARNING | Could not configure respawned server {hostname} with its previous shards{Style.RESET_ALL}', file=sys.stderr)
            
            # Reset the heartbeat fail counter for this server
            heartbeat_fail_count[hostname] = 0
            serv_ids[hostname] = serv_id
            
    except Exception as e:
        if DEBUG:
            print(f'{Fore.RED}ERROR | Failed to handle flatline for {hostname}: {e}{Style.RESET_ALL}', file=sys.stderr)

app = cors(Quart(__name__), allow_origin="*")

@app.after_serving
async def shutdown_db():
    if hasattr(app, 'db_pool') and pool:
        await pool.close()
        logging.info("Database connection pool closed.")
    else:
        logging.info("No database connection pool to close.")

@app.before_serving
async def startup():
    global pool
    try:
        app.add_background_task(get_heartbeats)
        pool = await asyncpg.create_pool( 
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            host=DB_HOST,
            port=DB_PORT
        )
        print(f'{Fore.GREEN}INFO | Database connection created.{Style.RESET_ALL}')
    except Exception as e:
        print(f'{Fore.RED}ERROR | Startup failed: '
              f'{e}'
              f'{Style.RESET_ALL}',
              file=sys.stderr)
        sys.exit(1)

@app.route('/',methods=['GET'])
@app.route('/help',methods=['GET'])
async def help():
    async with mutexLock:
        return jsonify({
                    'message': {
                        'help' : '/help - Methods : GET',
                        'init': '/init - Methods : GET,POST',
                        'status': '/status - Methods : GET',
                        'add': '/add - Methods : GET,POST',
                        'rm': '/rm - Methods : DELETE',
                        'read': '/read - Methods : GET,POST',
                        'write': '/write - Methods : GET,POST',
                        'update': '/update - Methods : PUT',
                        'del': '/del - Methods : DELETE',
                    },
                    'status': 'successful',
                }), 200

@app.route('/init',methods=['GET'])
async def init_get():
    example_schema = {
            "N": 3,
            "schema": {
                "columns": ["stud_id", "stud_name", "stud_marks"],
                "dtypes": ["Number", "String", "String"]
            },
            "shards": [
                {"stud_id_low": 0, "shard_id": "sh1", "shard_size": 4096},
                {"stud_id_low": 4096, "shard_id": "sh2", "shard_size": 4096},
                {"stud_id_low": 8192, "shard_id": "sh3", "shard_size": 4096}
            ],
            "servers": {
                "Server0": ["sh1", "sh2"],
                "Server1": ["sh2", "sh3"],
                "Server2": ["sh1", "sh3"]
            }
        }

    return jsonify({
        "message": "Expected schema for /init POST request",
        "payload_structure": example_schema,
        "status": "success"
    }), 200

@app.route('/init',methods=['POST'])
async def init():
    global Servers, heartbeat_fail_count, serv_ids,shard_map,schema,serv_id,pool

    await asyncio.sleep(0)

    try:
        payload = await request.get_json()
        print('Servers : ',Servers.getServerList())
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

        # print(f"Schema columns: {schema['columns']}")
        # print(f"Schema dtypes: {schema['dtypes']}")
        
        for shard in shards:
            if not all(k in shard.keys()
                for k in ['stud_id_low', 'shard_id', 'shard_size']):
                raise Exception('Invalid shard description')
        
        async with mutexLock:
            heartbeat_fail_count.clear()
            serv_ids.clear()
            shard_map.clear()

            shard_ids: Set[str] = set(shard['shard_id'] for shard in shards)
            miss_shards = set()
            for server_shards in servers.values():
                miss_shards |= set(server_shards) - shard_ids

            
            if(len(miss_shards)):
                raise Exception(f"Missing Shard Definations : `{miss_shards}` ")


            for shard in shards:
                shard_id = shard['shard_id']
                shard_map[shard_id] = ConsistentHashMap()
            
            docker_semaphore = asyncio.Semaphore(DOCKER_TASK_BATCH_SIZE)

            async def spawn_container(docker: Docker, serv_id: int, server: str):
                """Create and start a new Docker container for a server instance"""
                await asyncio.sleep(0)  # Yield to event loop
                async with docker_semaphore:  # Limit concurrent Docker operations
                    try:
                        container_config = {
                            'image': 'server:v2',
                            'detach': True,
                            'env': [
                                f'SERVER_ID={serv_id}', 
                                'DEBUG=true',
                                'POSTGRES_PASSWORD=postgres',
                                'POSTGRES_USER=postgres',
                                'POSTGRES_DB=postgres'    
                            ],
                            'hostname': server,
                            'tty': True,
                        }
                        # Create or replace container
                        container = await docker.containers.create_or_replace(
                            name=server,
                            config=container_config,
                        )
                        # Connect to network
                        LB = await docker.networks.get('LB')
                        await LB.connect({'Container': container.id, 'EndpointConfig': {'Aliases': [server]}})
                        
                        if DEBUG:
                            print(f'{Fore.LIGHTGREEN_EX}CREATE | Created container for {server}{Style.RESET_ALL}', file=sys.stderr)
                        
                        # Start container
                        await container.start()
                        
                        if DEBUG:
                            print(f'{Fore.MAGENTA}SPAWN | Started container for {server}{Style.RESET_ALL}', file=sys.stderr)
                    except Exception as e:
                        if DEBUG:
                            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)

            async def post_config_wrapper(semaphore: asyncio.Semaphore,session: aiohttp.ClientSession,server: str,payload: Dict):
                await asyncio.sleep(0)

                async with semaphore:
                    for _ in range(MAX_CONFIG_FAIL_COUNT):
                        try:
                            async with session.get(f'http://{server}:5000/heartbeat') as response:
                                # print(response)
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
                    
                    for shards_ in servers[server]:
                        shard_map[shards_].add(server)
                    serv_id += 1
                    new_tasks.append(spawn_container(docker, serv_id, server))

                res = await asyncio.gather(*new_tasks, return_exceptions=True)

                if any(res):
                    raise Exception('Failed to spawn containers')

            await asyncio.sleep(0)
            
            req_semaphore = asyncio.Semaphore(REQUEST_BATCH_SIZE)
            timeout = aiohttp.ClientTimeout(connect=REQUEST_TIMEOUT)
            

            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Define tasks
                new_tasks = [asyncio.create_task(post_config_wrapper(semaphore=req_semaphore,session=session,server=server,payload={"shards": servers[server]})) for server in server_name]

                # Wait for all tasks to complete
                config_responses = await asyncio.gather(*new_tasks, return_exceptions=True)
                config_responses = [None if isinstance(response, BaseException)
                                    else response
                                    for response in config_responses]
                for (server, response) in zip(server_name, config_responses):
                    if response is None or response.status != 200:
                        raise Exception(f'Failed to add shards to {server}')     

            async with pool.acquire() as con:
                async with con.transaction():
                    stmt = await con.prepare(
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

@app.route('/status',methods=["GET"])
async def status():
    global Servers, serv_ids,shard_map,schema,pool

    await asyncio.sleep(0)

    try:
        async with mutexLock:
            shards: List[Dict[str, Any]] = []

            async with pool.acquire() as conn:
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

            # print(shards)    

            servers_to_shards: Dict[str, List[str]] = {}
            _shard_map = {k: v.getServerList() for k, v in shard_map.items()}

            # print(_shard_map)
            for shard_id, ser in _shard_map.items():
                for se in ser:
                    if se in Servers.getServerList():
                        if se not in servers_to_shards.keys():
                            servers_to_shards[se] = []
                        servers_to_shards[se].append(shard_id)
            # print(servers_to_shards)

            return jsonify({
                'message': {
                    "N": len(Servers.getServerList()),
                    "schema" : schema,
                    "servers": servers_to_shards,
                    "shards" : shards,
                },
                'status': 'successful',
            }), 200

    except Exception as err:
        return jsonify(err_payload(err)), 400

@app.route('/add',methods =['GET'])
async def add_get():
    example_payload = {
        "n": 2,
        "new_shards" : [{"stud_id_low":12288,"shard_id":"sh5","shard_size":4096}],
        "servers" : {"Server4":["sh3","sh5"],"Server[5]":["sh2","sh5"]}
    }

    return jsonify({
        "example_payload": example_payload,
        "status": "success"
    }), 200

@app.route('/add',methods=['POST'])
async def add():
    """Add new server instances to the cluster"""
    global Servers, heartbeat_fail_count, serv_ids,shard_map,pool,serv_id
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
        
        server_names = list(servers.keys())

        # Validate parameters
        if n <= 0:
            raise Exception('Number of servers to add must be greater than 0')
        if len(server_names) != n:
            raise Exception('Length of hostname list is more than instances to add')
        if len(server_names) != len(set(server_names)):
            raise Exception('Hostname list contains duplicates')
            
        for shard in new_shards:
            if not all(k in shard.keys()
                       for k in
                       ('stud_id_low', 'shard_id', 'shard_size')):
                raise Exception('Invalid shard description')
        
        async with mutexLock: 
            
            if n > Servers.remaining():
                raise Exception(f'Insufficient slots. Only {Servers.remaining()} slots left')

            if not set(server_names).isdisjoint(set(Servers.getServerList())):
                raise Exception(f'Hostnames {set(server_names) & set(Servers.getServerList())} are already in Servers')
            
            # Extract shard IDs from new_shards dictionaries
            new_shard_ids = set(shard["shard_id"] for shard in new_shards)
            if not new_shard_ids.isdisjoint(shard_map.keys()):
                raise Exception(f'Shards {new_shard_ids & shard_map.keys()} is/are already in Shards')

            miss_shards = set()
            for shard in servers.values():
                miss_shards |= set(shard)-new_shard_ids-shard_map.keys() 

            if(len(miss_shards)):
                raise Exception(f'Shard {miss_shards} are already in Servers')

            for s in new_shard_ids:
                shard_map[s] = ConsistentHashMap()
                
            semaphore = asyncio.Semaphore(DOCKER_TASK_BATCH_SIZE)  # Limit concurrent Docker operations
    
            async def spawn_container(docker: Docker, serv_id: int, server: str):
                """Create and start a new Docker container for a server instance"""
                await asyncio.sleep(0)  # Yield to event loop
                async with semaphore:  # Limit concurrent Docker operations
                    try:
                        # Configure container
                        container_config = {
                            'image': 'server:v2',  # Docker image to use
                            'detach': True,  # Run in background
                            'env': [f'SERVER_ID={serv_id}', 
                                    'DEBUG=true',
                                    'POSTGRES_HOST=localhost',
                                    'POSTGRES_PORT=5432',
                                    'POSTGRES_USER=postgres',
                                    'POSTGRES_PASSWORD=postgres',
                                    'POSTGRES_DB_NAME=postgres'  
                                ],  # Environment variables
                            'hostname': server,  # Container hostname
                            'tty': True,  # Allocate a terminal
                        }

                        # Create or replace container
                        container = await docker.containers.create_or_replace(
                            name=server,
                            config=container_config,
                        )
                        # Connect to network
                        LB = await docker.networks.get('LB')
                        await LB.connect({'Container': container.id, 'EndpointConfig': {'Aliases': [server]}})
                        
                        if DEBUG:
                            print(f'{Fore.LIGHTGREEN_EX}CREATE | Created container for {server}{Style.RESET_ALL}', file=sys.stderr)
                        
                        # Start container
                        await container.start()
                        
                        if DEBUG:
                            print(f'{Fore.MAGENTA}SPAWN | Started container for {server}{Style.RESET_ALL}', file=sys.stderr)
                    except Exception as e:
                        if DEBUG:
                            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)
                            
            async with Docker() as docker:
                new_tasks = []
                for server in server_names:
                    Servers.add(server)
                    heartbeat_fail_count[server] = 0
                    serv_ids[server] = serv_id
                    serv_id += 1
                    new_tasks.append(spawn_container(docker, serv_id, server))
                    print(f"Added {server} to hash map. Current servers: {Servers.getServerList()}")
                    print(f"Server slots for {server}: {Servers.server_slots[server]}")

                await asyncio.gather(*new_tasks, return_exceptions=True)


            async def copy_shards_to_container(
                server: str,
                shards: List[str],
                semaphore: asyncio.Semaphore,
                servers_flatlined: Optional[List[str]]=None
            ):

                if servers_flatlined is None:
                    servers_flatlined = []

                global shard_map

                await asyncio.sleep(0)

                async def post_config_wrapper(
                    session: aiohttp.ClientSession,
                    server: str,
                    payload: dict,
                ):
                    await asyncio.sleep(0)

                    async with semaphore:
                        for _ in range(50):
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
    
                async def get_copy_wrapper(
                    session: aiohttp.ClientSession,
                    server: str,
                    payload: dict,
                ):
                    await asyncio.sleep(0)

                    async with semaphore:
                        async with session.get(f'http://{server}:5000/copy',
                                            json=payload) as response:
                            await response.read()

                        return response

                async def post_write_wrapper(
                    session: aiohttp.ClientSession,
                    server: str,
                    payload: dict,
                ):
                    # Allow other tasks to run
                    await asyncio.sleep(0)

                    async with semaphore:
                        async with session.post(f'http://{server}:5000/write',json=payload) as response:
                            await response.read()

                        return response
                    
                call_server_shards: dict[str, list[tuple[str, int]]] = {}

                # For each shard K in `shards`:
                async with pool.acquire() as conn:
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

                    config_task = asyncio.create_task(
                        post_config_wrapper(
                            session,
                            server,
                            payload={
                                "shards": shards
                            }
                        )
                    )
                    config_response = await asyncio.gather(*[config_task], return_exceptions=True)
                    config_response = (None if isinstance(config_response[0], BaseException)
                                    else config_response[0])

                    if config_response is None or config_response.status != 200:
                        raise Exception(f'Failed to add shards to {server}')

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

                    copy_responses = await asyncio.gather(*tasks, return_exceptions=True)
                    copy_responses = [None if isinstance(response, BaseException)
                                    else response
                                    for response in copy_responses]

                    all_data: dict[str, tuple[list, int]] = {}

                    for (response, server_shards) in zip(copy_responses,
                                                        call_server_shards.values()):
                        if response is None or response.status != 200:
                            raise Exception(f'Failed to copy shards to {server}')

                        data: dict = await response.json()

                        for shard_id, valid_at in server_shards:
                            all_data[shard_id] = (data[shard_id], valid_at)

                    tasks = [asyncio.create_task(
                        post_write_wrapper(
                            session,
                            server,
                            payload={
                                'shard': shard,
                                'data': data,
                                'admin': True,
                                'valid_at': valid_at,
                            }
                        )
                    ) for shard, (data, valid_at) in all_data.items()]

                    write_responses = await asyncio.gather(*tasks, return_exceptions=True)
                    write_responses = [None if isinstance(response, BaseException)
                                    else response
                                    for response in write_responses]

                    if any(response is None or response.status != 200
                            for response in write_responses):
                        raise Exception(f'Failed to write shards to {server}')

            await asyncio.sleep(0)
            
            new_tasks = [asyncio.create_task(
                copy_shards_to_container(
                    ser,
                    servers[ser],
                    semaphore
                )
            ) for ser in server_names]

            await asyncio.gather(*new_tasks,return_exceptions=True)

            for ser in server_names:
                for shard in servers[ser]:
                    shard_map[shard].add(ser)

            if len(new_shards) > 0:
                async with pool.acquire() as conn:
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
                             for shard in new_shards])  

            final_hostnames = Servers.getServerList()
    

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

@app.route('/rm',methods=['GET'])
async def rm_get():
    example_payload = {
        "n" : 2,
        "servers" : ["Server 4"]
    }

    return jsonify({
        "message": "Remove Shard",
        "payload_structure": example_payload,
        "status": "success"
    }), 200

@app.route('/rm',methods=['DELETE'])
async def delete():
    global Servers,heartbeat_fail_count,pool
    
    await asyncio.sleep(0)
    
    try:
        payload: dict = await request.get_json()
        
        if payload is None:
            raise Exception('Payload is empty')
        
        n = int(payload.get('n', -1))
        servers: list[str] = list(payload.get('servers', []))

        if n <= 0:
            raise Exception('Number of servers to delete must be greater than 0')
        if n > len(Servers):
            raise Exception('Number of servers to delete must be less than or equal to number of Servers')
        if len(servers) > n:
            raise Exception('Length of hostname list is more than instances to delete')

        async with mutexLock:
            
            choices = set(Servers.getServerList())
            if not set(servers).issubset(choices):
                raise Exception(f'Hostnames {set(servers) - choices} are not in Servers')

            choices = list(choices - set(servers))
            random_hostnames = random.sample(choices, k=n - len(servers))
            servers.extend(random_hostnames)
            
            semaphore = asyncio.Semaphore(DOCKER_TASK_BATCH_SIZE)  
            
            async def remove_container(docker: Docker, hostname: str):
                """Stop and remove a Docker container"""
                await asyncio.sleep(0) 
                async with semaphore:  
                    try:
                        container = await docker.containers.get(hostname)
                        await container.stop(timeout=STOP_TIMEOUT)
                        await container.delete(force=True)
                        
                        if DEBUG:
                            print(f'{Fore.LIGHTYELLOW_EX}REMOVE | Deleted container for {hostname}{Style.RESET_ALL}', file=sys.stderr)
                    except Exception as e:
                        if DEBUG:
                            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)
                            
            async with Docker() as docker:  
                tasks = []
                for hostname in servers:
                    Servers.remove(hostname)
                    heartbeat_fail_count.pop(hostname, None)
                    tasks.append(remove_container(docker, hostname))

                await asyncio.gather(*tasks, return_exceptions=True)

            final_hostnames = Servers.getServerList()
        
        return jsonify({
        'message': {
            'N': len(Servers),
            'Servers': final_hostnames
        },
        'status': 'success'
        }), 200
    except Exception as e:
        print(e)   

@app.route('/read',methods=['GET'])
async def read_get():
    example_payload = {
        "stud_id" : { "low" : 1000 , "high" : 8889 },
    }

    return jsonify({
        "message": "Read Student Records",
        "payload_structure": example_payload,
        "status": "success"
    }), 200

@app.route('/read',methods=['POST'])
async def read():
    global pool
    await asyncio.sleep(0)
    try:
        payload: dict = await request.get_json()

        if payload is None:
            raise Exception('Payload in empty Use Get to find payload formate')
        
        stud_id = dict(payload.get('stud_id',{}))

        if not len(stud_id):
            raise Exception('Payload dont contain stud_id')
        
        low = int(stud_id.get('low',-1))
        high = int(stud_id.get('high',-1))

        if low ==-1 or high == -1 :
            raise Exception('stud_id dont contain low or high')
            
        if high < low :
            raise Exception('low is more than high which is practically impossible')
        
        shard_ids: list[str] = []
        shard_valid_ats: list[int] = []

        async with mutexLock:
            async with pool.acquire() as con:
                async with con.transaction():
                    async for record in con.cursor(
                        '''--sql
                        SELECT
                            shard_id,
                            valid_at
                        FROM
                            ShardT
                        WHERE
                            (stud_id_low <= ($2::INTEGER)) AND
                            (($1::INTEGER) < stud_id_low + shard_size)
                        FOR SHARE;
                        ''',
                            low, high):

                        shard_ids.append(record["shard_id"])
                        shard_valid_ats.append(record["valid_at"])  

                    if not len(shard_ids):
                        return jsonify({
                            'message':"No Entry Found",
                            'status' : "success"
                            }),200

                    data = []
                    new_tasks = []


                    async def read_get_wrapper(
                        session: aiohttp.ClientSession,
                        server_name: str,
                        json_payload: Dict
                    ):
                        
                        await asyncio.sleep(0)

                        async with session.get(f'http://{server_name}:5000/read',json=json_payload) as response:
                            await response.read()

                        return response
    
                    timeout = aiohttp.ClientTimeout(connect=REQUEST_TIMEOUT)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        for shard_id, shard_valid_at in zip(shard_ids, shard_valid_ats):
                            if len(shard_map[shard_id]) == 0:
                                continue

                            server_name = shard_map[shard_id].find(random.randint(100000,999999))

                            if server_name in Servers.getServerList():
                                new_tasks.append(asyncio.create_task(
                                    read_get_wrapper(
                                        session=session,
                                        server_name=server_name,
                                        json_payload={
                                            "shard": shard_id,
                                            "stud_id": stud_id,
                                            "valid_at": shard_valid_at
                                        }
                                    )
                                ))
                        
                        serv_response = await asyncio.gather(*new_tasks, return_exceptions=True)
                        serv_response = [None if isinstance(r, BaseException) else r for r in serv_response]
                        
                    for r in serv_response:
                        if r is None or r.status != 200:
                            raise Exception('Failed to read data entry')
                            
                        _r = dict(await r.json())
                        data.extend(_r["data"])
                
        return jsonify({
            'shards_queried': shard_ids,
            'data': data,
            'status': 'success'
        }), 200
    except Exception as e:
        return jsonify(err_payload(e)), 400

@app.route('/write',methods=['GET'])
async def write_get():
    example_payload = {
        "data" : [
            { "stud_id":2255, "stud_name":"GHI" , "stud_marks":27},
            {"stud_id":3524,"stud_name":"JKBFSFS","stud_marks":56}
        ],
    }

    return jsonify({
        "message": "Write Student Records",
        "payload_structure": example_payload,
        "status": "success"
    }), 200

@app.route('/write',methods=['POST'])
async def write():
    global pool
    await asyncio.sleep(0)
    try:
        payload: dict = await request.get_json()

        if payload is None:
            raise Exception('Payload in empty Use Get to find payload formate')
        
        data : List[Dict] = list(payload.get("data",[]))

        if not len(data):
            raise Exception('Payload dont contain stud_id')

        for d in data:
            if not all(k in d.keys()
                       for k in
                       ["stud_id", "stud_name", "stud_marks"]):
                raise Exception('Data is invalid')
            
        shard_data: Dict[str, Tuple[List[Dict[str, Any]], int]] = {}
        
        async with mutexLock:
            async with pool.acquire() as con:
                async with con.transaction():
                    get_shard_id_stmt = await con.prepare(
                        '''--sql
                        SELECT
                            shard_id
                        FROM
                            ShardT
                        WHERE
                            (stud_id_low <= ($1::INTEGER)) AND
                            (($1::INTEGER) < stud_id_low + shard_size);
                        ''')

                    get_valid_at_stmt = await con.prepare(
                        '''--sql
                        SELECT
                            valid_at
                        FROM
                            ShardT
                        WHERE
                            shard_id = $1::TEXT
                        FOR UPDATE;
                        ''')

                    update_shard_info_stmt = await con.prepare(
                        '''--sql
                        UPDATE
                            ShardT
                        SET
                            valid_at = ($1::INTEGER)
                        WHERE
                            shard_id = ($2::TEXT);
                        ''')

                    for entry in data:
                        stud_id = int(entry["stud_id"])
                        record = await get_shard_id_stmt.fetchrow(stud_id)

                        if record is None:
                            raise Exception(f'Shard for {stud_id = } does not exist')

                        shard_id: str = record["shard_id"]

                        if shard_id not in shard_data:
                            shard_data[shard_id] = ([], 0)

                        shard_data[shard_id][0].append(entry)

                    for shard_id in sorted(shard_data.keys()):
                        shard_valid_at: int = await get_valid_at_stmt.fetchval(shard_id)
                        shard_data[shard_id] = (shard_data[shard_id][0],shard_valid_at)

                    async def write_wrapper(
                        session: aiohttp.ClientSession,
                        server_name: str,
                        json_payload: Dict
                    ):
                        await asyncio.sleep(0)

                        async with session.post(f'http://{server_name}:5000/write',json=json_payload) as response:
                            await response.read()

                        return response

                    for shard_id in shard_data:
                        server_names = shard_map[shard_id].getServerList()
                        timeout = aiohttp.ClientTimeout(
                            connect=REQUEST_TIMEOUT)
                        async with aiohttp.ClientSession(timeout=timeout) as session:
                            tasks = [asyncio.create_task(
                                write_wrapper(
                                    session=session,
                                    server_name=server_name,
                                    json_payload={
                                        "shard": shard_id,
                                        "data": shard_data[shard_id][0],
                                        "valid_at": shard_data[shard_id][1]
                                    }
                                )
                            ) for server_name in server_names]

                            serv_response = await asyncio.gather(*tasks, return_exceptions=True)
                            serv_response = [None if isinstance(r, BaseException)
                                             else r for r in serv_response]

                        max_valid_at = shard_data[shard_id][1]
                        for r in serv_response:
                            if r is None or r.status != 200:
                                raise Exception(
                                    'Failed to write all data entries')

                            resp = dict(await r.json())
                            cur_valid_at = int(resp["valid_at"])
                            max_valid_at = max(max_valid_at, cur_valid_at)

                        await update_shard_info_stmt.executemany([(max_valid_at, shard_id)]) 

        return jsonify({
            'message': f"{len(data)} data entries added",
            'status': 'success'
        }), 200
                    
    except Exception as e:
        return jsonify(err_payload(e)),400

@app.route('/update',methods=['GET'])
async def update_get():
    example_payload = {
        "stud_id" : "2255",
        "data" : {
            "stud_id" : 2255,
            "stud_name" : "GHI",
            "stud_marks" : 30
        }
    }

    return jsonify({
        "message": "Update Student Records",
        "payload_structure": example_payload,
        "status": "success"
    }), 200

@app.route('/update',methods=['PUT'])
async def update():
    global pool
    await asyncio.sleep(0)

    try:
        payload: dict = await request.get_json()
        
        if payload is None: 
            raise Exception('Payload Not Present')

        stud_id = int(payload.get('stud_id', -1))

        if stud_id == -1:
            raise Exception("stud_id not in Payload")

        data = dict(payload.get('data',{}))

        if not len(data):
            raise Exception('data not found')

        if not all(k in data.keys()
                   for k in
                   ["stud_id", "stud_name", "stud_marks"]):
            raise Exception('Data formate mismatch')
        
        if stud_id != data["stud_id"]:
            raise Exception("Cannot change stud_id field")

        async with mutexLock:
            async with pool.acquire() as con:
                async with con.transaction():
                    response = await con.fetchrow(
                        '''--sql
                        SELECT
                            shard_id,
                            valid_at
                        FROM
                            ShardT
                        WHERE
                            (stud_id_low <= ($1::INTEGER)) AND
                            (($1::INTEGER) < stud_id_low + shard_size)
                        FOR UPDATE;
                        ''',
                        stud_id
                    )

                    if response is None:
                        raise Exception('No Entry with Stud id : `{stud_id}')

                    shard_id: str = response["shard_id"]
                    shard_valid_at: int = response["valid_at"]

                    server_names = shard_map[shard_id].getServerList()
                    valid_at = shard_valid_at

                    async def update_wrapper(
                        session: aiohttp.ClientSession,
                        server_name: str,
                        json_payload: dict
                    ):
                        await asyncio.sleep(0)

                        async with session.post(f'http://{server_name}:5000/update',json=json_payload) as response:
                            await response.read()

                        return response

                    timeout = aiohttp.ClientTimeout(connect=REQUEST_TIMEOUT)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        tasks = [asyncio.create_task(
                            update_wrapper(
                                session=session,
                                server_name=server_name,
                                json_payload={
                                    "shard": shard_id,
                                    "stud_id": stud_id,
                                    "data": data,
                                    "valid_at": shard_valid_at
                                }
                            )
                        ) for server_name in server_names]

                        serv_response = await asyncio.gather(*tasks, return_exceptions=True)
                        serv_response = [None if isinstance(r, BaseException)
                                            else r for r in serv_response]

                    valid_at = shard_valid_at

                    for r in serv_response:
                        if r is None or r.status != 200:
                            raise Exception('Failed to update data entry')

                        resp = dict(await r.json())
                        cur_valid_at = int(resp["valid_at"])
                        valid_at = max(valid_at, cur_valid_at)


                    await con.execute(
                        '''--sql
                        UPDATE
                            ShardT
                        SET
                            valid_at = ($1::INTEGER)
                        WHERE
                            shard_id = ($2::TEXT)
                        ''',
                        valid_at,
                        shard_id,
                    )
                    
        return jsonify({
            'message': f"Data entry for stud_id: {stud_id} updated",
            'status': 'success'
        }), 200

    except Exception as e:
        return jsonify(err_payload(e)),200
        
@app.route('/del',methods=['GET'])
async def del_get():
    example_payload = {
        "stud_id" : 2255,
    }

    return jsonify({
        "message": "Delete Student Records",
        "payload_structure": example_payload,
        "status": "success"
    }), 200

@app.route('/del',methods=['DELETE'])
async def dele():
    global pool
    await asyncio.sleep(0)
    try:
        payload: dict = await request.get_json()

        if payload is None:
            raise Exception('Payload in empty Use Get to find payload formate')
        
        stud_id = int(payload.get('stud_id',-1))

        if stud_id == -1:
            raise Exception('Payload dont contain stud_id')

        async with mutexLock:
            async with pool.acquire() as con:
                async with con.transaction():
                    record = await con.fetchrow(
                        '''--sql
                        SELECT
                            shard_id,
                            valid_at
                        FROM
                            ShardT
                        WHERE
                            (stud_id_low <= ($1::INTEGER)) AND
                            (($1::INTEGER) < stud_id_low + shard_size)
                        FOR UPDATE;
                        ''',
                        stud_id)

                    if record is None:
                        raise Exception(f'stud_id {stud_id} does not exist')

                    shard_id: str = record["shard_id"]
                    shard_valid_at: int = record["valid_at"]

                    server_names = shard_map[shard_id].getServerList()
                    
                    async def del_wrapper(
                        session: aiohttp.ClientSession,
                        server_name: str,
                        json_payload: Dict
                    ):
                        await asyncio.sleep(0)

                        async with session.delete(f'http://{server_name}:5000/del',json=json_payload) as response:
                            await response.read()

                        return response
    
                    timeout = aiohttp.ClientTimeout(connect=REQUEST_TIMEOUT)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        tasks = [asyncio.create_task(
                            del_wrapper(
                                session=session,
                                server_name=server_name,
                                json_payload={
                                    "shard": shard_id,
                                    "stud_id": stud_id,
                                    "valid_at": shard_valid_at
                                }
                            )
                        ) for server_name in server_names]

                        serv_response = await asyncio.gather(*tasks, return_exceptions=True)
                        serv_response = [None if isinstance(r, BaseException)
                                            else r for r in serv_response]
                    
                    max_valid = shard_valid_at
                    for r in serv_response:
                        if r is None or r.status != 200:
                            raise Exception('Failed to delete data entry')

                        resp = dict(await r.json())
                        cur_valid_at = int(resp["valid_at"])
                        max_valid_at = max(max_valid, cur_valid_at)

                    await con.execute(
                        '''--sql
                        UPDATE
                            ShardT
                        SET
                            valid_at = ($1::INTEGER)
                        WHERE
                            shard_id = ($2::TEXT)
                        ''',
                        max_valid_at,
                        shard_id,
                    )
                        
        return jsonify({
            'message': f"Data entry with stud_id: {stud_id} removed",
            'status': 'success'
        }), 200
    except Exception as e:
        return jsonify(err_payload(e)),400


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, use_reloader=False)