from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from functools import wraps
from database.db_config import get_db_cursor, close_db_connection

# Create the monitor blueprint
monitor_bp = Blueprint('monitor', __name__, url_prefix='/monitor')

# Import the role_required decorator
def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page', 'warning')
                return redirect(url_for('login'))
            
            if 'role' not in session:
                flash('Access denied', 'danger')
                return redirect(url_for('index'))
                
            if session['role'] not in allowed_roles:
                flash('You do not have permission to access this page', 'danger')
                return redirect(url_for('dashboard'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Dashboard route for government monitors
@monitor_bp.route('/dashboard')
@role_required(['admin', 'government_monitor'])
def monitor_dashboard():
    return render_template('monitor/dashboard.html')

# Population Reports route
@monitor_bp.route('/population')
@role_required(['admin', 'government_monitor'])
def population_reports():
    conn, cur = get_db_cursor()
    try:
        # Get statistics for different event types
        cur.execute("""
            SELECT event_type, COUNT(*) as count
            FROM census_data
            GROUP BY event_type
            ORDER BY count DESC
        """)
        event_stats = cur.fetchall()
        
        # Get recent census activity
        cur.execute("""
            SELECT cd.event_type, cd.event_date, 
                   c.name AS citizen_name, h.address
            FROM census_data cd
            JOIN citizens c ON cd.citizen_id = c.citizen_id
            JOIN households h ON cd.household_id = h.household_id
            ORDER BY cd.event_date DESC
            LIMIT 10
        """)
        recent_activity = cur.fetchall()
        
        # Get population statistics by gender
        cur.execute("""
            SELECT gender, COUNT(*) as count
            FROM citizens
            GROUP BY gender
        """)
        gender_stats = cur.fetchall()
        
        # Get household statistics
        cur.execute("""
            SELECT COUNT(*) as household_count,
                   AVG(CAST((SELECT COUNT(*) FROM citizens WHERE household_id = h.household_id) AS FLOAT)) as avg_size
            FROM households h
        """)
        household_stats = cur.fetchone()
        
        # Format data for template
        statistics = {
            'event_stats': [{'type': stat[0], 'count': stat[1]} for stat in event_stats],
            'recent_activity': [{'type': act[0], 'date': act[1], 'name': act[2], 'address': act[3]} for act in recent_activity],
            'gender_stats': [{'gender': stat[0], 'count': stat[1]} for stat in gender_stats],
            'household_count': household_stats[0],
            'avg_household_size': round(household_stats[1], 2) if household_stats[1] else 0
        }
        
        return render_template('monitor/population_reports.html', statistics=statistics)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

# Agricultural Statistics route
@monitor_bp.route('/agriculture')
@role_required(['admin', 'government_monitor'])
def agricultural_statistics():
    conn, cur = get_db_cursor()
    try:
        # Get total agricultural land
        cur.execute("""
            SELECT SUM(area_acres) as total_area
            FROM land_records
        """)
        total_area = cur.fetchone()[0] or 0
        
        # Get land by crop type
        cur.execute("""
            SELECT crop_type, COUNT(*) as field_count, SUM(area_acres) as total_area
            FROM land_records
            GROUP BY crop_type
            ORDER BY total_area DESC
        """)
        crop_stats = cur.fetchall()
        
        # Get top landowners
        cur.execute("""
            SELECT c.name, SUM(l.area_acres) as total_area
            FROM land_records l
            JOIN citizens c ON l.citizen_id = c.citizen_id
            GROUP BY c.name
            ORDER BY total_area DESC
            LIMIT 10
        """)
        top_landowners = cur.fetchall()
        
        # Format data for template
        statistics = {
            'total_area': round(total_area, 2),
            'crop_stats': [{'crop_type': stat[0] or 'Unspecified', 'field_count': stat[1], 'total_area': round(stat[2], 2)} for stat in crop_stats],
            'top_landowners': [{'name': owner[0], 'total_area': round(owner[1], 2)} for owner in top_landowners]
        }
        
        return render_template('monitor/agricultural_statistics.html', statistics=statistics)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

# Welfare Scheme Analytics route
@monitor_bp.route('/welfare')
@role_required(['admin', 'government_monitor'])
def welfare_scheme_analytics():
    conn, cur = get_db_cursor()
    try:
        # Get all welfare schemes with enrollment counts
        cur.execute("""
            SELECT ws.scheme_id, ws.name, ws.description, 
                   COUNT(se.enrollment_id) as enrollment_count
            FROM welfare_schemes ws
            LEFT JOIN scheme_enrollments se ON ws.scheme_id = se.scheme_id
            GROUP BY ws.scheme_id, ws.name, ws.description
            ORDER BY enrollment_count DESC
        """)
        schemes = cur.fetchall()
        
        # Get total number of enrollments directly from the scheme_enrollments table
        cur.execute("""
            SELECT COUNT(*) FROM scheme_enrollments
        """)
        total_enrollments = cur.fetchone()[0] or 0
        
        # Get total number of schemes
        cur.execute("""
            SELECT COUNT(*) FROM welfare_schemes
        """)
        scheme_count = cur.fetchone()[0] or 0
        
        # Calculate average enrollments per scheme
        avg_enrollments = 0
        if scheme_count > 0:
            avg_enrollments = round(total_enrollments / scheme_count, 1)
        
        # Get enrollment demographics by gender
        cur.execute("""
            SELECT ws.name, c.gender, COUNT(*) as count
            FROM scheme_enrollments se
            JOIN citizens c ON se.citizen_id = c.citizen_id
            JOIN welfare_schemes ws ON se.scheme_id = ws.scheme_id
            GROUP BY ws.name, c.gender
            ORDER BY ws.name, c.gender
        """)
        gender_demographics = cur.fetchall()
        
        # Get recent enrollments
        cur.execute("""
            SELECT ws.name, se.enrollment_date, c.name, c.gender
            FROM scheme_enrollments se
            JOIN citizens c ON se.citizen_id = c.citizen_id
            JOIN welfare_schemes ws ON se.scheme_id = ws.scheme_id
            ORDER BY se.enrollment_date DESC
            LIMIT 10
        """)
        recent_enrollments = cur.fetchall()
        
        # Format data for template
        statistics = {
            'schemes': [{'id': scheme[0], 'name': scheme[1], 'description': scheme[2], 'count': scheme[3]} for scheme in schemes],
            'total_enrollments': total_enrollments,
            'avg_enrollments': avg_enrollments,
            'gender_demographics': [{'scheme': demo[0], 'gender': demo[1], 'count': demo[2]} for demo in gender_demographics],
            'recent_enrollments': [{'scheme': enroll[0], 'date': enroll[1], 'name': enroll[2], 'gender': enroll[3]} for enroll in recent_enrollments]
        }

        
        return render_template('monitor/welfare_analytics.html', statistics=statistics)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

# Health Metrics route
@monitor_bp.route('/health')
@role_required(['admin', 'government_monitor'])
def health_metrics():
    conn, cur = get_db_cursor()
    try:
        # Get statistics for different vaccine types
        cur.execute("""
            SELECT vaccine_type, COUNT(*) as count
            FROM vaccinations
            GROUP BY vaccine_type
            ORDER BY count DESC
        """)
        vaccine_stats = cur.fetchall()
        
        # Get vaccination counts by month
        cur.execute("""
            SELECT TO_CHAR(date_administered, 'YYYY-MM') as month, COUNT(*) as count
            FROM vaccinations
            GROUP BY month
            ORDER BY month DESC
            LIMIT 12
        """)
        monthly_stats = cur.fetchall()
        
        # Get recent vaccination activity
        cur.execute("""
            SELECT v.vaccine_type, v.date_administered, 
                   c.name AS citizen_name, c.dob
            FROM vaccinations v
            JOIN citizens c ON v.citizen_id = c.citizen_id
            ORDER BY v.date_administered DESC
            LIMIT 10
        """)
        recent_activity = cur.fetchall()
        
        # Get age group statistics
        cur.execute("""
            SELECT 
                CASE 
                    WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, c.dob)) < 5 THEN 'Under 5'
                    WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, c.dob)) BETWEEN 5 AND 18 THEN '5-18'
                    WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, c.dob)) BETWEEN 19 AND 45 THEN '19-45'
                    WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, c.dob)) BETWEEN 46 AND 65 THEN '46-65'
                    ELSE 'Over 65'
                END as age_group,
                COUNT(DISTINCT v.citizen_id) as vaccinated_count
            FROM vaccinations v
            JOIN citizens c ON v.citizen_id = c.citizen_id
            GROUP BY age_group
            ORDER BY age_group
        """)
        age_group_stats = cur.fetchall()
        
        # Format data for template
        statistics = {
            'vaccine_stats': [{'type': stat[0], 'count': stat[1]} for stat in vaccine_stats],
            'monthly_stats': [{'month': stat[0], 'count': stat[1]} for stat in monthly_stats],
            'recent_activity': [{'type': act[0], 'date': act[1], 'name': act[2], 'dob': act[3]} for act in recent_activity],
            'age_group_stats': [{'age_group': stat[0], 'count': stat[1]} for stat in age_group_stats]
        }
        
        return render_template('monitor/health_metrics.html', statistics=statistics)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

# Infrastructure Monitoring route
@monitor_bp.route('/infrastructure')
@role_required(['admin', 'government_monitor'])
def infrastructure_monitoring():
    conn, cur = get_db_cursor()
    try:
        # Get statistics for different asset types
        cur.execute("""
            SELECT type, COUNT(*) as count
            FROM assets
            GROUP BY type
            ORDER BY count DESC
        """)
        asset_type_stats = cur.fetchall()
        
        # Get assets by installation year
        cur.execute("""
            SELECT EXTRACT(YEAR FROM installation_date) as year, COUNT(*) as count
            FROM assets
            WHERE installation_date IS NOT NULL
            GROUP BY year
            ORDER BY year DESC
        """)
        yearly_stats = cur.fetchall()
        
        # Get recent asset additions
        cur.execute("""
            SELECT asset_id, type, location, installation_date
            FROM assets
            ORDER BY 
                CASE WHEN installation_date IS NULL THEN '1900-01-01'::date ELSE installation_date END DESC,
                asset_id DESC
            LIMIT 10
        """)
        recent_assets = cur.fetchall()
        
        # Format data for template
        statistics = {
            'asset_type_stats': [{'type': stat[0], 'count': stat[1]} for stat in asset_type_stats],
            'yearly_stats': [{'year': int(stat[0]), 'count': stat[1]} for stat in yearly_stats],
            'recent_assets': [{'id': asset[0], 'type': asset[1], 'location': asset[2], 'date': asset[3]} for asset in recent_assets]
        }
        
        return render_template('monitor/infrastructure_monitoring.html', statistics=statistics)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)