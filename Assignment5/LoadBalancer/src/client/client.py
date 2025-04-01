import sys
import signal
import requests
import asyncio
import aiohttp
import matplotlib.pyplot as plt
from pprint import pp
from time import time

url = 'http://127.0.0.1:5001'

def signal_handler(sig, frame):
    print('Exiting...')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# handles all server endpoints(add, del, rep)
def make_request(endpoint: str, payload=None):
    request_funcs = {
        "add": requests.post,
        "rm": requests.delete,
        "rep": requests.get
    }
    
    response = request_funcs[endpoint](f'{url}/{endpoint}', json=payload)
    return f'Response: {response.text} | Code: {response.status_code}'

# load testing
async def gather_with_concurrency(
    session: aiohttp.ClientSession,
    batch: int,
    *urls: str
):
    semaphore = asyncio.Semaphore(batch)
    
    async def fetch(url: str):
        async with semaphore:
            try:
                async with session.get(url) as response:
                    await response.read()
                await asyncio.sleep(0)
                return response
            except Exception as e:
                print(f"Error fetching {url}: {e}")
                return None
    
    tasks = [fetch(url) for url in urls]
    return [None if isinstance(r, BaseException) 
            else r for r in 
            await asyncio.gather(*tasks, return_exceptions=True)]

# main testing function
async def tester(server_count=3):
    print(f"Testing with {server_count} servers at {url} for 10000 requests")
    
    N = server_count
    counts = {k: 0 for k in range(N+1)}
    counts[0] = 0 
 
    async with aiohttp.ClientSession() as session:
        responses = await gather_with_concurrency(
            session, 1000, 
            *[f'{url}/home' for _ in range(10000)]
        )
    
    for response in responses:
        if response is None or not response.status == 200:
            counts[0] += 1
            continue
            
        try:
            payload = await response.json()
            serv_id = int(payload.get('message', '').split(':')[-1].strip())
            
            if serv_id is not None and 1 <= serv_id <= N:
                counts[serv_id] += 1
            else:
                counts[0] += 1
        except Exception as e:
            print(f"Error processing response: {e}")
            counts[0] += 1
    
    pp(counts)
    success_count = sum(counts[k] for k in range(1, N+1))
    total_count = success_count + counts[0]
    
    print(f"Success rate: {success_count/total_count*100:.2f}% ({success_count}/{total_count})")
    
    plt.figure(figsize=(10, 6))
    plt.bar(list(counts.keys()), list(counts.values()))
    plt.xlabel('Server ID (0 = errors)')
    plt.ylabel('Number of requests')
    plt.title(f'Load Test Results: 10,000 Requests to {server_count} Servers')
    
    for i, v in counts.items():
        plt.text(i, v + 5, str(v), ha='center')
    
    filename = f'../../plots/plot-{server_count}-{int(time())}.png'
    plt.savefig(filename)
    print(f"Plot saved as {filename}")
    
    return counts

async def main(server_count=3):
    return await tester(server_count=server_count)

def _raise_value_error(message):
    raise ValueError(message)

# parse i/p command
def parse_command(cmd: str):
    parts = cmd.strip().split()
    if not parts:
        raise ValueError("No command provided")

    cmd_map = {
        "ADD": lambda p: ('ADD', int(p[0]), p[1:]) if p else (_raise_value_error("Not enough arguments for ADD")),
        "DEL": lambda p: ('DEL', int(p[0]), p[1:]) if p else (_raise_value_error("Not enough arguments for DEL")),
        "REP": lambda _: ('REP',),
        "TEST": lambda p: ('TEST', {"server_count": int(p[0])}) if p else ('TEST', {}),
        "HELP": lambda _: ('HELP',),
        "QUIT": lambda _: ('QUIT',)
    }

    return cmd_map.get(parts[0].upper(), lambda _: ("UNKNOWN",))(parts[1:])

# for handling commands
def handle_command(cmd: str, *args):
    if cmd == 'ADD':
        return make_request("add", {'n': args[0], 'hostnames': args[1]})
    elif cmd == 'DEL':
        return make_request("rm", {'n': args[0], 'hostnames': args[1]})
    elif cmd == 'REP':
        return make_request("rep")
    elif cmd == 'TEST':
        asyncio.run(main(**args[0]))  # Running async function
        return "Test completed"
    elif cmd == 'HELP':
        return """Available commands:
  ADD n [hostnames...]    - Add n servers with optional hostnames
  DEL n [hostnames...]    - Delete n servers with optional hostnames
  REP                     - Get server report
  TEST n                  - Run load test with n servers
  HELP                    - Show this help message
  QUIT                    - Exit the program"""
    elif cmd == 'QUIT':
        sys.exit(0)
    else:
        return f"Unknown command: {cmd}"

# interactive mode
def interactive_mode():
    print("Server Load Testing Tool\nType HELP for available commands")

    while True:
        try:
            command = input("\nEnter command: ")
            cmd, *args = parse_command(command)
            print(handle_command(cmd, *args))
        except ValueError as e:
            print(f"Error: {e}")
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        if sys.argv[1].upper() == 'TEST':
            server_count = int(sys.argv[2]) if len(sys.argv) > 2 else 3
            asyncio.run(main(server_count=server_count))
    else:
        interactive_mode()