from __future__ import annotations

import asyncio
import os
import sys
import asyncpg
from colorama import Fore, Style
from quart import Quart, jsonify, request, Response

# for the postgres conn
SERVER_ID = os.environ.get('SERVER_ID', '0')
HOSTNAME = os.environ.get('HOSTNAME', 'localhost')
DB_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
DB_PORT = int(os.environ.get('POSTGRES_PORT', 5432))
DB_USER = os.environ.get('POSTGRES_USER', 'postgres')
DB_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'postgres')
DB_NAME = os.environ.get('POSTGRES_DB_NAME', 'postgres')

pool: asyncpg.Pool[asyncpg.Record]

# helper functions
def err_payload(err: Exception):
    return {
        'message': f'<Error> {err}',
        'status': 'failure'
    }

async def rules(shard_id: str, valid_at: int) -> None:
    """
    Rule 1: Permanently delete records with:
        - created_at > valid_at
        - OR deleted_at is set and deleted_at <= valid_at

    Rule 2: Restore records where deleted_at > valid_at
    """
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute('''
                    DELETE FROM StudT
                    WHERE shard_id = $1
                      AND (created_at > $2
                           OR (deleted_at IS NOT NULL AND deleted_at <= $2));
                ''', shard_id, valid_at)

                await conn.execute('''
                    UPDATE StudT
                    SET deleted_at = NULL
                    WHERE shard_id = $1
                      AND deleted_at > $2;
                ''', shard_id, valid_at)
    except Exception as e:
        raise e
    

app = Quart(__name__)

# try to connect to the db
@app.before_serving
async def startup():
    global pool 
    try:
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

# if connected, close the connection
@app.after_serving
async def shutdown():
    if pool: 
        await pool.close()
        print(f'{Fore.YELLOW}INFO | Database connection closed.{Style.RESET_ALL}')


# sends a hello message to the client
@app.route('/home', methods=['GET'])
async def home():
    """ Send client with my server ID. """
    return jsonify({
        'message': f"Hello from {HOSTNAME}: {SERVER_ID}",
        'status': "successful"
    }), 200

# for heartbeat check
@app.route('/heartbeat', methods=['GET'])
async def heartbeat():
    """ Send heartbeat response. """
    return Response(status=200)

# this route gets the shards that the server must store and it configures the same
@app.route('/config', methods=["POST"])
async def server_config():
    """ Assigns the list of shards whose data the server must store """
    try:
        payload: dict = await request.get_json()
        shard_list: list = payload.get("shards", [])

        response_payload = {}
        async with pool.acquire() as conn:
            async with conn.transaction():
                stmt = await conn.prepare('''
                    INSERT INTO TermT (shard_id)
                    VALUES ($1::TEXT)
                    ON CONFLICT (shard_id) DO NOTHING;
                ''')
                await stmt.executemany([(shard,) for shard in shard_list])
        response_payload['status'] = 'success'
        return jsonify(response_payload), 200
    except Exception as e:
        return jsonify(err_payload(e)), 400

# this route gets the shards that the server must return
@app.route('/copy', methods=['GET'])
async def copy():
    """Returns all data entries corresponding to the requested shard tables."""
    try:
        req_data = await request.get_json()
        shards = req_data.get('shards', [])
        valid_at = req_data.get('valid_at', [])

        if not shards:
            raise ValueError("Shard list cannot be empty.")
        if len(shards) != len(valid_at):
            raise ValueError("Number of shards and valid_at entries must match.")

        shard_data = {shard: [] for shard in shards}

        async with pool.acquire() as conn:
            async with conn.transaction():
                rule_tasks = [
                    asyncio.create_task(rules(shard, ts))
                    for shard, ts in zip(shards, valid_at)
                ]
                rule_results = await asyncio.gather(*rule_tasks, return_exceptions=True)

                for idx, result in enumerate(rule_results):
                    if isinstance(result, Exception):
                        raise RuntimeError(f"rules() failed for shard '{shards[idx]}': {result}")

                query = '''
                    SELECT Stud_id, Stud_name, Stud_marks
                    FROM StudT
                    WHERE shard_id = $1::TEXT
                    AND created_at <= $2::INTEGER;
                '''
                stmt = await conn.prepare(query)

                async def fetch_records(shard_id, valid_time):
                    async for row in stmt.cursor(shard_id, valid_time):
                        shard_data[shard_id].append(dict(row))

                fetch_tasks = [
                    asyncio.create_task(fetch_records(shard, ts))
                    for shard, ts in zip(shards, valid_at)
                ]
                await asyncio.gather(*fetch_tasks)

        shard_data['status'] = 'success'
        return jsonify(shard_data), 200

    except Exception as ex:
        return jsonify(err_payload(ex)), 400

# reads the data from the database
@app.route('/read', methods=['GET'])
async def read():
    """Fetches student records based on shard, time, and ID range."""
    try:
        req_data: dict = await request.get_json()

        shard_id = str(req_data.get('shard', '')).strip()
        valid_at = int(req_data.get('valid_at', -1))
        id_range = req_data.get('stud_id', {})

        if not shard_id:
            raise ValueError("Missing 'shard' field.")
        if not all(k in id_range for k in ['low', 'high']):
            raise ValueError("Missing 'low' or 'high' in student ID range.")

        low_id = int(id_range['low'])
        high_id = int(id_range['high'])

        result = {'data': [], 'status': 'success'}

        async with pool.acquire() as conn:
            async with conn.transaction():
                await rules(shard_id, valid_at)

                stmt = '''
                    SELECT Stud_id, Stud_name, Stud_marks
                    FROM StudT
                    WHERE shard_id = $1
                      AND stud_id BETWEEN $2 AND $3
                      AND created_at <= $4;
                '''

                async for row in conn.cursor(stmt, shard_id, low_id, high_id, valid_at):
                    result['data'].append(dict(row))

        return jsonify(result), 200

    except Exception as err:
        return jsonify(err_payload(err)), 400

# write data to the database
@app.route('/write', methods=['POST'])
async def write():
    """Insert new student entries into the shard."""
    try:
        req_data: dict = await request.get_json()
        shard_id = str(req_data.get('shard', '')).strip()
        data_rows = list(req_data.get('data', []))
        valid_at = int(req_data.get('valid_at', -1))
        is_admin = str(req_data.get('admin', 'false')).lower() == 'true'

        if not shard_id:
            raise ValueError("Missing shard ID.")
        if not data_rows:
            raise ValueError("Data list must not be empty.")

        student_ids = []
        for entry in data_rows:
            if not all(field in entry for field in ("stud_id", "stud_name", "stud_marks")):
                raise ValueError("Each entry must include 'stud_id', 'stud_name', and 'stud_marks'.")
            student_ids.append(entry["stud_id"])

        async with pool.acquire() as conn:
            async with conn.transaction():
                if is_admin:
                    curr_valid_at = valid_at
                else:
                    await rules(shard_id, valid_at)

                    duplicates = await conn.fetchval('''
                        SELECT COUNT(*)
                        FROM StudT
                        WHERE stud_id = ANY($1::INTEGER[])
                          AND shard_id = $2::TEXT
                          AND deleted_at IS NULL;
                    ''', student_ids, shard_id)

                    if duplicates > 0:
                        raise ValueError(f"Duplicate stud_id(s) found in shard {shard_id}.")

                    current_term = await conn.fetchval('''
                        SELECT term
                        FROM TermT
                        WHERE shard_id = $1::TEXT;
                    ''', shard_id)

                    if current_term is None:
                        raise ValueError(f"Term info not found for shard {shard_id}.")

                    curr_valid_at = max(current_term, valid_at) + 1

                insert_stmt = await conn.prepare('''
                    INSERT INTO StudT (stud_id, stud_name, stud_marks, shard_id, created_at)
                    VALUES ($1, $2, $3, $4, $5);
                ''')

                await insert_stmt.executemany([
                    (record['stud_id'], record['stud_name'], record['stud_marks'], shard_id, curr_valid_at)
                    for record in data_rows
                ])

                await conn.execute('''
                    UPDATE TermT
                    SET term = $1
                    WHERE shard_id = $2;
                ''', curr_valid_at, shard_id)

        result = {
            "message": "Data entries added successfully.",
            "valid_at": curr_valid_at,
            "status": "success"
        }
        return jsonify(result), 200

    except Exception as err:
        return jsonify(err_payload(err)), 400

# update existing student entry
@app.route('/update', methods=['POST'])
async def update():
    """Update an existing student record with new data."""
    try:
        req_data: dict = await request.get_json()
        shard_id = str(req_data.get('shard', '')).strip()
        stud_id = int(req_data.get('stud_id', -1))
        valid_at = int(req_data.get('valid_at', -1))
        new_data = dict(req_data.get('data', {}))

        if not shard_id:
            raise ValueError("Missing shard ID.")
        if stud_id == -1:
            raise ValueError("Missing student ID.")
        if not new_data or not all(field in new_data for field in ("stud_id", "stud_name", "stud_marks")):
            raise ValueError("New data must include 'stud_id', 'stud_name', and 'stud_marks'.")
        if new_data["stud_id"] != stud_id:
            raise ValueError("Mismatch between root stud_id and data['stud_id'].")

        async with pool.acquire() as conn:
            async with conn.transaction():
                await rules(shard_id, valid_at)

                existing = await conn.fetchrow('''
                    SELECT created_at
                    FROM StudT
                    WHERE stud_id = $1
                      AND shard_id = $2;
                ''', stud_id, shard_id)

                if not existing:
                    raise ValueError(f"No record found for stud_id {stud_id} in shard {shard_id}.")

                current_term = await conn.fetchval('''
                    SELECT term
                    FROM TermT
                    WHERE shard_id = $1;
                ''', shard_id)

                if current_term is None:
                    raise ValueError(f"Term not set for shard {shard_id}.")

                next_term = max(current_term, valid_at) + 1

                # fake delete old record
                await conn.execute('''
                    UPDATE StudT
                    SET deleted_at = $1
                    WHERE stud_id = $2
                      AND shard_id = $3
                      AND created_at <= $4;
                ''', next_term, stud_id, shard_id, valid_at)

                # insert new record
                await conn.execute('''
                    INSERT INTO StudT (stud_id, stud_name, stud_marks, shard_id, created_at)
                    VALUES ($1, $2, $3, $4, $5);
                ''', new_data["stud_id"], new_data["stud_name"], new_data["stud_marks"], shard_id, next_term + 1)

                await conn.execute('''
                    UPDATE TermT
                    SET term = $1
                    WHERE shard_id = $2;
                ''', next_term + 1, shard_id)

        response = {
            "message": f"Student {stud_id} updated successfully.",
            "valid_at": next_term + 1,
            "status": "success"
        }
        return jsonify(response), 200

    except Exception as err:
        return jsonify(err_payload(err)), 400

# delete existing student entry
@app.route('/del', methods=['DELETE'])
async def delete():
    """Soft delete a student record from the database."""
    try:
        req_data: dict = await request.get_json()
        shard_id = str(req_data.get('shard', '')).strip()
        stud_id = int(req_data.get('stud_id', -1))
        valid_at = int(req_data.get('valid_at', -1))

        if not shard_id:
            raise ValueError("Missing shard ID.")
        if stud_id == -1:
            raise ValueError("Missing student ID.")

        async with pool.acquire() as conn:
            async with conn.transaction():
                await rules(shard_id, valid_at)

                existing = await conn.fetchrow('''
                    SELECT created_at
                    FROM StudT
                    WHERE stud_id = $1
                      AND shard_id = $2
                      AND deleted_at IS NULL;
                ''', stud_id, shard_id)

                if not existing:
                    raise ValueError(f"Student ID {stud_id} not found or already deleted in shard {shard_id}.")

                current_term = await conn.fetchval('''
                    SELECT term
                    FROM TermT
                    WHERE shard_id = $1;
                ''', shard_id)

                if current_term is None:
                    raise ValueError(f"Term not set for shard {shard_id}.")

                next_term = max(current_term, valid_at) + 1

                result = await conn.execute('''
                    UPDATE StudT
                    SET deleted_at = $1
                    WHERE stud_id = $2
                      AND shard_id = $3
                      AND created_at <= $4;
                ''', next_term, stud_id, shard_id, valid_at)

                if result == 'UPDATE 0':
                    raise ValueError(f"Failed to delete stud_id {stud_id} at valid_at {valid_at}.")

                await conn.execute('''
                    UPDATE TermT
                    SET term = $1
                    WHERE shard_id = $2;
                ''', next_term, shard_id)

        response = {
            "message": f"Student {stud_id} marked as deleted.",
            "valid_at": next_term,
            "status": "success"
        }
        return jsonify(response), 200

    except Exception as err:
        return jsonify(err_payload(err)), 400


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    host = '0.0.0.0'
    print(f'{Fore.CYAN}INFO | Starting server on {host}:{port}{Style.RESET_ALL}')
    app.run(host=host, port=port, use_reloader=False)