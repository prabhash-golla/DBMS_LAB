from quart import Blueprint, request, jsonify
import asyncio
from ..loadBalancer import Servers, mutexLock, err_payload

read_bp = Blueprint('read', __name__)

@read_bp.route('/read', methods=['POST'])
async def read():
    """Read data entries from the distributed database based on a range of Stud_id."""
    try:
        payload = await request.get_json()
        if not payload or 'Stud_id' not in payload:
            raise Exception('Invalid payload. "Stud_id" range is required.')

        stud_id_range = payload['Stud_id']
        low, high = stud_id_range.get('low'), stud_id_range.get('high')
        if low is None or high is None:
            raise Exception('Both "low" and "high" values are required in Stud_id range.')

        shards_queried = []
        data = []

        async with mutexLock:  # Thread-safe access to Servers
            for stud_id in range(low, high + 1):
                shard_id = stud_id % Servers.shard_size
                server_name = Servers.find(shard_id)
                if server_name:
                    shards_queried.append(server_name)
                    # Simulate fetching data from the server
                    data.append({
                        "Stud_id": stud_id,
                        "Stud_name": f"Name-{stud_id}",
                        "Stud_marks": random.randint(20, 100)
                    })

        return jsonify({
            "shards_queried": list(set(shards_queried)),
            "data": data,
            "status": "success"
        }), 200
    except Exception as e:
        return jsonify(err_payload(e)), 400