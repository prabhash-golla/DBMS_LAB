from quart import Blueprint, request, jsonify
from ..loadBalancer import Servers, mutexLock, err_payload

update_bp = Blueprint('update', __name__)

@update_bp.route('/update', methods=['PUT'])
async def update():
    """Update a particular data entry in the distributed database."""
    try:
        payload = await request.get_json()
        if not payload or 'Stud_id' not in payload or 'data' not in payload:
            raise Exception('Invalid payload. "Stud_id" and "data" are required.')

        stud_id = payload['Stud_id']
        data = payload['data']

        shard_id = stud_id % Servers.shard_size
        server_name = Servers.find(shard_id)
        if server_name:
            # Simulate updating data on the server
            print(f"Updating {data} for Stud_id {stud_id} on server {server_name}")

        return jsonify({
            "message": f"Data entry for Stud_id {stud_id} updated",
            "status": "success"
        }), 200
    except Exception as e:
        return jsonify(err_payload(e)), 400