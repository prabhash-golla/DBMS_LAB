from flask import Flask, render_template, redirect, url_for, flash, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import psycopg2
from database.db_config import get_db_connection, get_db_cursor, close_db_connection
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Custom decorator for role-based access control
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role_id = request.form['role_id']
        
        # Hash the password
        password_hash = generate_password_hash(password)
        
        # Connect to database and insert user
        conn, cur = get_db_cursor()
        try:
            # Check if username or email already exists
            cur.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, email))
            if cur.fetchone():
                flash('Username or email already exists', 'danger')
                close_db_connection(conn, cur)
                # Get roles again before rendering the template
                conn_roles, cur_roles = get_db_cursor()
                cur_roles.execute("SELECT role_id, role_name FROM user_roles")
                roles = cur_roles.fetchall()
                close_db_connection(conn_roles, cur_roles)
                return render_template('register.html', roles=roles)
            
            # Insert new user
            cur.execute(
                "INSERT INTO users (username, email, password_hash, role_id) VALUES (%s, %s, %s, %s) RETURNING user_id",
                (username, email, password_hash, role_id)
            )
            user_id = cur.fetchone()[0]
            
            # If registering as a citizen, collect additional information
            if int(role_id) == 3:  # Citizen role ID
                # Get citizen details from form
                name = request.form['name']
                gender = request.form.get('gender')
                dob = request.form.get('dob')
                education = request.form.get('education')
                
                # Validate required citizen fields
                if not name or not gender or not dob:
                    flash('Please fill in all required citizen information fields (Name, Gender, and Date of Birth).', 'danger')
                    close_db_connection(conn, cur)
                    # Get roles again before rendering the template
                    conn_roles, cur_roles = get_db_cursor()
                    cur_roles.execute("SELECT role_id, role_name FROM user_roles")
                    roles = cur_roles.fetchall()
                    close_db_connection(conn_roles, cur_roles)
                    return render_template('register.html', roles=roles)
                
                # Check for household existence
                household_exists = request.form.get('household_exists')
                
                # Debug logging
                print(f"Processing citizen registration for {name}")
                print(f"Household exists: {household_exists}")
                
                if household_exists == 'yes':
                    # Use existing household
                    household_id = request.form.get('existing_household_id')
                    
                    if not household_id:
                        flash('Household ID is required when using an existing household', 'danger')
                        close_db_connection(conn, cur)
                        # Get roles again before rendering the template
                        conn_roles, cur_roles = get_db_cursor()
                        cur_roles.execute("SELECT role_id, role_name FROM user_roles")
                        roles = cur_roles.fetchall()
                        close_db_connection(conn_roles, cur_roles)
                        return render_template('register.html', roles=roles)
                    
                    # Verify household exists
                    cur.execute("SELECT * FROM households WHERE household_id = %s", (household_id,))
                    if not cur.fetchone():
                        flash('Household ID not found', 'danger')
                        close_db_connection(conn, cur)
                        # Get roles again before rendering the template
                        conn_roles, cur_roles = get_db_cursor()
                        cur_roles.execute("SELECT role_id, role_name FROM user_roles")
                        roles = cur_roles.fetchall()
                        close_db_connection(conn_roles, cur_roles)
                        return render_template('register.html', roles=roles)
                else:
                    # Create a new household
                    household_address = request.form.get('address')
                    household_income = request.form.get('income', 0)
                    
                    # Convert empty string to 0 for income
                    if household_income == '':
                        household_income = 0
                    
                    if not household_address:
                        flash('Address is required for a new household', 'danger')
                        close_db_connection(conn, cur)
                        # Get roles again before rendering the template
                        conn_roles, cur_roles = get_db_cursor()
                        cur_roles.execute("SELECT role_id, role_name FROM user_roles")
                        roles = cur_roles.fetchall()
                        close_db_connection(conn_roles, cur_roles)
                        return render_template('register.html', roles=roles)

                    try:
                        # Create household
                        cur.execute(
                            "INSERT INTO households (address, income) VALUES (%s, %s) RETURNING household_id",
                            (household_address, household_income)
                        )
                        household_id = cur.fetchone()[0]
                        print(f"Created new household with ID: {household_id}")
                    except Exception as e:
                        print(f"Error creating household: {str(e)}")
                        flash(f'Error creating household: {str(e)}', 'danger')
                        close_db_connection(conn, cur)
                        # Get roles again before rendering the template
                        conn_roles, cur_roles = get_db_cursor()
                        cur_roles.execute("SELECT role_id, role_name FROM user_roles")
                        roles = cur_roles.fetchall()
                        close_db_connection(conn_roles, cur_roles)
                        return render_template('register.html', roles=roles)
                
                try:
                    # Create citizen record
                    cur.execute(
                        "INSERT INTO citizens (name, gender, dob, household_id, educational_qualification, user_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING citizen_id",
                        (name, gender, dob, household_id, education, user_id)
                    )
                    citizen_id = cur.fetchone()[0]
                    print(f"Created citizen with ID: {citizen_id}")
                except Exception as e:
                    print(f"Error creating citizen: {str(e)}")
                    flash(f'Error creating citizen record: {str(e)}', 'danger')
                    close_db_connection(conn, cur)
                    # Get roles again before rendering the template
                    conn_roles, cur_roles = get_db_cursor()
                    cur_roles.execute("SELECT role_id, role_name FROM user_roles")
                    roles = cur_roles.fetchall()
                    close_db_connection(conn_roles, cur_roles)
                    return render_template('register.html', roles=roles)
            
            # If registering as a panchayat employee
            elif int(role_id) == 2:  # Panchayat employee role ID
                # Employees must have an existing citizen ID
                citizen_id = request.form.get('existing_citizen_id')
                employee_role = request.form.get('employee_role')
                
                if not citizen_id:
                    flash('Citizen ID is required for employee registration. Please register as a citizen first.', 'danger')
                    close_db_connection(conn, cur)
                    # Get roles again before rendering the template
                    conn_roles, cur_roles = get_db_cursor()
                    cur_roles.execute("SELECT role_id, role_name FROM user_roles")
                    roles = cur_roles.fetchall()
                    close_db_connection(conn_roles, cur_roles)
                    return render_template('register.html', roles=roles)
                
                # Verify citizen exists
                cur.execute("SELECT * FROM citizens WHERE citizen_id = %s", (citizen_id,))
                if not cur.fetchone():
                    flash('Citizen ID not found. Please provide a valid Citizen ID.', 'danger')
                    close_db_connection(conn, cur)
                    # Get roles again before rendering the template
                    conn_roles, cur_roles = get_db_cursor()
                    cur_roles.execute("SELECT role_id, role_name FROM user_roles")
                    roles = cur_roles.fetchall()
                    close_db_connection(conn_roles, cur_roles)
                    return render_template('register.html', roles=roles)
                
                # Check if citizen is already an employee
                cur.execute("SELECT * FROM panchayat_employees WHERE citizen_id = %s", (citizen_id,))
                if cur.fetchone():
                    flash('This Citizen ID is already registered as an employee.', 'danger')
                    close_db_connection(conn, cur)
                    # Get roles again before rendering the template
                    conn_roles, cur_roles = get_db_cursor()
                    cur_roles.execute("SELECT role_id, role_name FROM user_roles")
                    roles = cur_roles.fetchall()
                    close_db_connection(conn_roles, cur_roles)
                    return render_template('register.html', roles=roles)
                    
                # Add employee record with user_id and citizen_id reference
                cur.execute(
                    "INSERT INTO panchayat_employees (citizen_id, role, user_id) VALUES (%s, %s, %s)",
                    (citizen_id, employee_role, user_id)
                )
            
            flash('Registration successful! You can now log in.', 'success')
            close_db_connection(conn, cur)
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            close_db_connection(conn, cur)
            # Get roles again before rendering the template
            conn_roles, cur_roles = get_db_cursor()
            cur_roles.execute("SELECT role_id, role_name FROM user_roles")
            roles = cur_roles.fetchall()
            close_db_connection(conn_roles, cur_roles)
            return render_template('register.html', roles=roles)
    
    # GET request - display registration form
    conn, cur = get_db_cursor()
    cur.execute("SELECT role_id, role_name FROM user_roles")
    roles = cur.fetchall()
    close_db_connection(conn, cur)
    # Get roles again before rendering the template
    conn_roles, cur_roles = get_db_cursor()
    cur_roles.execute("SELECT role_id, role_name FROM user_roles")
    roles = cur_roles.fetchall()
    close_db_connection(conn_roles, cur_roles)
    return render_template('register.html', roles=roles)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn, cur = get_db_cursor()
        cur.execute(
            "SELECT u.user_id, u.username, u.password_hash, r.role_name FROM users u JOIN user_roles r ON u.role_id = r.role_id WHERE u.username = %s",
            (username,)
        )
        user = cur.fetchone()
        close_db_connection(conn, cur)
        
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[3]
            flash(f'Welcome back, {username}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please log in to access the dashboard', 'warning')
        return redirect(url_for('login'))
    
    # Different dashboard views based on user role
    role = session.get('role')
    
    if role == 'admin':
        return render_template('dashboard/admin.html')
    elif role == 'panchayat_employee':
        return render_template('dashboard/employee.html')
    elif role == 'citizen':
        return render_template('dashboard/citizen.html')
    elif role == 'government_monitor':
        return render_template('dashboard/monitor.html')
    else:
        flash('Invalid role', 'danger')
        return redirect(url_for('logout'))

# Example of a role-restricted route
@app.route('/admin/users')
@role_required(['admin'])
def admin_users():
    conn, cur = get_db_cursor()
    cur.execute(
        "SELECT u.user_id, u.username, u.email, r.role_name FROM users u JOIN user_roles r ON u.role_id = r.role_id"
    )
    users = cur.fetchall()
    close_db_connection(conn, cur)
    return render_template('admin/users.html', users=users)

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash('Please log in to view your profile', 'warning')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    role = session.get('role')
    
    conn, cur = get_db_cursor()
    
    if role == 'citizen':
        # Fetch citizen information
        cur.execute("""
            SELECT c.citizen_id, c.name, c.gender, c.dob, c.educational_qualification, 
                   h.household_id, h.address, h.income
            FROM citizens c
            JOIN households h ON c.household_id = h.household_id
            WHERE c.user_id = %s
        """, (user_id,))
        citizen_data = cur.fetchone()
        
        if citizen_data:
            citizen_info = {
                'citizen_id': citizen_data[0],
                'name': citizen_data[1],
                'gender': citizen_data[2],
                'dob': citizen_data[3],
                'education': citizen_data[4],
                'household_id': citizen_data[5],
                'address': citizen_data[6],
                'household_income': citizen_data[7]
            }
            
            # Fetch household members
            cur.execute("""
                SELECT c.citizen_id, c.name, c.gender, c.dob
                FROM citizens c
                WHERE c.household_id = %s AND c.citizen_id != %s
            """, (citizen_info['household_id'], citizen_info['citizen_id']))
            
            household_members = []
            for member in cur.fetchall():
                household_members.append({
                    'citizen_id': member[0],
                    'name': member[1],
                    'gender': member[2],
                    'dob': member[3]
                })
            
            # Fetch welfare scheme enrollments
            cur.execute("""
                SELECT ws.name, ws.description, se.enrollment_date
                FROM scheme_enrollments se
                JOIN welfare_schemes ws ON se.scheme_id = ws.scheme_id
                WHERE se.citizen_id = %s
            """, (citizen_info['citizen_id'],))
            
            schemes = []
            for scheme in cur.fetchall():
                schemes.append({
                    'name': scheme[0],
                    'description': scheme[1],
                    'enrollment_date': scheme[2]
                })
            
            # Fetch vaccination records
            cur.execute("""
                SELECT vaccine_type, date_administered
                FROM vaccinations
                WHERE citizen_id = %s
            """, (citizen_info['citizen_id'],))
            
            vaccinations = []
            for vax in cur.fetchall():
                vaccinations.append({
                    'vaccine_type': vax[0],
                    'date': vax[1]
                })
            
            # Fetch land records
            cur.execute("""
                SELECT land_id, area_acres, crop_type
                FROM land_records
                WHERE citizen_id = %s
            """, (citizen_info['citizen_id'],))
            
            land_records = []
            for record in cur.fetchall():
                land_records.append({
                    'land_id': record[0],
                    'area': record[1],
                    'crop_type': record[2]
                })
            
            close_db_connection(conn, cur)
            return render_template(
                'profile/citizen_profile.html',
                citizen=citizen_info,
                household_members=household_members,
                schemes=schemes,
                vaccinations=vaccinations,
                land_records=land_records
            )
        else:
            flash('Citizen profile not found', 'danger')
            close_db_connection(conn, cur)
            return redirect(url_for('dashboard'))
            
    elif role == 'panchayat_employee':
        # Fetch employee information using the user_id field in panchayat_employees table
        cur.execute("""
            SELECT e.employee_id, e.role, e.joining_date, e.citizen_id,
                   c.name, c.gender, c.dob, c.educational_qualification,
                   h.household_id, h.address
            FROM panchayat_employees e
            JOIN citizens c ON e.citizen_id = c.citizen_id
            JOIN households h ON c.household_id = h.household_id
            WHERE e.user_id = %s
        """, (user_id,))
        
        employee_data = cur.fetchone()
        
        if employee_data:
            employee_info = {
                'employee_id': employee_data[0],
                'role': employee_data[1],
                'joining_date': employee_data[2],
                'citizen_id': employee_data[3],
                'name': employee_data[4],
                'gender': employee_data[5],
                'dob': employee_data[6],
                'education': employee_data[7],
                'household_id': employee_data[8],
                'address': employee_data[9]
            }
            
            close_db_connection(conn, cur)
            return render_template('profile/employee_profile.html', employee=employee_info)
        else:
            flash('Employee profile not found', 'danger')
            close_db_connection(conn, cur)
            return redirect(url_for('dashboard'))
    
    else:
        close_db_connection(conn, cur)
        return render_template('profile/user_profile.html')

# ------------------------------------------------------------------------------ #
# ----------------------------- EMPLOYEE DASHBOARD ------------------------- #
# ------------------------------------------------------------------------------ #

# Routes for Citizen Management by Employees
@app.route('/employee/citizens')
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

@app.route('/employee/citizens/add', methods=['GET', 'POST'])
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
            return redirect(url_for('add_citizen'))
        
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
                    return redirect(url_for('add_citizen'))
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
                    return redirect(url_for('add_citizen'))
                
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
                    return redirect(url_for('add_citizen'))
                
                # Check if username or email already exists
                cur.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, email))
                if cur.fetchone():
                    flash('Username or email already exists', 'danger')
                    close_db_connection(conn, cur)
                    return redirect(url_for('add_citizen'))
                
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
            return redirect(url_for('manage_citizens'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('add_citizen'))
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
        return redirect(url_for('manage_citizens'))
    finally:
        close_db_connection(conn, cur)

@app.route('/employee/citizens/edit/<int:citizen_id>', methods=['GET', 'POST'])
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
            return redirect(url_for('edit_citizen', citizen_id=citizen_id))
        
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
            return redirect(url_for('manage_citizens'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('edit_citizen', citizen_id=citizen_id))
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
            return redirect(url_for('manage_citizens'))
        
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
        return redirect(url_for('manage_citizens'))
    finally:
        close_db_connection(conn, cur)
@app.route('/employee/citizens/delete/<int:citizen_id>', methods=['POST'])
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
            return redirect(url_for('manage_citizens'))
        
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
    
    return redirect(url_for('manage_citizens'))

@app.route('/employee/citizens/view/<int:citizen_id>')
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
            return redirect(url_for('manage_citizens'))
        
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
        return redirect(url_for('manage_citizens'))
    finally:
        close_db_connection(conn, cur)

# ------------------------------------------------------------------------------ #


# Initialize database tables
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Read schema.sql file
    with open('database/schema.sql', 'r') as f:
        schema = f.read()
    
    # Execute the SQL commands
    cur.execute(schema)
    conn.commit()
    
    cur.close()
    conn.close()
    print("Database initialized successfully")

if __name__ == '__main__':
    # Uncomment to initialize the database on first run
    # init_db()
    app.run(debug=True, use_reloader=False)    