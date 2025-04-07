import os
import sys
from quart import Quart, jsonify

# Initialize the Quart web application
app = Quart(__name__)

@app.route('/home', methods=['GET'])
async def home():
    """
    Home route for the server.

    This endpoint returns a JSON response containing a server ID and a success status. 
    The server ID is fetched from the environment variable 'SERVER_ID', and defaults 
    to '0' if not set.

    Returns:
        JSON response with message containing the server ID and status.
    """
    # Fetch the server ID from environment variables or default to '0'
    serv_id = os.environ.get('SERVER_ID', '0')
    
    # Return a JSON response with the server ID and status
    return jsonify({
        'message': f"Hello from Server: {serv_id}",
        'status': "successful"
    }), 200

@app.route('/heartbeat', methods=['GET'])
async def heartbeat():
    """
    Heartbeat route to check server health.

    This is a simple endpoint that responds with an HTTP status code 200 to indicate
    the server is running and responsive. It's often used for health checks in 
    load balancers or monitoring systems.

    Returns:
        HTTP 200 status code with an empty response body.
    """
    return '', 200 

if __name__ == '__main__':
    """
    Main entry point for the Quart web application.

    This block is executed when the script is run directly. It checks if a port is passed 
    as a command-line argument, and if not, defaults to port 5000. The application is 
    then started on all available network interfaces (0.0.0.0) and the specified port.
    
    The 'use_reloader=False' is set to prevent the application from restarting in debug mode 
    (useful when running in production).
    """
    # Read the port number from command line arguments, default to 5000 if not provided
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000

    # Run the application on all interfaces and the specified port
    app.run(host='0.0.0.0', port=port, use_reloader=False)
