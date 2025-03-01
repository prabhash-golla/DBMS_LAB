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