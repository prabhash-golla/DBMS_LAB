import aiohttp
import asyncio
import os
import random
import sys
from aiodocker import Docker
from icecream import ic
from quart import Quart, request, jsonify
from colorama import Fore, Style
from ConsistentHashing import ConsistentHashMap
from utils import *
from asyncio import Lock

app = Quart(__name__)
mutexLock = Lock()

HASH_NUM = int(os.environ.get('HASH_NUM', 0))
DEBUG = False
ic.configureOutput(prefix='[LB] | ')
ic.disable()

Servers = ConsistentHashMap()
heartbeat_fail_count: dict[str, int] = {}
serv_id = 3
MAX_FAIL_COUNT = 5
HEARTBEAT_INTERVAL = 10
STOP_TIMEOUT = 5
REQUEST_TIMEOUT = 1
REQUEST_BATCH_SIZE = 10
DOCKER_TASK_BATCH_SIZE = 10

@app.route('/rep', methods=['GET'])
async def rep():
    global Servers
    async with mutexLock:
        return jsonify(ic({
            'message': {
                'N': len(Servers),
                'Servers': Servers.getServerList(),
            },
            'status': 'successful',
        })), 200

@app.route('/add', methods=['POST'])
async def add():
    global Servers, heartbeat_fail_count, serv_id
    await asyncio.sleep(0)
    try:
        payload: dict = await request.get_json()
        ic(payload)
        if payload is None:
            raise Exception('Payload is empty')
        n = int(payload.get('n', -1))
        hostnames: list[str] = list(payload.get('hostnames', []))
        if n <= 0:
            raise Exception('Number of servers to add must be greater than 0')
        if len(hostnames) > n:
            raise Exception('Length of hostname list is more than instances to add')
        if len(hostnames) != len(set(hostnames)):
            raise Exception('Hostname list contains duplicates')
        new_hostnames = set()
        while len(new_hostnames) < n - len(hostnames):
            new_hostnames.add(random_hostname())
        hostnames.extend(new_hostnames)
        async with mutexLock:
            if n > Servers.remaining():
                raise Exception(f'Insufficient slots. Only {Servers.remaining()} slots left')
            if not set(hostnames).isdisjoint(set(Servers.getServerList())):
                raise Exception(f'Hostnames {set(hostnames) & set(Servers.getServerList())} are already in Servers')
            ic("To add: ", hostnames)
            semaphore = asyncio.Semaphore(DOCKER_TASK_BATCH_SIZE)
            async def spawn_container(docker: Docker, serv_id: int, hostname: str):
                await asyncio.sleep(0)
                async with semaphore:
                    try:
                        container_config = {
                            'image': 'server:v1',
                            'detach': True,
                            'env': [f'SERVER_ID={serv_id}', 'DEBUG=true'],
                            'hostname': hostname,
                            'tty': True,
                        }
                        container = await docker.containers.create_or_replace(
                            name=hostname,
                            config=container_config,
                        )
                        my_net = await docker.networks.get('my_net')
                        await my_net.connect({'Container': container.id, 'EndpointConfig': {'Aliases': [hostname]}})
                        if DEBUG:
                            print(f'{Fore.LIGHTGREEN_EX}CREATE | Created container for {hostname}{Style.RESET_ALL}', file=sys.stderr)
                        await container.start()
                        if DEBUG:
                            print(f'{Fore.MAGENTA}SPAWN | Started container for {hostname}{Style.RESET_ALL}', file=sys.stderr)
                    except Exception as e:
                        if DEBUG:
                            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)
            async with Docker() as docker:
                tasks = []
                for hostname in hostnames:
                    Servers.add(hostname)
                    heartbeat_fail_count[hostname] = 0
                    serv_id += 1
                    tasks.append(spawn_container(docker, serv_id, hostname))
                await asyncio.gather(*tasks, return_exceptions=True)
            final_hostnames = Servers.getServerList()
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
    global Servers, heartbeat_fail_count
    await asyncio.sleep(0)
    try:
        payload: dict = await request.get_json()
        ic(payload)
        if payload is None:
            raise Exception('Payload is empty')
        n = int(payload.get('n', -1))
        hostnames: list[str] = list(payload.get('hostnames', []))
        if n <= 0:
            raise Exception('Number of servers to delete must be greater than 0')
        if n > len(Servers):
            raise Exception('Number of servers to delete must be less than or equal to number of Servers')
        if len(hostnames) > n:
            raise Exception('Length of hostname list is more than instances to delete')
        async with mutexLock:
            choices = set(Servers.getServerList())
            if not set(hostnames).issubset(choices):
                raise Exception(f'Hostnames {set(hostnames) - choices} are not in Servers')
            choices = list(choices - set(hostnames))
            random_hostnames = random.sample(choices, k=n - len(hostnames))
            hostnames.extend(random_hostnames)
            ic("To delete: ", hostnames)
            semaphore = asyncio.Semaphore(DOCKER_TASK_BATCH_SIZE)
            async def remove_container(docker: Docker, hostname: str):
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
                for hostname in hostnames:
                    Servers.remove(hostname)
                    heartbeat_fail_count.pop(hostname, None)
                    tasks.append(remove_container(docker, hostname))
                await asyncio.gather(*tasks, return_exceptions=True)
            final_hostnames = Servers.getServerList()
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
    global Servers
    await asyncio.sleep(0)
    try:
        request_id = random.randint(100000, 999999)
        ic(request_id)
        async with mutexLock:
            server_name = Servers.find(request_id)
        if server_name is None:
            raise Exception('No servers are available')
        ic(server_name)
        async def wrapper(session: aiohttp.ClientSession, server_name: str):
            await asyncio.sleep(0)
            async with session.get(f'http://{server_name}:5000/home') as response:
                await response.read()
            return response
        timeout = aiohttp.ClientTimeout(connect=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [asyncio.create_task(wrapper(session, server_name))]
            serv_response = await asyncio.gather(*tasks, return_exceptions=True)
            serv_response = serv_response[0] if not isinstance(serv_response[0], BaseException) else None
        if serv_response is None:
            raise Exception('Server did not respond')
        return jsonify(ic(await serv_response.json())), 200
    except Exception as e:
        if DEBUG:
            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)
        return jsonify(ic(err_payload(e))), 400

@app.route('/<path:path>')
async def catch_all(path):
    return jsonify(ic({
        'message': f'<Error> /{path} endpoint does not exist in server Servers',
        'status': 'failure'
    })), 400

@app.before_serving
async def my_startup():
    app.add_background_task(get_heartbeats)

@app.after_serving
async def my_shutdown():
    app.background_tasks.pop().cancel()
    semaphore = asyncio.Semaphore(DOCKER_TASK_BATCH_SIZE)
    async def wrapper(docker: Docker, server_name: str):
        await asyncio.sleep(0)
        async with semaphore:
            try:
                container = await docker.containers.get(server_name)
                await container.stop(timeout=STOP_TIMEOUT)
                await container.delete(force=True)
                if DEBUG:
                    print(f'{Fore.LIGHTYELLOW_EX}REMOVE | Deleted container for {server_name}{Style.RESET_ALL}', file=sys.stderr)
            except Exception as e:
                if DEBUG:
                    print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)
    async with Docker() as docker:
        tasks = [wrapper(docker, server_name) for server_name in Servers.getServerList()]
        await asyncio.gather(*tasks, return_exceptions=True)

async def get_heartbeats():
    global Servers, heartbeat_fail_count, serv_id
    if DEBUG:
        print(f'{Fore.CYAN}HEARTBEAT | Heartbeat background task started{Style.RESET_ALL}', file=sys.stderr)
    await asyncio.sleep(0)
    try:
        while True:
            async with mutexLock:
                if DEBUG:
                    print(f'{Fore.CYAN}HEARTBEAT | Checking heartbeat every {HEARTBEAT_INTERVAL} seconds{Style.RESET_ALL}', file=sys.stderr)
                hostnames = Servers.getServerList().copy()
            heartbeat_urls = [f'http://{server_name}:5000/heartbeat' for server_name in hostnames]
            timeout = aiohttp.ClientTimeout(connect=REQUEST_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                heartbeats = await gather_with_concurrency(session, REQUEST_BATCH_SIZE, *heartbeat_urls)
            await asyncio.sleep(0)
            semaphore = asyncio.Semaphore(DOCKER_TASK_BATCH_SIZE)
            async def flatline_wrapper(serv_id: int, server_name: str):
                await asyncio.sleep(0)
                async with semaphore:
                    try:
                        await handle_flatline(serv_id, server_name)
                    except Exception as e:
                        if DEBUG:
                            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)
            flatlines = []
            async with mutexLock:
                for i, response in enumerate(heartbeats):
                    if response is None or not response.status == 200:
                        heartbeat_fail_count[hostnames[i]] = heartbeat_fail_count.get(hostnames[i], 0) + 1
                        if heartbeat_fail_count[hostnames[i]] >= MAX_FAIL_COUNT:
                            serv_id += 1
                            flatlines.append(flatline_wrapper(serv_id, hostnames[i]))
                    else:
                        heartbeat_fail_count[hostnames[i]] = 0
                if flatlines:
                    await asyncio.gather(*flatlines, return_exceptions=True)
            await asyncio.sleep(HEARTBEAT_INTERVAL)
    except asyncio.CancelledError:
        if DEBUG:
            print(f'{Fore.CYAN}HEARTBEAT | Heartbeat background task stopped{Style.RESET_ALL}', file=sys.stderr)

async def handle_flatline(serv_id: int, hostname: str):
    await asyncio.sleep(0)
    if DEBUG:
        print(f'{Fore.LIGHTRED_EX}FLATLINE | Flatline of server replica {hostname} detected{Style.RESET_ALL}', file=sys.stderr)
    try:
        async with Docker() as docker:
            container_config = {
                'image': 'server:v1',
                'detach': True,
                'env': [f'SERVER_ID={serv_id}', 'DEBUG=true'],
                'hostname': hostname,
                'tty': True,
            }
            container = await docker.containers.create_or_replace(name=hostname, config=container_config)
            my_net = await docker.networks.get('my_net')
            await my_net.connect({'Container': container.id, 'EndpointConfig': {'Aliases': [hostname]}})
            await container.start()
            if DEBUG:
                print(f'{Fore.MAGENTA}RESPAWN | Started container for {hostname}{Style.RESET_ALL}', file=sys.stderr)
    except Exception as e:
        if DEBUG:
            print(f'{Fore.RED}ERROR | {e}{Style.RESET_ALL}', file=sys.stderr)

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    app.run(host='0.0.0.0', port=port, use_reloader=False, debug=DEBUG)
