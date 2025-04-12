from quart import Blueprint, request, jsonify
import asyncio
from ..loadBalancer import Servers, mutexLock, err_payload

write_bp = Blueprint('write', __name__)

@write_bp.route('/write', methods=['POST'])
async def write():
    """Write data entries to the distributed database."""
    try:
        payload = await request.get_json()
        if not payload or 'data' not in payload:
            raise Exception('Invalid payload. "data" is required.')

        data_entries = payload['data']
        if not isinstance(data_entries, list):
            raise Exception('"data" must be a list of entries.')

        async with mutexLock:  # Thread-safe access to Servers
            for entry in data_entries:
                stud_id = entry.get('Stud_id')
                if stud_id is None:
                    raise Exception('Each entry must have a "Stud_id".')

                shard_id = stud_id % Servers.shard_size
                server_name = Servers.find(shard_id)
                if server_name:
                    # Simulate writing data to the server
                    print(f"Writing {entry} to server {server_name}")

        return jsonify({
            "message": f"{len(data_entries)} Data entries added",
            "status": "success"
        }), 200
    except Exception as e:
        return jsonify(err_payload(e)), 400