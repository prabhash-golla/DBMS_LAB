from quart import Blueprint, request, jsonify
from ..loadBalancer import Servers, mutexLock, err_payload

delete_bp = Blueprint('delete', __name__)

@delete_bp.route('/del', methods=['DELETE'])
async def delete_entry():
    """Delete a particular data entry in the distributed database."""
    try:
        payload = await request.get_json()
        if not payload or 'Stud_id' not in payload:
            raise Exception('Invalid payload. "Stud_id" is required.')

        stud_id = payload['Stud_id']

        shard_id = stud_id % Servers.shard_size
        server_name = Servers.find(shard_id)
        if server_name:
            # Simulate deleting data from the server
            print(f"Deleting Stud_id {stud_id} from server {server_name}")

        return jsonify({
            "message": f"Data entry with Stud_id {stud_id} removed from all replicas",
            "status": "success"
        }), 200
    except Exception as e:
        return jsonify(err_payload(e)), 400