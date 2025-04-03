import sys
import signal
import requests
import asyncio
import aiohttp
import json
import matplotlib.pyplot as plt
from pprint import pp
from time import time

# Get the port number from command-line arguments, default to 5000 if not provided
port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
url = f'http://127.0.0.1:{port}'  # Use the port in the URL

# Signal handler to handle graceful termination when a SIGINT (Ctrl+C) signal is received
def signal_handler(sig, frame):
    print('Exiting...')
    sys.exit(0)

# Register the signal handler for SIGINT (Ctrl+C) interrupt
signal.signal(signal.SIGINT, signal_handler)

# Function to handle server endpoint requests (add, delete, report)
def make_request(endpoint: str, payload=None):
    """
    Make a request to the given server endpoint.

    Args:
        endpoint (str): The endpoint to call (e.g., "add", "rm", "rep").
        payload (dict, optional): Data to be sent with the request (for "add" and "rm" endpoints).

    Returns:
        str: The server's response along with the HTTP status code.
    """
    # Dictionary mapping endpoint names to their corresponding HTTP request methods
    request_funcs = {
        "add": requests.post,
        "rm": requests.delete,
        "rep": requests.get
    }
    
    # Make the appropriate HTTP request based on the endpoint
    response = request_funcs[endpoint](f'{url}/{endpoint}', json=payload)

    # Try to parse and pretty-print the JSON response
    try:
        json_response = response.json()
        pretty_json = json.dumps(json_response, indent=4)
        return f'\nResponse:\n{pretty_json}\n\nResponse Code: {response.status_code}\n'
    except:
        # If JSON parsing fails, return the original text
        return f'Response: {response.text} | Code: {response.status_code}'

# Load testing function with concurrency using asyncio and aiohttp
async def gather_with_concurrency(session: aiohttp.ClientSession, batch: int, *urls: str):
    """
    Execute multiple HTTP requests concurrently with a limit on the number of concurrent requests.

    Args:
        session (aiohttp.ClientSession): The session used to make HTTP requests.
        batch (int): The maximum number of concurrent requests.
        *urls (str): The list of URLs to send requests to.

    Returns:
        list: List of responses or None for requests that resulted in exceptions.
    """
    semaphore = asyncio.Semaphore(batch)  # Limit concurrency to the batch size
    
    # Function to fetch data from each URL
    async def fetch(url: str):
        async with semaphore:  # Ensure that no more than 'batch' requests run concurrently
            try:
                async with session.get(url) as response:
                    await response.read()  # Read the response content
                await asyncio.sleep(0)  # Yield control to the event loop to avoid blocking
                return response
            except Exception as e:
                print(f"Error fetching {url}: {e}")
                return None
    
    tasks = [fetch(url) for url in urls]  # Create a list of fetch tasks
    return [None if isinstance(r, BaseException) 
            else r for r in 
            await asyncio.gather(*tasks, return_exceptions=True)]  # Return results, handling exceptions

# Main testing function for load testing
async def tester(server_count=3):
    """
    Perform load testing by sending 10,000 requests to the specified number of servers.

    Args:
        server_count (int): The number of servers to test.

    Returns:
        dict: A dictionary of counts representing the number of requests handled by each server.
    """
    print(f"Testing with {server_count} servers at {url} for 10000 requests")
    
    N = server_count
    counts = {k: 0 for k in range(N+1)}  # Dictionary to count requests per server (including errors)
    counts[0] = 0  # Count for errors

    # Create an asynchronous session for making HTTP requests
    async with aiohttp.ClientSession() as session:
        responses = await gather_with_concurrency(
            session, 1000,  # Limit to 1000 concurrent requests at a time
            *[f'{url}/home' for _ in range(10000)]  # Send 10,000 requests to the /home endpoint
        )
    
    # Process the responses and count successful requests per server
    for response in responses:
        if response is None or not response.status == 200:
            counts[0] += 1  # Increment error count if no response or non-200 status code
            continue
            
        try:
            payload = await response.json()  # Parse the JSON response
            serv_id = int(payload.get('message', '').split(':')[-1].strip())  # Extract server ID
            
            # Increment the count for the appropriate server ID
            if serv_id is not None and 1 <= serv_id <= N:
                counts[serv_id] += 1
            else:
                counts[0] += 1  # Increment error count for invalid server ID
        except Exception as e:
            print(f"Error processing response: {e}")
            counts[0] += 1  # Increment error count on exception
    
    # Print the counts of requests handled by each server (and errors)
    pp(counts)
    
    # Calculate the success rate
    success_count = sum(counts[k] for k in range(1, N+1))
    total_count = success_count + counts[0]
    
    print(f"Success rate: {success_count/total_count*100:.2f}% ({success_count}/{total_count})")
    
    # Generate and save a bar chart of the results
    plt.figure(figsize=(10, 6))
    plt.bar(list(counts.keys()), list(counts.values()))
    plt.xlabel('Server ID (0 = errors)')
    plt.ylabel('Number of requests')
    plt.title(f'Load Test Results: 10,000 Requests to {server_count} Servers')
    
    for i, v in counts.items():
        plt.text(i, v + 5, str(v), ha='center')  # Display counts above each bar
    
    # Save the plot as a PNG file
    filename = f'../../plots/plot-{server_count}-{int(time())}.png'
    plt.savefig(filename)
    print(f"Plot saved as {filename}")
    
    return counts

# Main entry point for running the load test
async def main(server_count=3):
    return await tester(server_count=server_count)

# Raise ValueError with a custom message (used for error handling)
def _raise_value_error(message):
    raise ValueError(message)

# Parse the user command input
def parse_command(cmd: str):
    """
    Parse a command string into a command and its associated arguments.

    Args:
        cmd (str): The command string to parse.

    Returns:
        tuple: A tuple consisting of the command and its arguments.
    """
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

# Handle the parsed command and execute corresponding action
def handle_command(cmd: str, *args):
    """
    Execute the command based on the parsed input and return the appropriate response.

    Args:
        cmd (str): The command to execute.
        *args: Arguments associated with the command.

    Returns:
        str: The result of the command execution.
    """
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

# Interactive mode for the user to enter commands
def interactive_mode():
    """
    Start interactive mode where the user can enter commands and get responses.

    Available commands include adding/removing servers, running tests, and getting help.
    """
    print("Server Load Testing Tool\n")
    print("""Available commands:
             ADD n [hostnames...]    - Add n servers with optional hostnames
             DEL n [hostnames...]    - Delete n servers with optional hostnames
             REP                     - Get server report
             TEST n                  - Run load test with n servers
             HELP                    - Show this help message
             QUIT                    - Exit the program""")

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

# Main entry point
if __name__ == '__main__':
    """
    This is the main entry point of the program. It checks if 2 command-line arguments
    are provided and runs the appropriate function. If 0/1 arguments are given, it
    starts interactive mode.
    """
    if len(sys.argv) > 2:
        if sys.argv[2].upper() == 'TEST':
            server_count = int(sys.argv[3]) if len(sys.argv) > 3 else 3
            asyncio.run(main(server_count=server_count))  # Run the load test
    else:
        interactive_mode()  # Start the interactive mode
