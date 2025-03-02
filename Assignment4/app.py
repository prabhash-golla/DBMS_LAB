from flask import Flask, render_template, redirect, url_for, flash, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import psycopg2
from database.db_config import get_db_connection, get_db_cursor, close_db_connection
from config import Config

# Import the blueprints
from employee_routes import employee_bp
from citizen_routes import citizen_bp
from monitor_routes import monitor_bp  
from admin_routes import admin_bp 

app = Flask(__name__)
app.config.from_object(Config)

# Register blueprints
app.register_blueprint(employee_bp)
app.register_blueprint(citizen_bp) 
app.register_blueprint(monitor_bp)
app.register_blueprint(admin_bp)  

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
        
        # Connect to database
        conn, cur = get_db_cursor()

        try:
            # Check if username or email already exists
            cur.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, email))
            if cur.fetchone():
                flash('Username or email already exists', 'danger')
                
                close_db_connection(conn, cur)
                
                # Get roles again for the registration form
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
                    
                    # Get roles again
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
                        
                        # Get roles again
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
                        
                        # Get roles again
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
                        
                        # Get roles again
                        conn_roles, cur_roles = get_db_cursor()
                        cur_roles.execute("SELECT role_id, role_name FROM user_roles")
                        roles = cur_roles.fetchall()
                        close_db_connection(conn_roles, cur_roles)
                        
                        return render_template('register.html', roles=roles)

                    # Create household
                    cur.execute(
                        "INSERT INTO households (address, income) VALUES (%s, %s) RETURNING household_id",
                        (household_address, household_income)
                    )
                    household_id = cur.fetchone()[0]
                    print(f"Created new household with ID: {household_id}")
                
                # Create citizen record
                cur.execute(
                    "INSERT INTO citizens (name, gender, dob, household_id, educational_qualification, user_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING citizen_id",
                    (name, gender, dob, household_id, education, user_id)
                )
                citizen_id = cur.fetchone()[0]
                print(f"Created citizen with ID: {citizen_id}")
            
            # If registering as a panchayat employee
            elif int(role_id) == 2:  # Panchayat employee role ID
                # Employees must have an existing citizen ID
                citizen_id = request.form.get('existing_citizen_id')
                employee_role = request.form.get('employee_role')
                
                if not citizen_id:
                    flash('Citizen ID is required for employee registration. Please register as a citizen first.', 'danger')
                    
                    close_db_connection(conn, cur)
                    
                    # Get roles again
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
                    
                    # Get roles again
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
                    
                    # Get roles again
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
            
            # If we get here, everything succeeded, so commit the transaction
            conn.commit()
            
            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            # If any error occurs, roll back the entire transaction
            flash(f'An error occurred: {str(e)}', 'danger')
            
            # Get roles again
            conn_roles, cur_roles = get_db_cursor()
            cur_roles.execute("SELECT role_id, role_name FROM user_roles")
            roles = cur_roles.fetchall()
            close_db_connection(conn_roles, cur_roles)
            
            return render_template('register.html', roles=roles)
        finally:
            
            close_db_connection(conn, cur)
    
    # GET request - display registration form
    conn, cur = get_db_cursor()
    cur.execute("SELECT role_id, role_name FROM user_roles")
    roles = cur.fetchall()
    close_db_connection(conn, cur)
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
        # Initialize village_stats with default values
        village_stats = {
            'population': 0,
            'families': 0,
            'land_area': 0,
            'schemes': 0
        }
        
        # Try to get actual data
        try:
            conn, cur = get_db_cursor()
            
            # Get population count
            cur.execute("SELECT COUNT(*) FROM citizens")
            village_stats['population'] = cur.fetchone()[0]
            
            # Get household count
            cur.execute("SELECT COUNT(DISTINCT household_id) FROM households")
            village_stats['families'] = cur.fetchone()[0]
            
            # Get total land area
            cur.execute("SELECT SUM(area_acres) FROM land_records")
            total_area = cur.fetchone()[0]
            village_stats['land_area'] = total_area if total_area else 0
            
            # Get count of welfare schemes
            cur.execute("SELECT COUNT(*) FROM welfare_schemes")
            village_stats['schemes'] = cur.fetchone()[0]
            
            close_db_connection(conn, cur)
        except Exception as e:
            print(f"Error fetching village stats: {e}")
            # If there's an error, we'll use the default values initialized above
        
        return render_template('dashboard/citizen.html', village_stats=village_stats)
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