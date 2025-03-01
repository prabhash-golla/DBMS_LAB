from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from werkzeug.security import generate_password_hash
from functools import wraps
from database.db_config import get_db_cursor, close_db_connection

# Create the employee blueprint
employee_bp = Blueprint('employee', __name__, url_prefix='/employee')

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

# Routes for Citizen Management by Employees
@employee_bp.route('/citizens')
@role_required(['admin', 'panchayat_employee'])
def manage_citizens():
    conn, cur = get_db_cursor()
    try:
        # Fetch all citizens with their household information
        cur.execute("""
            SELECT c.citizen_id, c.name, c.gender, c.dob, c.educational_qualification, 
                   h.household_id, h.address, u.username, u.email
            FROM citizens c
            LEFT JOIN households h ON c.household_id = h.household_id
            LEFT JOIN users u ON c.user_id = u.user_id
            ORDER BY c.name
        """)
        citizens = cur.fetchall()
        
        # Format the data for template
        citizens_data = []
        for citizen in citizens:
            citizens_data.append({
                'citizen_id': citizen[0],
                'name': citizen[1],
                'gender': citizen[2],
                'dob': citizen[3],
                'education': citizen[4],
                'household_id': citizen[5],
                'address': citizen[6],
                'username': citizen[7],
                'email': citizen[8]
            })
        
        return render_template('employee/manage_citizens.html', citizens=citizens_data)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/citizens/add', methods=['GET', 'POST'])
@role_required(['admin', 'panchayat_employee'])
def add_citizen():
    if request.method == 'POST':
        # Extract form data
        name = request.form['name']
        gender = request.form['gender']
        dob = request.form['dob']
        education = request.form.get('education')
        household_exists = request.form.get('household_exists')
        
        # Validate required fields
        if not name or not gender or not dob:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('employee.add_citizen'))
        
        conn, cur = get_db_cursor()
        try:
            # Handle household assignment
            if household_exists == 'yes':
                household_id = request.form.get('existing_household_id')
                
                # Verify household exists
                cur.execute("SELECT * FROM households WHERE household_id = %s", (household_id,))
                if not cur.fetchone():
                    flash('Household ID not found', 'danger')
                    close_db_connection(conn, cur)
                    return redirect(url_for('employee.add_citizen'))
            else:
                # Create a new household
                address = request.form.get('address')
                income = request.form.get('income', 0)
                
                # Convert empty string to 0 for income
                if not income:
                    income = 0
                
                if not address:
                    flash('Address is required for a new household', 'danger')
                    close_db_connection(conn, cur)
                    return redirect(url_for('employee.add_citizen'))
                
                cur.execute(
                    "INSERT INTO households (address, income) VALUES (%s, %s) RETURNING household_id",
                    (address, income)
                )
                household_id = cur.fetchone()[0]
            
            # Check if we need to create a user account
            create_account = request.form.get('create_account') == 'yes'
            user_id = None
            
            if create_account:
                username = request.form.get('username')
                email = request.form.get('email')
                password = request.form.get('password')
                
                if not username or not email or not password:
                    flash('Please fill in all user account fields.', 'danger')
                    close_db_connection(conn, cur)
                    return redirect(url_for('employee.add_citizen'))
                
                # Check if username or email already exists
                cur.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, email))
                if cur.fetchone():
                    flash('Username or email already exists', 'danger')
                    close_db_connection(conn, cur)
                    return redirect(url_for('employee.add_citizen'))
                
                # Create user with citizen role (role_id=3)
                password_hash = generate_password_hash(password)
                cur.execute(
                    "INSERT INTO users (username, email, password_hash, role_id) VALUES (%s, %s, %s, 3) RETURNING user_id",
                    (username, email, password_hash)
                )
                user_id = cur.fetchone()[0]
            
            # Create citizen record
            cur.execute(
                "INSERT INTO citizens (name, gender, dob, household_id, educational_qualification, user_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING citizen_id",
                (name, gender, dob, household_id, education, user_id)
            )
            citizen_id = cur.fetchone()[0]
            
            flash(f'Citizen {name} added successfully with ID: {citizen_id}', 'success')
            return redirect(url_for('employee.manage_citizens'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('employee.add_citizen'))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form
    conn, cur = get_db_cursor()
    try:
        # Get all households for dropdown
        cur.execute("SELECT household_id, address FROM households ORDER BY household_id")
        households = cur.fetchall()
        return render_template('employee/add_citizen.html', households=households)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_citizens'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/citizens/edit/<int:citizen_id>', methods=['GET', 'POST'])
@role_required(['admin', 'panchayat_employee'])
def edit_citizen(citizen_id):
    if request.method == 'POST':
        # Extract form data
        name = request.form['name']
        gender = request.form['gender']
        dob = request.form['dob']
        education = request.form.get('education')
        household_id = request.form.get('household_id')
        
        # Validate required fields
        if not name or not gender or not dob or not household_id:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('employee.edit_citizen', citizen_id=citizen_id))
        
        conn, cur = get_db_cursor()
        try:
            # Update citizen information
            cur.execute(
                """
                UPDATE citizens 
                SET name = %s, gender = %s, dob = %s, educational_qualification = %s, household_id = %s
                WHERE citizen_id = %s
                """,
                (name, gender, dob, education, household_id, citizen_id)
            )
            
            # Check if we need to update user account information
            if 'user_id' in request.form and request.form['user_id']:
                user_id = request.form['user_id']
                email = request.form.get('email')
                
                if email:
                    cur.execute(
                        "UPDATE users SET email = %s WHERE user_id = %s",
                        (email, user_id)
                    )
            
            flash(f'Citizen information updated successfully.', 'success')
            return redirect(url_for('employee.manage_citizens'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('employee.edit_citizen', citizen_id=citizen_id))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form with citizen data
    conn, cur = get_db_cursor()
    try:
        # Get citizen information
        cur.execute(
            """
            SELECT c.citizen_id, c.name, c.gender, c.dob, c.educational_qualification, 
                   c.household_id, c.user_id, u.username, u.email
            FROM citizens c
            LEFT JOIN users u ON c.user_id = u.user_id
            WHERE c.citizen_id = %s
            """,
            (citizen_id,)
        )
        citizen = cur.fetchone()
        
        if not citizen:
            flash('Citizen not found.', 'danger')
            return redirect(url_for('employee.manage_citizens'))
        
        # Get all households for dropdown
        cur.execute("SELECT household_id, address FROM households ORDER BY household_id")
        households = cur.fetchall()
        
        citizen_data = {
            'citizen_id': citizen[0],
            'name': citizen[1],
            'gender': citizen[2],
            'dob': citizen[3],
            'education': citizen[4],
            'household_id': citizen[5],
            'user_id': citizen[6],
            'username': citizen[7],
            'email': citizen[8]
        }
        
        return render_template('employee/edit_citizen.html', citizen=citizen_data, households=households)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_citizens'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/citizens/delete/<int:citizen_id>', methods=['POST'])
@role_required(['admin', 'panchayat_employee'])
def delete_citizen(citizen_id):
    conn, cur = get_db_cursor()
    try:
        # Start a transaction
        conn.autocommit = False
        
        # First check if citizen exists
        cur.execute("SELECT citizen_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
        if not cur.fetchone():
            flash('Citizen not found.', 'danger')
            conn.rollback()
            return redirect(url_for('employee.manage_citizens'))
        
        # Check if citizen is a panchayat employee
        cur.execute("""
            SELECT e.employee_id, e.user_id 
            FROM panchayat_employees e 
            WHERE e.citizen_id = %s
        """, (citizen_id,))
        employee_data = cur.fetchone()
        
        employee_id = None
        employee_user_id = None
        
        if employee_data:
            employee_id = employee_data[0]
            employee_user_id = employee_data[1]
            
            # Log employee deletion
            print(f"Deleting employee ID: {employee_id} with user_id: {employee_user_id}")
        
        # Get the citizen's user_id
        cur.execute("SELECT user_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
        citizen_user_id = cur.fetchone()[0]
        
        # Delete dependent records first in the correct order
        # 1. Delete scheme enrollments
        cur.execute("DELETE FROM scheme_enrollments WHERE citizen_id = %s", (citizen_id,))
        
        # 2. Delete vaccinations
        cur.execute("DELETE FROM vaccinations WHERE citizen_id = %s", (citizen_id,))
        
        # 3. Delete land records
        cur.execute("DELETE FROM land_records WHERE citizen_id = %s", (citizen_id,))
        
        # 4. Delete census data
        cur.execute("DELETE FROM census_data WHERE citizen_id = %s", (citizen_id,))
        
        # 5. Delete from panchayat_employees if applicable
        if employee_id:
            cur.execute("DELETE FROM panchayat_employees WHERE employee_id = %s", (employee_id,))
        
        # 6. Delete the citizen record
        cur.execute("DELETE FROM citizens WHERE citizen_id = %s", (citizen_id,))
        
        # 7. Delete the user accounts if they exist
        user_ids_to_delete = []
        
        if citizen_user_id:
            user_ids_to_delete.append(citizen_user_id)
            
        if employee_user_id and employee_user_id != citizen_user_id:
            user_ids_to_delete.append(employee_user_id)
        
        for user_id in user_ids_to_delete:
            if user_id:
                # Log user deletion
                print(f"Deleting user ID: {user_id}")
                cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        
        # Commit the transaction
        conn.commit()
        
        flash('Citizen and all associated records deleted successfully.', 'success')
    except Exception as e:
        # Rollback in case of error
        conn.rollback()
        flash(f'An error occurred: {str(e)}', 'danger')
        print(f"Delete error: {str(e)}")
    finally:
        # Restore autocommit mode
        conn.autocommit = True
        close_db_connection(conn, cur)
    
    return redirect(url_for('employee.manage_citizens'))

@employee_bp.route('/citizens/view/<int:citizen_id>')
@role_required(['admin', 'panchayat_employee'])
def view_citizen(citizen_id):
    conn, cur = get_db_cursor()
    try:
        # Get comprehensive citizen information
        cur.execute(
            """
            SELECT c.citizen_id, c.name, c.gender, c.dob, c.educational_qualification, 
                   h.household_id, h.address, h.income, c.user_id, u.username, u.email
            FROM citizens c
            LEFT JOIN households h ON c.household_id = h.household_id
            LEFT JOIN users u ON c.user_id = u.user_id
            WHERE c.citizen_id = %s
            """,
            (citizen_id,)
        )
        citizen_data = cur.fetchone()
        
        if not citizen_data:
            flash('Citizen not found.', 'danger')
            return redirect(url_for('employee.manage_citizens'))
        
        citizen = {
            'citizen_id': citizen_data[0],
            'name': citizen_data[1],
            'gender': citizen_data[2],
            'dob': citizen_data[3],
            'education': citizen_data[4],
            'household_id': citizen_data[5],
            'address': citizen_data[6],
            'household_income': citizen_data[7],
            'user_id': citizen_data[8],
            'username': citizen_data[9],
            'email': citizen_data[10]
        }
        
        # Get household members
        cur.execute(
            """
            SELECT citizen_id, name, gender, dob
            FROM citizens
            WHERE household_id = %s AND citizen_id != %s
            """,
            (citizen['household_id'], citizen_id)
        )
        
        household_members = []
        for member in cur.fetchall():
            household_members.append({
                'citizen_id': member[0],
                'name': member[1],
                'gender': member[2],
                'dob': member[3]
            })
        
        # Get welfare scheme enrollments
        cur.execute(
            """
            SELECT ws.name, ws.description, se.enrollment_date
            FROM scheme_enrollments se
            JOIN welfare_schemes ws ON se.scheme_id = ws.scheme_id
            WHERE se.citizen_id = %s
            """,
            (citizen_id,)
        )
        
        schemes = []
        for scheme in cur.fetchall():
            schemes.append({
                'name': scheme[0],
                'description': scheme[1],
                'enrollment_date': scheme[2]
            })
        
        # Get vaccination records
        cur.execute(
            """
            SELECT vaccine_type, date_administered
            FROM vaccinations
            WHERE citizen_id = %s
            """,
            (citizen_id,)
        )
        
        vaccinations = []
        for vax in cur.fetchall():
            vaccinations.append({
                'vaccine_type': vax[0],
                'date': vax[1]
            })
        
        # Get land records
        cur.execute(
            """
            SELECT land_id, area_acres, crop_type
            FROM land_records
            WHERE citizen_id = %s
            """,
            (citizen_id,)
        )
        
        land_records = []
        for record in cur.fetchall():
            land_records.append({
                'land_id': record[0],
                'area': record[1],
                'crop_type': record[2]
            })
        
        return render_template(
            'employee/view_citizen.html',
            citizen=citizen,
            household_members=household_members,
            schemes=schemes,
            vaccinations=vaccinations,
            land_records=land_records
        )
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_citizens'))
    finally:
        close_db_connection(conn, cur)

# Land Records Management Routes
@employee_bp.route('/land_records')
@role_required(['admin', 'panchayat_employee'])
def manage_land_records():
    conn, cur = get_db_cursor()
    try:
        # Fetch all land records with owner information
        cur.execute("""
            SELECT l.land_id, l.area_acres, l.crop_type, c.citizen_id, c.name, h.address
            FROM land_records l
            JOIN citizens c ON l.citizen_id = c.citizen_id
            JOIN households h ON c.household_id = h.household_id
            ORDER BY l.land_id
        """)
        records = cur.fetchall()
        
        # Format the data for template
        land_records = []
        for record in records:
            land_records.append({
                'land_id': record[0],
                'area_acres': record[1],
                'crop_type': record[2],
                'citizen_id': record[3],
                'owner_name': record[4],
                'location': record[5]
            })
        
        return render_template('employee/manage_land_records.html', land_records=land_records)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/land_records/add', methods=['GET', 'POST'])
@role_required(['admin', 'panchayat_employee'])
def add_land_record():
    if request.method == 'POST':
        # Extract form data
        citizen_id = request.form['citizen_id']
        area_acres = request.form['area_acres']
        crop_type = request.form['crop_type']
        
        # Validate required fields
        if not citizen_id or not area_acres:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('employee.add_land_record'))
        
        conn, cur = get_db_cursor()
        try:
            # Verify citizen exists
            cur.execute("SELECT citizen_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
            if not cur.fetchone():
                flash('Citizen ID not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('employee.add_land_record'))
            
            # Insert new land record
            cur.execute(
                "INSERT INTO land_records (citizen_id, area_acres, crop_type) VALUES (%s, %s, %s) RETURNING land_id",
                (citizen_id, area_acres, crop_type)
            )
            land_id = cur.fetchone()[0]
            
            flash(f'Land record added successfully with ID: {land_id}', 'success')
            return redirect(url_for('employee.manage_land_records'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('employee.add_land_record'))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form
    conn, cur = get_db_cursor()
    try:
        # Get all citizens for dropdown
        cur.execute("""
            SELECT c.citizen_id, c.name, h.address
            FROM citizens c
            JOIN households h ON c.household_id = h.household_id
            ORDER BY c.name
        """)
        citizens = cur.fetchall()
        
        # Get common crop types for dropdown
        common_crops = ["Rice", "Wheat", "Cotton", "Sugarcane", "Pulses", "Vegetables", "Fruits", "Other"]
        
        return render_template('employee/add_land_record.html', citizens=citizens, common_crops=common_crops)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_land_records'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/land_records/edit/<int:land_id>', methods=['GET', 'POST'])
@role_required(['admin', 'panchayat_employee'])
def edit_land_record(land_id):
    if request.method == 'POST':
        # Extract form data
        citizen_id = request.form['citizen_id']
        area_acres = request.form['area_acres']
        crop_type = request.form['crop_type']
        
        # Validate required fields
        if not citizen_id or not area_acres:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('employee.edit_land_record', land_id=land_id))
        
        conn, cur = get_db_cursor()
        try:
            # Verify citizen exists
            cur.execute("SELECT citizen_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
            if not cur.fetchone():
                flash('Citizen ID not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('employee.edit_land_record', land_id=land_id))
            
            # Update land record
            cur.execute(
                "UPDATE land_records SET citizen_id = %s, area_acres = %s, crop_type = %s WHERE land_id = %s",
                (citizen_id, area_acres, crop_type, land_id)
            )
            
            flash('Land record updated successfully.', 'success')
            return redirect(url_for('employee.manage_land_records'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('employee.edit_land_record', land_id=land_id))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form with land record data
    conn, cur = get_db_cursor()
    try:
        # Get land record information
        cur.execute("SELECT land_id, citizen_id, area_acres, crop_type FROM land_records WHERE land_id = %s", (land_id,))
        record = cur.fetchone()
        
        if not record:
            flash('Land record not found.', 'danger')
            return redirect(url_for('employee.manage_land_records'))
        
        land_record = {
            'land_id': record[0],
            'citizen_id': record[1],
            'area_acres': record[2],
            'crop_type': record[3]
        }
        
        # Get all citizens for dropdown
        cur.execute("""
            SELECT c.citizen_id, c.name, h.address
            FROM citizens c
            JOIN households h ON c.household_id = h.household_id
            ORDER BY c.name
        """)
        citizens = cur.fetchall()
        
        # Get common crop types for dropdown
        common_crops = ["Rice", "Wheat", "Cotton", "Sugarcane", "Pulses", "Vegetables", "Fruits", "Other"]
        
        return render_template('employee/edit_land_record.html', land_record=land_record, citizens=citizens, common_crops=common_crops)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_land_records'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/land_records/delete/<int:land_id>', methods=['POST'])
@role_required(['admin', 'panchayat_employee'])
def delete_land_record(land_id):
    conn, cur = get_db_cursor()
    try:
        # Check if land record exists
        cur.execute("SELECT land_id FROM land_records WHERE land_id = %s", (land_id,))
        if not cur.fetchone():
            flash('Land record not found.', 'danger')
            return redirect(url_for('employee.manage_land_records'))
        
        # Delete the land record
        cur.execute("DELETE FROM land_records WHERE land_id = %s", (land_id,))
        
        flash('Land record deleted successfully.', 'success')
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
    finally:
        close_db_connection(conn, cur)
    
    return redirect(url_for('employee.manage_land_records'))

@employee_bp.route('/land_records/view/<int:land_id>')
@role_required(['admin', 'panchayat_employee'])
def view_land_record(land_id):
    conn, cur = get_db_cursor()
    try:
        # Get comprehensive land record information with owner details
        cur.execute("""
            SELECT l.land_id, l.area_acres, l.crop_type,
                   c.citizen_id, c.name, c.gender,
                   h.household_id, h.address
            FROM land_records l
            JOIN citizens c ON l.citizen_id = c.citizen_id
            JOIN households h ON c.household_id = h.household_id
            WHERE l.land_id = %s
        """, (land_id,))
        record_data = cur.fetchone()
        
        if not record_data:
            flash('Land record not found.', 'danger')
            return redirect(url_for('employee.manage_land_records'))
        
        land_record = {
            'land_id': record_data[0],
            'area_acres': record_data[1],
            'crop_type': record_data[2],
            'citizen_id': record_data[3],
            'owner_name': record_data[4],
            'owner_gender': record_data[5],
            'household_id': record_data[6],
            'location': record_data[7]
        }
        
        return render_template('employee/view_land_record.html', land_record=land_record)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_land_records'))
    finally:
        close_db_connection(conn, cur)

# Welfare Scheme Management Routes
@employee_bp.route('/welfare_schemes')
@role_required(['admin', 'panchayat_employee'])
def manage_welfare_schemes():
    conn, cur = get_db_cursor()
    try:
        # Fetch all welfare schemes
        cur.execute("""
            SELECT scheme_id, name, description 
            FROM welfare_schemes
            ORDER BY name
        """)
        schemes = cur.fetchall()
        
        # Format the data for template
        welfare_schemes = []
        for scheme in schemes:
            # Count enrollments for each scheme
            cur.execute("""
                SELECT COUNT(*) FROM scheme_enrollments
                WHERE scheme_id = %s
            """, (scheme[0],))
            enrollment_count = cur.fetchone()[0]
            
            welfare_schemes.append({
                'scheme_id': scheme[0],
                'name': scheme[1],
                'description': scheme[2],
                'enrollment_count': enrollment_count
            })
        
        return render_template('employee/manage_welfare_schemes.html', welfare_schemes=welfare_schemes)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/welfare_schemes/add', methods=['GET', 'POST'])
@role_required(['admin', 'panchayat_employee'])
def add_welfare_scheme():
    if request.method == 'POST':
        # Extract form data
        name = request.form['name']
        description = request.form['description']
        
        # Validate required fields
        if not name:
            flash('Scheme name is required.', 'danger')
            return redirect(url_for('employee.add_welfare_scheme'))
        
        conn, cur = get_db_cursor()
        try:
            # Check if scheme with same name already exists
            cur.execute("SELECT scheme_id FROM welfare_schemes WHERE name = %s", (name,))
            if cur.fetchone():
                flash('A welfare scheme with this name already exists.', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('employee.add_welfare_scheme'))
            
            # Insert new welfare scheme
            cur.execute(
                "INSERT INTO welfare_schemes (name, description) VALUES (%s, %s) RETURNING scheme_id",
                (name, description)
            )
            scheme_id = cur.fetchone()[0]
            
            flash(f'Welfare scheme "{name}" added successfully.', 'success')
            return redirect(url_for('employee.manage_welfare_schemes'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('employee.add_welfare_scheme'))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form
    return render_template('employee/add_welfare_scheme.html')

@employee_bp.route('/welfare_schemes/edit/<int:scheme_id>', methods=['GET', 'POST'])
@role_required(['admin', 'panchayat_employee'])
def edit_welfare_scheme(scheme_id):
    if request.method == 'POST':
        # Extract form data
        name = request.form['name']
        description = request.form['description']
        
        # Validate required fields
        if not name:
            flash('Scheme name is required.', 'danger')
            return redirect(url_for('employee.edit_welfare_scheme', scheme_id=scheme_id))
        
        conn, cur = get_db_cursor()
        try:
            # Check if another scheme with same name already exists
            cur.execute("SELECT scheme_id FROM welfare_schemes WHERE name = %s AND scheme_id != %s", (name, scheme_id))
            if cur.fetchone():
                flash('Another welfare scheme with this name already exists.', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('employee.edit_welfare_scheme', scheme_id=scheme_id))
            
            # Update welfare scheme
            cur.execute(
                "UPDATE welfare_schemes SET name = %s, description = %s WHERE scheme_id = %s",
                (name, description, scheme_id)
            )
            
            flash(f'Welfare scheme updated successfully.', 'success')
            return redirect(url_for('employee.manage_welfare_schemes'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('employee.edit_welfare_scheme', scheme_id=scheme_id))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form with welfare scheme data
    conn, cur = get_db_cursor()
    try:
        # Get welfare scheme information
        cur.execute("SELECT scheme_id, name, description FROM welfare_schemes WHERE scheme_id = %s", (scheme_id,))
        scheme = cur.fetchone()
        
        if not scheme:
            flash('Welfare scheme not found.', 'danger')
            return redirect(url_for('employee.manage_welfare_schemes'))
        
        welfare_scheme = {
            'scheme_id': scheme[0],
            'name': scheme[1],
            'description': scheme[2]
        }
        
        return render_template('employee/edit_welfare_scheme.html', welfare_scheme=welfare_scheme)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_welfare_schemes'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/welfare_schemes/delete/<int:scheme_id>', methods=['POST'])
@role_required(['admin', 'panchayat_employee'])
def delete_welfare_scheme(scheme_id):
    conn, cur = get_db_cursor()
    try:
        # Start a transaction
        conn.autocommit = False
        
        # Check if scheme exists
        cur.execute("SELECT scheme_id FROM welfare_schemes WHERE scheme_id = %s", (scheme_id,))
        if not cur.fetchone():
            flash('Welfare scheme not found.', 'danger')
            conn.rollback()
            return redirect(url_for('employee.manage_welfare_schemes'))
        
        # Check if there are enrollments for this scheme
        cur.execute("SELECT COUNT(*) FROM scheme_enrollments WHERE scheme_id = %s", (scheme_id,))
        enrollment_count = cur.fetchone()[0]
        
        if enrollment_count > 0:
            # Delete all enrollments for this scheme first
            cur.execute("DELETE FROM scheme_enrollments WHERE scheme_id = %s", (scheme_id,))
        
        # Delete the welfare scheme
        cur.execute("DELETE FROM welfare_schemes WHERE scheme_id = %s", (scheme_id,))
        
        # Commit the transaction
        conn.commit()
        
        flash('Welfare scheme and all associated enrollments deleted successfully.', 'success')
    except Exception as e:
        # Rollback in case of error
        conn.rollback()
        flash(f'An error occurred: {str(e)}', 'danger')
    finally:
        # Restore autocommit mode
        conn.autocommit = True
        close_db_connection(conn, cur)
    
    return redirect(url_for('employee.manage_welfare_schemes'))

@employee_bp.route('/welfare_schemes/view/<int:scheme_id>')
@role_required(['admin', 'panchayat_employee'])
def view_welfare_scheme(scheme_id):
    conn, cur = get_db_cursor()
    try:
        # Get welfare scheme information
        cur.execute("SELECT scheme_id, name, description FROM welfare_schemes WHERE scheme_id = %s", (scheme_id,))
        scheme_data = cur.fetchone()
        
        if not scheme_data:
            flash('Welfare scheme not found.', 'danger')
            return redirect(url_for('employee.manage_welfare_schemes'))
        
        welfare_scheme = {
            'scheme_id': scheme_data[0],
            'name': scheme_data[1],
            'description': scheme_data[2]
        }
        
        # Get all enrollments for this scheme
        cur.execute("""
            SELECT se.enrollment_id, se.enrollment_date, c.citizen_id, c.name, c.gender, h.address
            FROM scheme_enrollments se
            JOIN citizens c ON se.citizen_id = c.citizen_id
            JOIN households h ON c.household_id = h.household_id
            WHERE se.scheme_id = %s
            ORDER BY se.enrollment_date DESC
        """, (scheme_id,))
        
        enrollments = []
        for enrollment in cur.fetchall():
            enrollments.append({
                'enrollment_id': enrollment[0],
                'enrollment_date': enrollment[1],
                'citizen_id': enrollment[2],
                'citizen_name': enrollment[3],
                'gender': enrollment[4],
                'address': enrollment[5]
            })
        
        return render_template('employee/view_welfare_scheme.html', welfare_scheme=welfare_scheme, enrollments=enrollments)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_welfare_schemes'))
    finally:
        close_db_connection(conn, cur)

# Scheme Enrollment Management Routes
@employee_bp.route('/enrollments')
@role_required(['admin', 'panchayat_employee'])
def manage_enrollments():
    conn, cur = get_db_cursor()
    try:
        # Fetch all enrollments with citizen and scheme information
        cur.execute("""
            SELECT se.enrollment_id, se.enrollment_date, 
                   c.citizen_id, c.name AS citizen_name,
                   ws.scheme_id, ws.name AS scheme_name
            FROM scheme_enrollments se
            JOIN citizens c ON se.citizen_id = c.citizen_id
            JOIN welfare_schemes ws ON se.scheme_id = ws.scheme_id
            ORDER BY se.enrollment_date DESC
        """)
        enrollments_data = cur.fetchall()
        
        # Format the data for template
        enrollments = []
        for enrollment in enrollments_data:
            enrollments.append({
                'enrollment_id': enrollment[0],
                'enrollment_date': enrollment[1],
                'citizen_id': enrollment[2],
                'citizen_name': enrollment[3],
                'scheme_id': enrollment[4],
                'scheme_name': enrollment[5]
            })
        
        return render_template('employee/manage_enrollments.html', enrollments=enrollments)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/enrollments/add', methods=['GET', 'POST'])
@role_required(['admin', 'panchayat_employee'])
def add_enrollment():
    if request.method == 'POST':
        # Extract form data
        citizen_id = request.form['citizen_id']
        scheme_id = request.form['scheme_id']
        enrollment_date = request.form.get('enrollment_date') or None
        
        # Validate required fields
        if not citizen_id or not scheme_id:
            flash('Please select both a citizen and a welfare scheme.', 'danger')
            return redirect(url_for('employee.add_enrollment'))
        
        conn, cur = get_db_cursor()
        try:
            # Check if citizen exists
            cur.execute("SELECT citizen_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
            if not cur.fetchone():
                flash('Citizen not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('employee.add_enrollment'))
            
            # Check if scheme exists
            cur.execute("SELECT scheme_id FROM welfare_schemes WHERE scheme_id = %s", (scheme_id,))
            if not cur.fetchone():
                flash('Welfare scheme not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('employee.add_enrollment'))
            
            # Check if enrollment already exists
            cur.execute("""
                SELECT enrollment_id FROM scheme_enrollments
                WHERE citizen_id = %s AND scheme_id = %s
            """, (citizen_id, scheme_id))
            if cur.fetchone():
                flash('This citizen is already enrolled in this scheme.', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('employee.add_enrollment'))
            
            # Insert new enrollment
            if enrollment_date:
                cur.execute(
                    "INSERT INTO scheme_enrollments (citizen_id, scheme_id, enrollment_date) VALUES (%s, %s, %s) RETURNING enrollment_id",
                    (citizen_id, scheme_id, enrollment_date)
                )
            else:
                cur.execute(
                    "INSERT INTO scheme_enrollments (citizen_id, scheme_id) VALUES (%s, %s) RETURNING enrollment_id",
                    (citizen_id, scheme_id)
                )
            enrollment_id = cur.fetchone()[0]
            
            flash('Enrollment added successfully.', 'success')
            return redirect(url_for('employee.manage_enrollments'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('employee.add_enrollment'))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form
    conn, cur = get_db_cursor()
    try:
        # Get all citizens for dropdown
        cur.execute("""
            SELECT c.citizen_id, c.name, h.address
            FROM citizens c
            JOIN households h ON c.household_id = h.household_id
            ORDER BY c.name
        """)
        citizens = cur.fetchall()
        
        # Get all welfare schemes for dropdown
        cur.execute("SELECT scheme_id, name FROM welfare_schemes ORDER BY name")
        schemes = cur.fetchall()
        
        return render_template('employee/add_enrollment.html', citizens=citizens, schemes=schemes)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_enrollments'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/enrollments/delete/<int:enrollment_id>', methods=['POST'])
@role_required(['admin', 'panchayat_employee'])
def delete_enrollment(enrollment_id):
    conn, cur = get_db_cursor()
    try:
        # Check if enrollment exists
        cur.execute("SELECT enrollment_id FROM scheme_enrollments WHERE enrollment_id = %s", (enrollment_id,))
        if not cur.fetchone():
            flash('Enrollment not found.', 'danger')
            return redirect(url_for('employee.manage_enrollments'))
        
        # Delete the enrollment
        cur.execute("DELETE FROM scheme_enrollments WHERE enrollment_id = %s", (enrollment_id,))
        
        flash('Enrollment deleted successfully.', 'success')
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
    finally:
        close_db_connection(conn, cur)
    
    return redirect(url_for('employee.manage_enrollments'))

@employee_bp.route('/enrollments/citizen/<int:citizen_id>')
@role_required(['admin', 'panchayat_employee'])
def citizen_enrollments(citizen_id):
    conn, cur = get_db_cursor()
    try:
        # Get citizen information
        cur.execute("""
            SELECT c.citizen_id, c.name, c.gender, c.dob, h.address
            FROM citizens c
            JOIN households h ON c.household_id = h.household_id
            WHERE c.citizen_id = %s
        """, (citizen_id,))
        citizen_data = cur.fetchone()
        
        if not citizen_data:
            flash('Citizen not found.', 'danger')
            return redirect(url_for('employee.manage_enrollments'))
        
        citizen = {
            'citizen_id': citizen_data[0],
            'name': citizen_data[1],
            'gender': citizen_data[2],
            'dob': citizen_data[3],
            'address': citizen_data[4]
        }
        
        # Get all enrollments for this citizen
        cur.execute("""
            SELECT se.enrollment_id, se.enrollment_date, ws.scheme_id, ws.name, ws.description
            FROM scheme_enrollments se
            JOIN welfare_schemes ws ON se.scheme_id = ws.scheme_id
            WHERE se.citizen_id = %s
            ORDER BY se.enrollment_date DESC
        """, (citizen_id,))
        
        enrollments = []
        for enrollment in cur.fetchall():
            enrollments.append({
                'enrollment_id': enrollment[0],
                'enrollment_date': enrollment[1],
                'scheme_id': enrollment[2],
                'scheme_name': enrollment[3],
                'scheme_description': enrollment[4]
            })
        
        return render_template('employee/citizen_enrollments.html', citizen=citizen, enrollments=enrollments)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_enrollments'))
    finally:
        close_db_connection(conn, cur)        

# Census Data Management Routes
@employee_bp.route('/census')
@role_required(['admin', 'panchayat_employee'])
def manage_census():
    conn, cur = get_db_cursor()
    try:
        # Fetch all census records with citizen and household information
        cur.execute("""
            SELECT cd.census_id, cd.event_type, cd.event_date, 
                   c.citizen_id, c.name AS citizen_name, 
                   h.household_id, h.address
            FROM census_data cd
            JOIN citizens c ON cd.citizen_id = c.citizen_id
            JOIN households h ON cd.household_id = h.household_id
            ORDER BY cd.event_date DESC
        """)
        records = cur.fetchall()
        
        # Format the data for template
        census_data = []
        for record in records:
            census_data.append({
                'census_id': record[0],
                'event_type': record[1],
                'event_date': record[2],
                'citizen_id': record[3],
                'citizen_name': record[4],
                'household_id': record[5],
                'address': record[6]
            })
        
        return render_template('employee/manage_census.html', census_data=census_data)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/census/add', methods=['GET', 'POST'])
@role_required(['admin', 'panchayat_employee'])
def add_census_record():
    if request.method == 'POST':
        # Extract form data
        citizen_id = request.form['citizen_id']
        household_id = request.form.get('household_id')
        event_type = request.form['event_type']
        event_date = request.form.get('event_date') or None
        
        # Validate required fields
        if not citizen_id or not event_type:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('employee.add_census_record'))
        
        conn, cur = get_db_cursor()
        try:
            # Check if citizen exists
            cur.execute("SELECT citizen_id, household_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
            citizen_data = cur.fetchone()
            
            if not citizen_data:
                flash('Citizen not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('employee.add_census_record'))
            
            # If household_id not provided, use the citizen's household
            if not household_id:
                household_id = citizen_data[1]
            
            # Verify household exists
            cur.execute("SELECT household_id FROM households WHERE household_id = %s", (household_id,))
            if not cur.fetchone():
                flash('Household not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('employee.add_census_record'))
            
            # Insert new census record
            if event_date:
                cur.execute(
                    "INSERT INTO census_data (citizen_id, household_id, event_type, event_date) VALUES (%s, %s, %s, %s) RETURNING census_id",
                    (citizen_id, household_id, event_type, event_date)
                )
            else:
                cur.execute(
                    "INSERT INTO census_data (citizen_id, household_id, event_type) VALUES (%s, %s, %s) RETURNING census_id",
                    (citizen_id, household_id, event_type)
                )
            census_id = cur.fetchone()[0]
            
            flash(f'Census record added successfully.', 'success')
            return redirect(url_for('employee.manage_census'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('employee.add_census_record'))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form
    conn, cur = get_db_cursor()
    try:
        # Get all citizens for dropdown
        cur.execute("""
            SELECT c.citizen_id, c.name, h.address
            FROM citizens c
            JOIN households h ON c.household_id = h.household_id
            ORDER BY c.name
        """)
        citizens = cur.fetchall()
        
        # Get all households for dropdown
        cur.execute("SELECT household_id, address FROM households ORDER BY household_id")
        households = cur.fetchall()
        
        # Define common event types
        event_types = [
            "Birth", "Death", "Marriage", "Migration_In", "Migration_Out", 
            "Education_Update", "Income_Change", "Occupation_Change",
            "Health_Status_Update"
        ]
        
        return render_template('employee/add_census_record.html', 
                              citizens=citizens, 
                              households=households, 
                              event_types=event_types)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_census'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/census/edit/<int:census_id>', methods=['GET', 'POST'])
@role_required(['admin', 'panchayat_employee'])
def edit_census_record(census_id):
    if request.method == 'POST':
        # Extract form data
        citizen_id = request.form['citizen_id']
        household_id = request.form.get('household_id')
        event_type = request.form['event_type']
        event_date = request.form.get('event_date') or None
        
        # Validate required fields
        if not citizen_id or not event_type:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('employee.edit_census_record', census_id=census_id))
        
        conn, cur = get_db_cursor()
        try:
            # Check if citizen exists
            cur.execute("SELECT citizen_id, household_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
            citizen_data = cur.fetchone()
            
            if not citizen_data:
                flash('Citizen not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('employee.edit_census_record', census_id=census_id))
            
            # If household_id not provided, use the citizen's household
            if not household_id:
                household_id = citizen_data[1]
            
            # Verify household exists
            cur.execute("SELECT household_id FROM households WHERE household_id = %s", (household_id,))
            if not cur.fetchone():
                flash('Household not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('employee.edit_census_record', census_id=census_id))
            
            # Update census record
            if event_date:
                cur.execute(
                    "UPDATE census_data SET citizen_id = %s, household_id = %s, event_type = %s, event_date = %s WHERE census_id = %s",
                    (citizen_id, household_id, event_type, event_date, census_id)
                )
            else:
                cur.execute(
                    "UPDATE census_data SET citizen_id = %s, household_id = %s, event_type = %s, event_date = CURRENT_DATE WHERE census_id = %s",
                    (citizen_id, household_id, event_type, census_id)
                )
            
            flash('Census record updated successfully.', 'success')
            return redirect(url_for('employee.manage_census'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('employee.edit_census_record', census_id=census_id))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form with census record data
    conn, cur = get_db_cursor()
    try:
        # Get census record information
        cur.execute("""
            SELECT cd.census_id, cd.citizen_id, cd.household_id, cd.event_type, cd.event_date
            FROM census_data cd
            WHERE cd.census_id = %s
        """, (census_id,))
        record = cur.fetchone()
        
        if not record:
            flash('Census record not found.', 'danger')
            return redirect(url_for('employee.manage_census'))
        
        census_record = {
            'census_id': record[0],
            'citizen_id': record[1],
            'household_id': record[2],
            'event_type': record[3],
            'event_date': record[4]
        }
        
        # Get all citizens for dropdown
        cur.execute("""
            SELECT c.citizen_id, c.name, h.address
            FROM citizens c
            JOIN households h ON c.household_id = h.household_id
            ORDER BY c.name
        """)
        citizens = cur.fetchall()
        
        # Get all households for dropdown
        cur.execute("SELECT household_id, address FROM households ORDER BY household_id")
        households = cur.fetchall()
        
        # Define common event types
        event_types = [
            "Birth", "Death", "Marriage", "Migration_In", "Migration_Out", 
            "Education_Update", "Income_Change", "Occupation_Change",
            "Health_Status_Update"
        ]
        
        return render_template('employee/edit_census_record.html', 
                              census_record=census_record,
                              citizens=citizens, 
                              households=households, 
                              event_types=event_types)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_census'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/census/delete/<int:census_id>', methods=['POST'])
@role_required(['admin', 'panchayat_employee'])
def delete_census_record(census_id):
    conn, cur = get_db_cursor()
    try:
        # Check if census record exists
        cur.execute("SELECT census_id FROM census_data WHERE census_id = %s", (census_id,))
        if not cur.fetchone():
            flash('Census record not found.', 'danger')
            return redirect(url_for('employee.manage_census'))
        
        # Delete the census record
        cur.execute("DELETE FROM census_data WHERE census_id = %s", (census_id,))
        
        flash('Census record deleted successfully.', 'success')
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
    finally:
        close_db_connection(conn, cur)
    
    return redirect(url_for('employee.manage_census'))

@employee_bp.route('/census/citizen/<int:citizen_id>')
@role_required(['admin', 'panchayat_employee'])
def citizen_census(citizen_id):
    conn, cur = get_db_cursor()
    try:
        # Get citizen information
        cur.execute("""
            SELECT c.citizen_id, c.name, c.gender, c.dob, h.address
            FROM citizens c
            JOIN households h ON c.household_id = h.household_id
            WHERE c.citizen_id = %s
        """, (citizen_id,))
        citizen_data = cur.fetchone()
        
        if not citizen_data:
            flash('Citizen not found.', 'danger')
            return redirect(url_for('employee.manage_census'))
        
        citizen = {
            'citizen_id': citizen_data[0],
            'name': citizen_data[1],
            'gender': citizen_data[2],
            'dob': citizen_data[3],
            'address': citizen_data[4]
        }
        
        # Get all census records for this citizen
        cur.execute("""
            SELECT cd.census_id, cd.event_type, cd.event_date, h.address
            FROM census_data cd
            JOIN households h ON cd.household_id = h.household_id
            WHERE cd.citizen_id = %s
            ORDER BY cd.event_date DESC
        """, (citizen_id,))
        
        census_records = []
        for record in cur.fetchall():
            census_records.append({
                'census_id': record[0],
                'event_type': record[1],
                'event_date': record[2],
                'address': record[3]
            })
        
        return render_template('employee/citizen_census.html', citizen=citizen, census_records=census_records)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_census'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/census/household/<int:household_id>')
@role_required(['admin', 'panchayat_employee'])
def household_census(household_id):
    conn, cur = get_db_cursor()
    try:
        # Get household information
        cur.execute("""
            SELECT h.household_id, h.address, h.income
            FROM households h
            WHERE h.household_id = %s
        """, (household_id,))
        household_data = cur.fetchone()
        
        if not household_data:
            flash('Household not found.', 'danger')
            return redirect(url_for('employee.manage_census'))
        
        household = {
            'household_id': household_data[0],
            'address': household_data[1],
            'income': household_data[2]
        }
        
        # Get all citizens in the household
        cur.execute("""
            SELECT c.citizen_id, c.name, c.gender, c.dob
            FROM citizens c
            WHERE c.household_id = %s
            ORDER BY c.name
        """, (household_id,))
        
        members = []
        for member in cur.fetchall():
            members.append({
                'citizen_id': member[0],
                'name': member[1],
                'gender': member[2],
                'dob': member[3]
            })
        
        # Get all census records for this household
        cur.execute("""
            SELECT cd.census_id, cd.event_type, cd.event_date, 
                   c.citizen_id, c.name AS citizen_name
            FROM census_data cd
            JOIN citizens c ON cd.citizen_id = c.citizen_id
            WHERE cd.household_id = %s
            ORDER BY cd.event_date DESC
        """, (household_id,))
        
        census_records = []
        for record in cur.fetchall():
            census_records.append({
                'census_id': record[0],
                'event_type': record[1],
                'event_date': record[2],
                'citizen_id': record[3],
                'citizen_name': record[4]
            })
        
        return render_template('employee/household_census.html', 
                              household=household, 
                              members=members,
                              census_records=census_records)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_census'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/census/reports')
@role_required(['admin', 'panchayat_employee'])
def census_reports():
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
        
        return render_template('employee/census_reports.html', statistics=statistics)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_census'))
    finally:
        close_db_connection(conn, cur)        

# Vaccination Management Routes
@employee_bp.route('/vaccinations')
@role_required(['admin', 'panchayat_employee'])
def manage_vaccinations():
    conn, cur = get_db_cursor()
    try:
        # Fetch all vaccination records with citizen information
        cur.execute("""
            SELECT v.vaccination_id, v.vaccine_type, v.date_administered, 
                   c.citizen_id, c.name AS citizen_name, c.gender, c.dob,
                   h.address
            FROM vaccinations v
            JOIN citizens c ON v.citizen_id = c.citizen_id
            JOIN households h ON c.household_id = h.household_id
            ORDER BY v.date_administered DESC
        """)
        records = cur.fetchall()
        
        # Format the data for template
        vaccination_records = []
        for record in records:
            vaccination_records.append({
                'vaccination_id': record[0],
                'vaccine_type': record[1],
                'date_administered': record[2],
                'citizen_id': record[3],
                'citizen_name': record[4],
                'gender': record[5],
                'dob': record[6],
                'address': record[7]
            })
        
        return render_template('employee/manage_vaccinations.html', vaccination_records=vaccination_records)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/vaccinations/add', methods=['GET', 'POST'])
@role_required(['admin', 'panchayat_employee'])
def add_vaccination():
    if request.method == 'POST':
        # Extract form data
        citizen_id = request.form['citizen_id']
        vaccine_type = request.form['vaccine_type']
        date_administered = request.form.get('date_administered') or None
        notes = request.form.get('notes', '')
        
        # Validate required fields
        if not citizen_id or not vaccine_type:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('employee.add_vaccination'))
        
        conn, cur = get_db_cursor()
        try:
            # Check if citizen exists
            cur.execute("SELECT citizen_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
            if not cur.fetchone():
                flash('Citizen not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('employee.add_vaccination'))
            
            # Check if this vaccination already exists for this citizen
            cur.execute("""
                SELECT vaccination_id FROM vaccinations 
                WHERE citizen_id = %s AND vaccine_type = %s AND date_administered = %s
            """, (citizen_id, vaccine_type, date_administered))
            
            if cur.fetchone():
                flash('This vaccination record already exists for this citizen.', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('employee.add_vaccination'))
            
            # Insert new vaccination record
            if date_administered:
                cur.execute(
                    "INSERT INTO vaccinations (citizen_id, vaccine_type, date_administered) VALUES (%s, %s, %s) RETURNING vaccination_id",
                    (citizen_id, vaccine_type, date_administered)
                )
            else:
                cur.execute(
                    "INSERT INTO vaccinations (citizen_id, vaccine_type) VALUES (%s, %s, %s) RETURNING vaccination_id",
                    (citizen_id, vaccine_type)
                )
            vaccination_id = cur.fetchone()[0]
            
            flash(f'Vaccination record added successfully.', 'success')
            return redirect(url_for('employee.manage_vaccinations'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('employee.add_vaccination'))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form
    conn, cur = get_db_cursor()
    try:
        # Get all citizens for dropdown
        cur.execute("""
            SELECT c.citizen_id, c.name, c.dob, h.address
            FROM citizens c
            JOIN households h ON c.household_id = h.household_id
            ORDER BY c.name
        """)
        citizens = cur.fetchall()
        
        # Common vaccine types
        vaccine_types = [
            "BCG", "OPV", "IPV", "DPT", "Hepatitis B", "Measles", 
            "MMR", "TT", "Rotavirus", "PCV", "COVID-19", "Influenza",
            "HPV", "Typhoid", "Chicken Pox", "Hepatitis A"
        ]
        
        return render_template('employee/add_vaccination.html', 
                              citizens=citizens, 
                              vaccine_types=vaccine_types)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_vaccinations'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/vaccinations/edit/<int:vaccination_id>', methods=['GET', 'POST'])
@role_required(['admin', 'panchayat_employee'])
def edit_vaccination(vaccination_id):
    if request.method == 'POST':
        # Extract form data
        citizen_id = request.form['citizen_id']
        vaccine_type = request.form['vaccine_type']
        date_administered = request.form.get('date_administered') or None
        notes = request.form.get('notes', '')
        
        # Validate required fields
        if not citizen_id or not vaccine_type:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('employee.edit_vaccination', vaccination_id=vaccination_id))
        
        conn, cur = get_db_cursor()
        try:
            # Check if citizen exists
            cur.execute("SELECT citizen_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
            if not cur.fetchone():
                flash('Citizen not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('employee.edit_vaccination', vaccination_id=vaccination_id))
            
            # Check if this vaccination already exists for this citizen (excluding current record)
            cur.execute("""
                SELECT vaccination_id FROM vaccinations 
                WHERE citizen_id = %s AND vaccine_type = %s AND date_administered = %s AND vaccination_id != %s
            """, (citizen_id, vaccine_type, date_administered, vaccination_id))
            
            if cur.fetchone():
                flash('This vaccination record already exists for this citizen.', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('employee.edit_vaccination', vaccination_id=vaccination_id))
            
            # Update vaccination record
            if date_administered:
                cur.execute(
                    "UPDATE vaccinations SET citizen_id = %s, vaccine_type = %s, date_administered = %s WHERE vaccination_id = %s",
                    (citizen_id, vaccine_type, date_administered, vaccination_id)
                )
            else:
                cur.execute(
                    "UPDATE vaccinations SET citizen_id = %s, vaccine_type = %s, date_administered = CURRENT_DATE WHERE vaccination_id = %s",
                    (citizen_id, vaccine_type, vaccination_id)
                )
            
            flash('Vaccination record updated successfully.', 'success')
            return redirect(url_for('employee.manage_vaccinations'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('employee.edit_vaccination', vaccination_id=vaccination_id))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form with vaccination record data
    conn, cur = get_db_cursor()
    try:
        # Get vaccination record information
        cur.execute("""
            SELECT v.vaccination_id, v.citizen_id, v.vaccine_type, v.date_administered
            FROM vaccinations v
            WHERE v.vaccination_id = %s
        """, (vaccination_id,))
        record = cur.fetchone()
        
        if not record:
            flash('Vaccination record not found.', 'danger')
            return redirect(url_for('employee.manage_vaccinations'))
        
        vaccination = {
            'vaccination_id': record[0],
            'citizen_id': record[1],
            'vaccine_type': record[2],
            'date_administered': record[3]
        }
        
        # Get all citizens for dropdown
        cur.execute("""
            SELECT c.citizen_id, c.name, c.dob, h.address
            FROM citizens c
            JOIN households h ON c.household_id = h.household_id
            ORDER BY c.name
        """)
        citizens = cur.fetchall()
        
        # Common vaccine types
        vaccine_types = [
            "BCG", "OPV", "IPV", "DPT", "Hepatitis B", "Measles", 
            "MMR", "TT", "Rotavirus", "PCV", "COVID-19", "Influenza",
            "HPV", "Typhoid", "Chicken Pox", "Hepatitis A"
        ]
        
        return render_template('employee/edit_vaccination.html', 
                              vaccination=vaccination,
                              citizens=citizens, 
                              vaccine_types=vaccine_types)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_vaccinations'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/vaccinations/delete/<int:vaccination_id>', methods=['POST'])
@role_required(['admin', 'panchayat_employee'])
def delete_vaccination(vaccination_id):
    conn, cur = get_db_cursor()
    try:
        # Check if vaccination record exists
        cur.execute("SELECT vaccination_id FROM vaccinations WHERE vaccination_id = %s", (vaccination_id,))
        if not cur.fetchone():
            flash('Vaccination record not found.', 'danger')
            return redirect(url_for('employee.manage_vaccinations'))
        
        # Delete the vaccination record
        cur.execute("DELETE FROM vaccinations WHERE vaccination_id = %s", (vaccination_id,))
        
        flash('Vaccination record deleted successfully.', 'success')
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
    finally:
        close_db_connection(conn, cur)
    
    return redirect(url_for('employee.manage_vaccinations'))

@employee_bp.route('/vaccinations/citizen/<int:citizen_id>')
@role_required(['admin', 'panchayat_employee'])
def citizen_vaccinations(citizen_id):
    conn, cur = get_db_cursor()
    try:
        # Get citizen information
        cur.execute("""
            SELECT c.citizen_id, c.name, c.gender, c.dob, h.address
            FROM citizens c
            JOIN households h ON c.household_id = h.household_id
            WHERE c.citizen_id = %s
        """, (citizen_id,))
        citizen_data = cur.fetchone()
        
        if not citizen_data:
            flash('Citizen not found.', 'danger')
            return redirect(url_for('employee.manage_vaccinations'))
        
        citizen = {
            'citizen_id': citizen_data[0],
            'name': citizen_data[1],
            'gender': citizen_data[2],
            'dob': citizen_data[3],
            'address': citizen_data[4]
        }
        
        # Calculate age
        from datetime import datetime
        if citizen['dob']:
            dob = datetime.strptime(str(citizen['dob']), '%Y-%m-%d')
            today = datetime.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            citizen['age'] = age
        else:
            citizen['age'] = None
        
        # Get all vaccination records for this citizen
        cur.execute("""
            SELECT v.vaccination_id, v.vaccine_type, v.date_administered
            FROM vaccinations v
            WHERE v.citizen_id = %s
            ORDER BY v.date_administered DESC
        """, (citizen_id,))
        
        vaccination_records = []
        for record in cur.fetchall():
            vaccination_records.append({
                'vaccination_id': record[0],
                'vaccine_type': record[1],
                'date_administered': record[2]
            })
        
        # Get recommended vaccines based on age
        recommended_vaccines = get_recommended_vaccines(citizen['age'])
        
        # Check which vaccines have been administered
        administered_vaccines = {record['vaccine_type'] for record in vaccination_records}
        
        # Mark recommended vaccines as administered or pending
        for vaccine in recommended_vaccines:
            if vaccine['name'] in administered_vaccines:
                vaccine['status'] = 'administered'
            else:
                vaccine['status'] = 'pending'
        
        return render_template('employee/citizen_vaccinations.html', 
                             citizen=citizen, 
                             vaccination_records=vaccination_records,
                             recommended_vaccines=recommended_vaccines)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_vaccinations'))
    finally:
        close_db_connection(conn, cur)

@employee_bp.route('/vaccinations/reports')
@role_required(['admin', 'panchayat_employee'])
def vaccination_reports():
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
        
        return render_template('employee/vaccination_reports.html', statistics=statistics)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('employee.manage_vaccinations'))
    finally:
        close_db_connection(conn, cur)

# Helper function to get recommended vaccines based on age
def get_recommended_vaccines(age):
    # Define recommended vaccines by age group
    if age is None:
        return []
    
    recommended = []
    
    # For infants and young children (0-5 years)
    if age <= 5:
        recommended.extend([
            {'name': 'BCG', 'description': 'Tuberculosis vaccine', 'recommended_age': 'At birth'},
            {'name': 'Hepatitis B', 'description': 'Prevents hepatitis B', 'recommended_age': '0-6 months'},
            {'name': 'OPV', 'description': 'Oral polio vaccine', 'recommended_age': '6, 10, 14 weeks'},
            {'name': 'IPV', 'description': 'Inactivated polio vaccine', 'recommended_age': '14 weeks'},
            {'name': 'DPT', 'description': 'Diphtheria, Pertussis, Tetanus', 'recommended_age': '6, 10, 14 weeks'},
            {'name': 'Rotavirus', 'description': 'Prevents rotavirus diarrhea', 'recommended_age': '6, 10, 14 weeks'},
            {'name': 'PCV', 'description': 'Pneumococcal conjugate vaccine', 'recommended_age': '6, 10, 14 weeks'},
            {'name': 'Measles', 'description': 'Prevents measles', 'recommended_age': '9-12 months'},
            {'name': 'MMR', 'description': 'Measles, Mumps, Rubella', 'recommended_age': '16-24 months'},
            {'name': 'Typhoid', 'description': 'Prevents typhoid fever', 'recommended_age': '2 years+'},
            {'name': 'Hepatitis A', 'description': 'Prevents hepatitis A', 'recommended_age': '1-2 years'}
        ])
    
    # For children and adolescents (6-18 years)
    elif age <= 18:
        recommended.extend([
            {'name': 'TT', 'description': 'Tetanus Toxoid', 'recommended_age': '10 and 16 years'},
            {'name': 'Typhoid', 'description': 'Prevents typhoid fever', 'recommended_age': 'Every 3 years'},
            {'name': 'HPV', 'description': 'Human Papillomavirus vaccine', 'recommended_age': '9-14 years (girls)'}
        ])
    
    # For adults (19-64 years)
    elif age <= 64:
        recommended.extend([
            {'name': 'TT', 'description': 'Tetanus booster', 'recommended_age': 'Every 10 years'},
            {'name': 'Influenza', 'description': 'Seasonal flu vaccine', 'recommended_age': 'Annually'},
            {'name': 'COVID-19', 'description': 'Coronavirus vaccine', 'recommended_age': 'As per guidelines'}
        ])
    
    # For elderly (65+ years)
    else:
        recommended.extend([
            {'name': 'Influenza', 'description': 'Seasonal flu vaccine', 'recommended_age': 'Annually'},
            {'name': 'COVID-19', 'description': 'Coronavirus vaccine', 'recommended_age': 'As per guidelines'},
            {'name': 'Pneumococcal', 'description': 'Prevents pneumonia', 'recommended_age': 'Once after 65'}
        ])
    
    return recommended