import os
import sys
from quart import Quart, jsonify

app = Quart(__name__)

@app.route('/home', methods=['GET'])
async def home():
    serv_id = os.environ.get('SERVER_ID', '0')
    return jsonify({
        'message': f"Hello from Server: {serv_id}",
        'status': "successful"
    }), 200

@app.route('/heartbeat', methods=['GET'])
async def heartbeat():
    return '', 200 

if __name__ == '__main__':
    # port as input argument(default 5000)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000

    app.run(host='0.0.0.0', port=port, use_reloader=False)