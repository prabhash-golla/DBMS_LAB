from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from functools import wraps
from database.db_config import get_db_cursor, close_db_connection

# Create the blueprint
citizen_bp = Blueprint('citizen', __name__, url_prefix='/citizen')

# Decorator to ensure user is logged in as a citizen
def citizen_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('login'))
        
        if session.get('role') != 'citizen':
            flash('You must be logged in as a citizen to access this page', 'danger')
            return redirect(url_for('dashboard'))
            
        return f(*args, **kwargs)
    return decorated_function

@citizen_bp.route('/welfare-schemes')
@citizen_required
def welfare_schemes():
    user_id = session['user_id']
    
    conn, cur = get_db_cursor()
    
    # First get the citizen_id for this user
    cur.execute("SELECT citizen_id FROM citizens WHERE user_id = %s", (user_id,))
    citizen_result = cur.fetchone()
    
    if not citizen_result:
        flash('Citizen profile not found', 'danger')
        close_db_connection(conn, cur)
        return redirect(url_for('dashboard'))
    
    citizen_id = citizen_result[0]
    
    # Get enrolled schemes for this citizen
    cur.execute("""
        SELECT se.enrollment_id, ws.scheme_id, ws.name, ws.description, se.enrollment_date
        FROM scheme_enrollments se
        JOIN welfare_schemes ws ON se.scheme_id = ws.scheme_id
        WHERE se.citizen_id = %s
    """, (citizen_id,))
    
    enrolled_schemes = []
    for scheme in cur.fetchall():
        enrolled_schemes.append({
            'enrollment_id': scheme[0],
            'scheme_id': scheme[1],
            'name': scheme[2],
            'description': scheme[3],
            'enrollment_date': scheme[4]
        })
    
    # Get all available schemes
    cur.execute("SELECT scheme_id, name, description FROM welfare_schemes")
    
    all_schemes = []
    for scheme in cur.fetchall():
        # Check if citizen is already enrolled in this scheme
        is_enrolled = any(s['scheme_id'] == scheme[0] for s in enrolled_schemes)
        
        all_schemes.append({
            'scheme_id': scheme[0],
            'name': scheme[1],
            'description': scheme[2],
            'is_enrolled': is_enrolled
        })
    
    close_db_connection(conn, cur)
    
    return render_template(
        'citizen/welfare_schemes.html', 
        enrolled_schemes=enrolled_schemes,
        all_schemes=all_schemes
    )

@citizen_bp.route('/land-records')
@citizen_required
def land_records():
    user_id = session['user_id']
    
    conn, cur = get_db_cursor()
    
    # Get citizen_id
    cur.execute("SELECT citizen_id FROM citizens WHERE user_id = %s", (user_id,))
    citizen_result = cur.fetchone()
    
    if not citizen_result:
        flash('Citizen profile not found', 'danger')
        close_db_connection(conn, cur)
        return redirect(url_for('dashboard'))
    
    citizen_id = citizen_result[0]
    
    # Get land records for this citizen
    cur.execute("""
        SELECT land_id, area_acres, crop_type
        FROM land_records
        WHERE citizen_id = %s
    """, (citizen_id,))
    
    land_records = []
    for record in cur.fetchall():
        land_records.append({
            'land_id': record[0],
            'area': record[1],
            'crop_type': record[2]
        })
    
    close_db_connection(conn, cur)
    
    return render_template('citizen/land_records.html', land_records=land_records)

@citizen_bp.route('/vaccination-records')
@citizen_required
def vaccination_records():
    user_id = session['user_id']
    
    conn, cur = get_db_cursor()
    
    # Get citizen_id
    cur.execute("SELECT citizen_id FROM citizens WHERE user_id = %s", (user_id,))
    citizen_result = cur.fetchone()
    
    if not citizen_result:
        flash('Citizen profile not found', 'danger')
        close_db_connection(conn, cur)
        return redirect(url_for('dashboard'))
    
    citizen_id = citizen_result[0]
    
    # Get vaccination records
    cur.execute("""
        SELECT vaccination_id, vaccine_type, date_administered
        FROM vaccinations
        WHERE citizen_id = %s
        ORDER BY date_administered DESC
    """, (citizen_id,))
    
    vaccinations = []
    for record in cur.fetchall():
        vaccinations.append({
            'id': record[0],
            'vaccine_type': record[1],
            'date': record[2]
        })
    
    close_db_connection(conn, cur)
    
    return render_template(
        'citizen/vaccination_records.html', 
        vaccinations=vaccinations
    )

@citizen_bp.route('/village-info')
@citizen_required
def village_info():
    conn, cur = get_db_cursor()
    
    # Get village statistics
    village_stats = {}
    
    # Get population count
    try:
        cur.execute("SELECT COUNT(*) FROM citizens")
        village_stats['population'] = cur.fetchone()[0]
    except:
        village_stats['population'] = 0
    
    # Get household count
    try:
        cur.execute("SELECT COUNT(*) FROM households")
        village_stats['families'] = cur.fetchone()[0]
    except:
        village_stats['families'] = 0
    
    # Get total land area
    try:
        cur.execute("SELECT SUM(area_acres) FROM land_records")
        total_area = cur.fetchone()[0]
        village_stats['land_area'] = total_area if total_area else 0
    except:
        village_stats['land_area'] = 0
    
    # Get count of welfare schemes
    try:
        cur.execute("SELECT COUNT(*) FROM welfare_schemes")
        village_stats['schemes'] = cur.fetchone()[0]
    except:
        village_stats['schemes'] = 0
    
    close_db_connection(conn, cur)
    
    return render_template('citizen/village_info.html', village_stats=village_stats)