from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from werkzeug.security import generate_password_hash
from functools import wraps
from database.db_config import get_db_cursor, close_db_connection
from datetime import datetime

# Create the admin blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('login'))
        
        if session.get('role') != 'admin':
            flash('You must be logged in as an admin to access this page', 'danger')
            return redirect(url_for('dashboard'))
            
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin/dashboard.html')

# ===== User Management =====
@admin_bp.route('/users')
@admin_required
def manage_users():
    conn, cur = get_db_cursor()
    try:
        # Fetch all users with their roles
        cur.execute("""
            SELECT u.user_id, u.username, u.email, r.role_name, u.is_active, u.created_at
            FROM users u
            JOIN user_roles r ON u.role_id = r.role_id
            ORDER BY u.user_id
        """)
        users = cur.fetchall()
        
        # Format the data for template
        users_data = []
        for user in users:
            users_data.append({
                'user_id': user[0],
                'username': user[1],
                'email': user[2],
                'role': user[3],
                'is_active': user[4],
                'created_at': user[5]
            })
        
        return render_template('admin/manage_users.html', users=users_data)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.admin_dashboard'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/users/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role_id = request.form['role_id']
        
        # Validate input
        if not username or not email or not password or not role_id:
            flash('All fields are required', 'danger')
            return redirect(url_for('admin.add_user'))
        
        # Hash the password
        password_hash = generate_password_hash(password)
        
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
                
                return render_template('admin/add_user.html', roles=roles)
            
            # Insert the new user
            cur.execute(
                "INSERT INTO users (username, email, password_hash, role_id) VALUES (%s, %s, %s, %s) RETURNING user_id",
                (username, email, password_hash, role_id)
            )
            user_id = cur.fetchone()[0]
            
            flash(f'User "{username}" added successfully with ID: {user_id}', 'success')
            return redirect(url_for('admin.manage_users'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.add_user'))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form
    conn, cur = get_db_cursor()
    try:
        # Get all roles for dropdown
        cur.execute("SELECT role_id, role_name FROM user_roles")
        roles = cur.fetchall()
        return render_template('admin/add_user.html', roles=roles)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_users'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    # Check if user is trying to modify their own account
    if int(session.get('user_id')) == user_id:
        flash('You cannot modify your own admin account from this interface', 'warning')
        return redirect(url_for('admin.manage_users'))
    
    if request.method == 'POST':
        email = request.form['email']
        role_id = request.form['role_id']
        is_active = 'is_active' in request.form
        new_password = request.form.get('new_password')
        
        conn, cur = get_db_cursor()
        try:
            # Check if email already exists for another user
            cur.execute("SELECT user_id FROM users WHERE email = %s AND user_id != %s", (email, user_id))
            if cur.fetchone():
                flash('Email already exists for another user', 'danger')
                close_db_connection(conn, cur)
                
                # Get roles and user data again
                conn, cur = get_db_cursor()
                cur.execute("SELECT role_id, role_name FROM user_roles")
                roles = cur.fetchall()
                
                cur.execute("""
                    SELECT user_id, username, email, role_id, is_active
                    FROM users
                    WHERE user_id = %s
                """, (user_id,))
                user = cur.fetchone()
                close_db_connection(conn, cur)
                
                if not user:
                    flash('User not found', 'danger')
                    return redirect(url_for('admin.manage_users'))
                
                user_data = {
                    'user_id': user[0],
                    'username': user[1],
                    'email': user[2],
                    'role_id': user[3],
                    'is_active': user[4]
                }
                
                return render_template('admin/edit_user.html', user=user_data, roles=roles)
            
            # Update the user
            if new_password:
                # If password is provided, update it too
                password_hash = generate_password_hash(new_password)
                cur.execute(
                    """
                    UPDATE users 
                    SET email = %s, role_id = %s, password_hash = %s, is_active = %s
                    WHERE user_id = %s
                    """,
                    (email, role_id, password_hash, is_active, user_id)
                )
            else:
                # Otherwise just update the other fields
                cur.execute(
                    """
                    UPDATE users 
                    SET email = %s, role_id = %s, is_active = %s
                    WHERE user_id = %s
                    """,
                    (email, role_id, is_active, user_id)
                )
            
            flash('User updated successfully', 'success')
            return redirect(url_for('admin.manage_users'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form with user data
    conn, cur = get_db_cursor()
    try:
        # Get user information
        cur.execute("""
            SELECT user_id, username, email, role_id, is_active
            FROM users
            WHERE user_id = %s
        """, (user_id,))
        user = cur.fetchone()
        
        if not user:
            flash('User not found', 'danger')
            return redirect(url_for('admin.manage_users'))
        
        user_data = {
            'user_id': user[0],
            'username': user[1],
            'email': user[2],
            'role_id': user[3],
            'is_active': user[4]
        }
        
        # Get all roles for dropdown
        cur.execute("SELECT role_id, role_name FROM user_roles")
        roles = cur.fetchall()
        
        return render_template('admin/edit_user.html', user=user_data, roles=roles)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_users'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    # Check if user is trying to delete their own account
    if int(session.get('user_id')) == user_id:
        flash('You cannot delete your own admin account', 'danger')
        return redirect(url_for('admin.manage_users'))
    
    conn, cur = get_db_cursor()
    try:
        # Start a transaction
        conn.autocommit = False
        
        # Get user role to handle dependent records
        cur.execute("SELECT username, role_id FROM users WHERE user_id = %s", (user_id,))
        user_info = cur.fetchone()
        
        if not user_info:
            flash('User not found', 'danger')
            conn.rollback()
            return redirect(url_for('admin.manage_users'))
        
        username, role_id = user_info
        
        # Check if the user is linked to a citizen or employee
        citizen_id = None
        employee_id = None
        
        # Check for citizen link
        cur.execute("SELECT citizen_id FROM citizens WHERE user_id = %s", (user_id,))
        citizen_result = cur.fetchone()
        if citizen_result:
            citizen_id = citizen_result[0]
        
        # Check for employee link
        cur.execute("SELECT employee_id FROM panchayat_employees WHERE user_id = %s", (user_id,))
        employee_result = cur.fetchone()
        if employee_result:
            employee_id = employee_result[0]
        
        # Handle dependent records based on role
        if role_id == 3:  # Citizen role ID
            if citizen_id:
                # First delete any scheme enrollments
                cur.execute("DELETE FROM scheme_enrollments WHERE citizen_id = %s", (citizen_id,))
                
                # Delete any vaccinations
                cur.execute("DELETE FROM vaccinations WHERE citizen_id = %s", (citizen_id,))
                
                # Delete any land records
                cur.execute("DELETE FROM land_records WHERE citizen_id = %s", (citizen_id,))
                
                # Delete any census data
                cur.execute("DELETE FROM census_data WHERE citizen_id = %s", (citizen_id,))
                
                # Delete the citizen record
                cur.execute("DELETE FROM citizens WHERE citizen_id = %s", (citizen_id,))
        
        elif role_id == 2:  # Panchayat employee role ID
            if employee_id:
                # Delete the employee record
                cur.execute("DELETE FROM panchayat_employees WHERE employee_id = %s", (employee_id,))
                
                # If the employee is also a citizen and has a citizen record, delete that too
                if citizen_id:
                    # First delete any scheme enrollments
                    cur.execute("DELETE FROM scheme_enrollments WHERE citizen_id = %s", (citizen_id,))
                    
                    # Delete any vaccinations
                    cur.execute("DELETE FROM vaccinations WHERE citizen_id = %s", (citizen_id,))
                    
                    # Delete any land records
                    cur.execute("DELETE FROM land_records WHERE citizen_id = %s", (citizen_id,))
                    
                    # Delete any census data
                    cur.execute("DELETE FROM census_data WHERE citizen_id = %s", (citizen_id,))
                    
                    # Delete the citizen record
                    cur.execute("DELETE FROM citizens WHERE citizen_id = %s", (citizen_id,))
        
        # Finally, delete the user
        cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        
        # Commit the transaction
        conn.commit()
        flash(f'User "{username}" and all associated records deleted successfully', 'success')
    except Exception as e:
        # Rollback the transaction on error
        conn.rollback()
        flash(f'An error occurred: {str(e)}', 'danger')
    finally:
        # Restore autocommit mode
        conn.autocommit = True
        close_db_connection(conn, cur)
    
    return redirect(url_for('admin.manage_users'))

# ===== Citizens Management =====
@admin_bp.route('/citizens')
@admin_required
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
        
        return render_template('admin/manage_citizens.html', citizens=citizens_data)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.admin_dashboard'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/citizens/view/<int:citizen_id>')
@admin_required
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
            return redirect(url_for('admin.manage_citizens'))
        
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
        
        # Check if citizen is a panchayat employee
        cur.execute(
            """
            SELECT e.employee_id, e.role, e.joining_date
            FROM panchayat_employees e
            WHERE e.citizen_id = %s
            """,
            (citizen_id,)
        )
        employee_data = cur.fetchone()
        
        employee_info = None
        if employee_data:
            employee_info = {
                'employee_id': employee_data[0],
                'role': employee_data[1],
                'joining_date': employee_data[2]
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
            'admin/view_citizen.html',
            citizen=citizen,
            employee_info=employee_info,
            household_members=household_members,
            schemes=schemes,
            vaccinations=vaccinations,
            land_records=land_records
        )
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_citizens'))
    finally:
        close_db_connection(conn, cur)


@admin_bp.route('/citizens/add', methods=['GET', 'POST'])
@admin_required
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
            return redirect(url_for('admin.add_citizen'))
        
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
                    return redirect(url_for('admin.add_citizen'))
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
                    return redirect(url_for('admin.add_citizen'))
                
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
                    return redirect(url_for('admin.add_citizen'))
                
                # Check if username or email already exists
                cur.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, email))
                if cur.fetchone():
                    flash('Username or email already exists', 'danger')
                    close_db_connection(conn, cur)
                    return redirect(url_for('admin.add_citizen'))
                
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
            return redirect(url_for('admin.manage_citizens'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.add_citizen'))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form
    conn, cur = get_db_cursor()
    try:
        # Get all households for dropdown
        cur.execute("SELECT household_id, address FROM households ORDER BY household_id")
        households = cur.fetchall()
        return render_template('admin/add_citizen.html', households=households)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_citizens'))
    finally:
        close_db_connection(conn, cur)


@admin_bp.route('/citizens/edit/<int:citizen_id>', methods=['GET', 'POST'])
@admin_required
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
            return redirect(url_for('admin.edit_citizen', citizen_id=citizen_id))
        
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
            return redirect(url_for('admin.manage_citizens'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.edit_citizen', citizen_id=citizen_id))
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
            return redirect(url_for('admin.manage_citizens'))
        
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
        
        return render_template('admin/edit_citizen.html', citizen=citizen_data, households=households)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_citizens'))
    finally:
        close_db_connection(conn, cur)


@admin_bp.route('/citizens/delete/<int:citizen_id>', methods=['POST'])
@admin_required
def delete_citizen(citizen_id):
    conn, cur = get_db_cursor()
    try:
        # Start a transaction
        conn.autocommit = False
        
        # First check if citizen exists
        cur.execute("SELECT citizen_id, user_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
        citizen_data = cur.fetchone()
        
        if not citizen_data:
            flash('Citizen not found.', 'danger')
            conn.rollback()
            return redirect(url_for('admin.manage_citizens'))
        
        citizen_user_id = citizen_data[1]
        
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
                cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        
        # Commit the transaction
        conn.commit()
        
        flash('Citizen and all associated records deleted successfully.', 'success')
    except Exception as e:
        # Rollback in case of error
        conn.rollback()
        flash(f'An error occurred: {str(e)}', 'danger')
    finally:
        # Restore autocommit mode
        conn.autocommit = True
        close_db_connection(conn, cur)
    
    return redirect(url_for('admin.manage_citizens'))

# ===== Household Management =====
@admin_bp.route('/households')
@admin_required
def manage_households():
    conn, cur = get_db_cursor()
    try:
        # Fetch all households with count of members
        cur.execute("""
            SELECT h.household_id, h.address, h.income, 
                   (SELECT COUNT(*) FROM citizens WHERE household_id = h.household_id) as member_count
            FROM households h
            ORDER BY h.household_id
        """)
        households = cur.fetchall()
        
        # Format the data for template
        households_data = []
        for household in households:
            households_data.append({
                'household_id': household[0],
                'address': household[1],
                'income': household[2],
                'member_count': household[3]
            })
        
        return render_template('admin/manage_households.html', households=households_data)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.admin_dashboard'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/households/add', methods=['GET', 'POST'])
@admin_required
def add_household():
    if request.method == 'POST':
        address = request.form['address']
        income = request.form.get('income', 0)
        
        # Convert empty string to 0 for income
        if income == '':
            income = 0
        
        # Validate input
        if not address:
            flash('Address is required', 'danger')
            return redirect(url_for('admin.add_household'))
        
        conn, cur = get_db_cursor()
        try:
            # Insert the new household
            cur.execute(
                "INSERT INTO households (address, income) VALUES (%s, %s) RETURNING household_id",
                (address, income)
            )
            household_id = cur.fetchone()[0]
            
            flash(f'Household added successfully with ID: {household_id}', 'success')
            return redirect(url_for('admin.manage_households'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.add_household'))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form
    return render_template('admin/add_household.html')

@admin_bp.route('/households/edit/<int:household_id>', methods=['GET', 'POST'])
@admin_required
def edit_household(household_id):
    if request.method == 'POST':
        address = request.form['address']
        income = request.form.get('income', 0)
        
        # Convert empty string to 0 for income
        if income == '':
            income = 0
        
        # Validate input
        if not address:
            flash('Address is required', 'danger')
            return redirect(url_for('admin.edit_household', household_id=household_id))
        
        conn, cur = get_db_cursor()
        try:
            # Update the household
            cur.execute(
                "UPDATE households SET address = %s, income = %s WHERE household_id = %s",
                (address, income, household_id)
            )
            
            flash('Household updated successfully', 'success')
            return redirect(url_for('admin.manage_households'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.edit_household', household_id=household_id))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form with household data
    conn, cur = get_db_cursor()
    try:
        # Get household information
        cur.execute("SELECT household_id, address, income FROM households WHERE household_id = %s", (household_id,))
        household = cur.fetchone()
        
        if not household:
            flash('Household not found', 'danger')
            return redirect(url_for('admin.manage_households'))
        
        household_data = {
            'household_id': household[0],
            'address': household[1],
            'income': household[2]
        }
        
        return render_template('admin/edit_household.html', household=household_data)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_households'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/households/view/<int:household_id>')
@admin_required
def view_household(household_id):
    conn, cur = get_db_cursor()
    try:
        # Get household information
        cur.execute("SELECT household_id, address, income FROM households WHERE household_id = %s", (household_id,))
        household_data = cur.fetchone()
        
        if not household_data:
            flash('Household not found', 'danger')
            return redirect(url_for('admin.manage_households'))
        
        household = {
            'household_id': household_data[0],
            'address': household_data[1],
            'income': household_data[2]
        }
        
        # Get members of this household
        cur.execute("""
            SELECT c.citizen_id, c.name, c.gender, c.dob, c.educational_qualification, u.username
            FROM citizens c
            LEFT JOIN users u ON c.user_id = u.user_id
            WHERE c.household_id = %s
            ORDER BY c.name
        """, (household_id,))

        now = datetime.now().date()
        
        members = []
        for member in cur.fetchall():
            members.append({
                'citizen_id': member[0],
                'name': member[1],
                'gender': member[2],
                'dob': member[3],
                'education': member[4],
                'username': member[5]
            })
        
        return render_template('admin/view_household.html', household=household, members=members, now=now )
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_households'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/households/delete/<int:household_id>', methods=['POST'])
@admin_required
def delete_household(household_id):
    conn, cur = get_db_cursor()
    try:
        # Start a transaction
        conn.autocommit = False
        
        # Check if there are citizens in this household
        cur.execute("SELECT COUNT(*) FROM citizens WHERE household_id = %s", (household_id,))
        count = cur.fetchone()[0]
        
        if count > 0:
            flash(f'Cannot delete household because it contains {count} citizens. Please reassign or delete these citizens first.', 'danger')
            conn.rollback()
            return redirect(url_for('admin.manage_households'))
        
        # Delete the household
        cur.execute("DELETE FROM households WHERE household_id = %s", (household_id,))
        
        # Commit the transaction
        conn.commit()
        
        flash('Household deleted successfully', 'success')
    except Exception as e:
        # Rollback in case of error
        conn.rollback()
        flash(f'An error occurred: {str(e)}', 'danger')
    finally:
        # Restore autocommit mode
        conn.autocommit = True
        close_db_connection(conn, cur)
    
    return redirect(url_for('admin.manage_households'))

# ===== Welfare Schemes Management =====
@admin_bp.route('/welfare_schemes')
@admin_required
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
        
        return render_template('admin/manage_welfare_schemes.html', welfare_schemes=welfare_schemes)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/welfare_schemes/add', methods=['GET', 'POST'])
@admin_required
def add_welfare_scheme():
    if request.method == 'POST':
        # Extract form data
        name = request.form['name']
        description = request.form['description']
        
        # Validate required fields
        if not name:
            flash('Scheme name is required.', 'danger')
            return redirect(url_for('admin.add_welfare_scheme'))
        
        conn, cur = get_db_cursor()
        try:
            # Check if scheme with same name already exists
            cur.execute("SELECT scheme_id FROM welfare_schemes WHERE name = %s", (name,))
            if cur.fetchone():
                flash('A welfare scheme with this name already exists.', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('admin.add_welfare_scheme'))
            
            # Insert new welfare scheme
            cur.execute(
                "INSERT INTO welfare_schemes (name, description) VALUES (%s, %s) RETURNING scheme_id",
                (name, description)
            )
            scheme_id = cur.fetchone()[0]
            
            flash(f'Welfare scheme "{name}" added successfully.', 'success')
            return redirect(url_for('admin.manage_welfare_schemes'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.add_welfare_scheme'))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form
    return render_template('admin/add_welfare_scheme.html')

@admin_bp.route('/welfare_schemes/edit/<int:scheme_id>', methods=['GET', 'POST'])
@admin_required
def edit_welfare_scheme(scheme_id):
    if request.method == 'POST':
        # Extract form data
        name = request.form['name']
        description = request.form['description']
        
        # Validate required fields
        if not name:
            flash('Scheme name is required.', 'danger')
            return redirect(url_for('admin.edit_welfare_scheme', scheme_id=scheme_id))
        
        conn, cur = get_db_cursor()
        try:
            # Check if another scheme with same name already exists
            cur.execute("SELECT scheme_id FROM welfare_schemes WHERE name = %s AND scheme_id != %s", (name, scheme_id))
            if cur.fetchone():
                flash('Another welfare scheme with this name already exists.', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('admin.edit_welfare_scheme', scheme_id=scheme_id))
            
            # Update welfare scheme
            cur.execute(
                "UPDATE welfare_schemes SET name = %s, description = %s WHERE scheme_id = %s",
                (name, description, scheme_id)
            )
            
            flash(f'Welfare scheme updated successfully.', 'success')
            return redirect(url_for('admin.manage_welfare_schemes'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.edit_welfare_scheme', scheme_id=scheme_id))
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
            return redirect(url_for('admin.manage_welfare_schemes'))
        
        welfare_scheme = {
            'scheme_id': scheme[0],
            'name': scheme[1],
            'description': scheme[2]
        }
        
        return render_template('admin/edit_welfare_scheme.html', welfare_scheme=welfare_scheme)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_welfare_schemes'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/welfare_schemes/delete/<int:scheme_id>', methods=['POST'])
@admin_required
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
            return redirect(url_for('admin.manage_welfare_schemes'))
        
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
    
    return redirect(url_for('admin.manage_welfare_schemes'))

@admin_bp.route('/welfare_schemes/view/<int:scheme_id>')
@admin_required
def view_welfare_scheme(scheme_id):
    conn, cur = get_db_cursor()
    try:
        # Get welfare scheme information
        cur.execute("SELECT scheme_id, name, description FROM welfare_schemes WHERE scheme_id = %s", (scheme_id,))
        scheme_data = cur.fetchone()
        
        if not scheme_data:
            flash('Welfare scheme not found.', 'danger')
            return redirect(url_for('admin.manage_welfare_schemes'))
        
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
        
        return render_template('admin/view_welfare_scheme.html', welfare_scheme=welfare_scheme, enrollments=enrollments)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_welfare_schemes'))
    finally:
        close_db_connection(conn, cur)

# Scheme Enrollment Management Routes
@admin_bp.route('/enrollments')
@admin_required
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
        
        return render_template('admin/manage_enrollments.html', enrollments=enrollments)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/enrollments/add', methods=['GET', 'POST'])
@admin_required
def add_enrollment():
    if request.method == 'POST':
        # Extract form data
        citizen_id = request.form['citizen_id']
        scheme_id = request.form['scheme_id']
        enrollment_date = request.form.get('enrollment_date') or None
        
        # Validate required fields
        if not citizen_id or not scheme_id:
            flash('Please select both a citizen and a welfare scheme.', 'danger')
            return redirect(url_for('admin.add_enrollment'))
        
        conn, cur = get_db_cursor()
        try:
            # Check if citizen exists
            cur.execute("SELECT citizen_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
            if not cur.fetchone():
                flash('Citizen not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('admin.add_enrollment'))
            
            # Check if scheme exists
            cur.execute("SELECT scheme_id FROM welfare_schemes WHERE scheme_id = %s", (scheme_id,))
            if not cur.fetchone():
                flash('Welfare scheme not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('admin.add_enrollment'))
            
            # Check if enrollment already exists
            cur.execute("""
                SELECT enrollment_id FROM scheme_enrollments
                WHERE citizen_id = %s AND scheme_id = %s
            """, (citizen_id, scheme_id))
            if cur.fetchone():
                flash('This citizen is already enrolled in this scheme.', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('admin.add_enrollment'))
            
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
            return redirect(url_for('admin.manage_enrollments'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.add_enrollment'))
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
        
        return render_template('admin/add_enrollment.html', citizens=citizens, schemes=schemes)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_enrollments'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/enrollments/delete/<int:enrollment_id>', methods=['POST'])
@admin_required
def delete_enrollment(enrollment_id):
    conn, cur = get_db_cursor()
    try:
        # Check if enrollment exists
        cur.execute("SELECT enrollment_id FROM scheme_enrollments WHERE enrollment_id = %s", (enrollment_id,))
        if not cur.fetchone():
            flash('Enrollment not found.', 'danger')
            return redirect(url_for('admin.manage_enrollments'))
        
        # Delete the enrollment
        cur.execute("DELETE FROM scheme_enrollments WHERE enrollment_id = %s", (enrollment_id,))
        
        flash('Enrollment deleted successfully.', 'success')
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
    finally:
        close_db_connection(conn, cur)
    
    return redirect(url_for('admin.manage_enrollments'))

@admin_bp.route('/enrollments/citizen/<int:citizen_id>')
@admin_required
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
            return redirect(url_for('admin.manage_enrollments'))
        
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
        
        return render_template('admin/citizen_enrollments.html', citizen=citizen, enrollments=enrollments)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_enrollments'))
    finally:
        close_db_connection(conn, cur)        

# ===== Land Records Management =====
@admin_bp.route('/land_records')
@admin_required
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
        
        return render_template('admin/manage_land_records.html', land_records=land_records)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/land_records/add', methods=['GET', 'POST'])
@admin_required
def add_land_record():
    if request.method == 'POST':
        # Extract form data
        citizen_id = request.form['citizen_id']
        area_acres = request.form['area_acres']
        crop_type = request.form['crop_type']
        
        # Validate required fields
        if not citizen_id or not area_acres:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('admin.add_land_record'))
        
        conn, cur = get_db_cursor()
        try:
            # Verify citizen exists
            cur.execute("SELECT citizen_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
            if not cur.fetchone():
                flash('Citizen ID not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('admin.add_land_record'))
            
            # Insert new land record
            cur.execute(
                "INSERT INTO land_records (citizen_id, area_acres, crop_type) VALUES (%s, %s, %s) RETURNING land_id",
                (citizen_id, area_acres, crop_type)
            )
            land_id = cur.fetchone()[0]
            
            flash(f'Land record added successfully with ID: {land_id}', 'success')
            return redirect(url_for('admin.manage_land_records'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.add_land_record'))
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
        
        return render_template('admin/add_land_record.html', citizens=citizens, common_crops=common_crops)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_land_records'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/land_records/edit/<int:land_id>', methods=['GET', 'POST'])
@admin_required
def edit_land_record(land_id):
    if request.method == 'POST':
        # Extract form data
        citizen_id = request.form['citizen_id']
        area_acres = request.form['area_acres']
        crop_type = request.form['crop_type']
        
        # Validate required fields
        if not citizen_id or not area_acres:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('admin.edit_land_record', land_id=land_id))
        
        conn, cur = get_db_cursor()
        try:
            # Verify citizen exists
            cur.execute("SELECT citizen_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
            if not cur.fetchone():
                flash('Citizen ID not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('admin.edit_land_record', land_id=land_id))
            
            # Update land record
            cur.execute(
                "UPDATE land_records SET citizen_id = %s, area_acres = %s, crop_type = %s WHERE land_id = %s",
                (citizen_id, area_acres, crop_type, land_id)
            )
            
            flash('Land record updated successfully.', 'success')
            return redirect(url_for('admin.manage_land_records'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.edit_land_record', land_id=land_id))
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
            return redirect(url_for('admin.manage_land_records'))
        
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
        
        return render_template('admin/edit_land_record.html', land_record=land_record, citizens=citizens, common_crops=common_crops)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_land_records'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/land_records/delete/<int:land_id>', methods=['POST'])
@admin_required
def delete_land_record(land_id):
    conn, cur = get_db_cursor()
    try:
        # Check if land record exists
        cur.execute("SELECT land_id FROM land_records WHERE land_id = %s", (land_id,))
        if not cur.fetchone():
            flash('Land record not found.', 'danger')
            return redirect(url_for('admin.manage_land_records'))
        
        # Delete the land record
        cur.execute("DELETE FROM land_records WHERE land_id = %s", (land_id,))
        
        flash('Land record deleted successfully.', 'success')
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
    finally:
        close_db_connection(conn, cur)
    
    return redirect(url_for('admin.manage_land_records'))

@admin_bp.route('/land_records/view/<int:land_id>')
@admin_required
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
            return redirect(url_for('admin.manage_land_records'))
        
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
        
        return render_template('admin/view_land_record.html', land_record=land_record)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_land_records'))
    finally:
        close_db_connection(conn, cur)

# ===== Vaccination Records Management =====
@admin_bp.route('/vaccinations')
@admin_required
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
        
        return render_template('admin/manage_vaccinations.html', vaccination_records=vaccination_records)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/vaccinations/add', methods=['GET', 'POST'])
@admin_required
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
            return redirect(url_for('admin.add_vaccination'))
        
        conn, cur = get_db_cursor()
        try:
            # Check if citizen exists
            cur.execute("SELECT citizen_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
            if not cur.fetchone():
                flash('Citizen not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('admin.add_vaccination'))
            
            # Check if this vaccination already exists for this citizen
            cur.execute("""
                SELECT vaccination_id FROM vaccinations 
                WHERE citizen_id = %s AND vaccine_type = %s AND date_administered = %s
            """, (citizen_id, vaccine_type, date_administered))
            
            if cur.fetchone():
                flash('This vaccination record already exists for this citizen.', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('admin.add_vaccination'))
            
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
            return redirect(url_for('admin.manage_vaccinations'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.add_vaccination'))
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
        
        return render_template('admin/add_vaccination.html', 
                              citizens=citizens, 
                              vaccine_types=vaccine_types)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_vaccinations'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/vaccinations/edit/<int:vaccination_id>', methods=['GET', 'POST'])
@admin_required
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
            return redirect(url_for('admin.edit_vaccination', vaccination_id=vaccination_id))
        
        conn, cur = get_db_cursor()
        try:
            # Check if citizen exists
            cur.execute("SELECT citizen_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
            if not cur.fetchone():
                flash('Citizen not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('admin.edit_vaccination', vaccination_id=vaccination_id))
            
            # Check if this vaccination already exists for this citizen (excluding current record)
            cur.execute("""
                SELECT vaccination_id FROM vaccinations 
                WHERE citizen_id = %s AND vaccine_type = %s AND date_administered = %s AND vaccination_id != %s
            """, (citizen_id, vaccine_type, date_administered, vaccination_id))
            
            if cur.fetchone():
                flash('This vaccination record already exists for this citizen.', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('admin.edit_vaccination', vaccination_id=vaccination_id))
            
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
            return redirect(url_for('admin.manage_vaccinations'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.edit_vaccination', vaccination_id=vaccination_id))
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
            return redirect(url_for('admin.manage_vaccinations'))
        
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
        
        return render_template('admin/edit_vaccination.html', 
                              vaccination=vaccination,
                              citizens=citizens, 
                              vaccine_types=vaccine_types)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_vaccinations'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/vaccinations/delete/<int:vaccination_id>', methods=['POST'])
@admin_required
def delete_vaccination(vaccination_id):
    conn, cur = get_db_cursor()
    try:
        # Check if vaccination record exists
        cur.execute("SELECT vaccination_id FROM vaccinations WHERE vaccination_id = %s", (vaccination_id,))
        if not cur.fetchone():
            flash('Vaccination record not found.', 'danger')
            return redirect(url_for('admin.manage_vaccinations'))
        
        # Delete the vaccination record
        cur.execute("DELETE FROM vaccinations WHERE vaccination_id = %s", (vaccination_id,))
        
        flash('Vaccination record deleted successfully.', 'success')
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
    finally:
        close_db_connection(conn, cur)
    
    return redirect(url_for('admin.manage_vaccinations'))

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

@admin_bp.route('/vaccinations/citizen/<int:citizen_id>')
@admin_required
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
            return redirect(url_for('admin.manage_vaccinations'))
        
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
        
        return render_template('admin/citizen_vaccinations.html', 
                             citizen=citizen, 
                             vaccination_records=vaccination_records,
                             recommended_vaccines=recommended_vaccines)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_vaccinations'))
    finally:
        close_db_connection(conn, cur)

# ===== Census Data Management =====
@admin_bp.route('/census')
@admin_required
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
        
        return render_template('admin/manage_census.html', census_data=census_data)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/census/add', methods=['GET', 'POST'])
@admin_required
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
            return redirect(url_for('admin.add_census_record'))
        
        conn, cur = get_db_cursor()
        try:
            # Check if citizen exists
            cur.execute("SELECT citizen_id, household_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
            citizen_data = cur.fetchone()
            
            if not citizen_data:
                flash('Citizen not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('admin.add_census_record'))
            
            # If household_id not provided, use the citizen's household
            if not household_id:
                household_id = citizen_data[1]
            
            # Verify household exists
            cur.execute("SELECT household_id FROM households WHERE household_id = %s", (household_id,))
            if not cur.fetchone():
                flash('Household not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('admin.add_census_record'))
            
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
            return redirect(url_for('admin.manage_census'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.add_census_record'))
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
        
        return render_template('admin/add_census_record.html', 
                              citizens=citizens, 
                              households=households, 
                              event_types=event_types)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_census'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/census/edit/<int:census_id>', methods=['GET', 'POST'])
@admin_required
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
            return redirect(url_for('admin.edit_census_record', census_id=census_id))
        
        conn, cur = get_db_cursor()
        try:
            # Check if citizen exists
            cur.execute("SELECT citizen_id, household_id FROM citizens WHERE citizen_id = %s", (citizen_id,))
            citizen_data = cur.fetchone()
            
            if not citizen_data:
                flash('Citizen not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('admin.edit_census_record', census_id=census_id))
            
            # If household_id not provided, use the citizen's household
            if not household_id:
                household_id = citizen_data[1]
            
            # Verify household exists
            cur.execute("SELECT household_id FROM households WHERE household_id = %s", (household_id,))
            if not cur.fetchone():
                flash('Household not found', 'danger')
                close_db_connection(conn, cur)
                return redirect(url_for('admin.edit_census_record', census_id=census_id))
            
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
            return redirect(url_for('admin.manage_census'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.edit_census_record', census_id=census_id))
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
            return redirect(url_for('admin.manage_census'))
        
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
        
        return render_template('admin/edit_census_record.html', 
                              census_record=census_record,
                              citizens=citizens, 
                              households=households, 
                              event_types=event_types)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_census'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/census/delete/<int:census_id>', methods=['POST'])
@admin_required
def delete_census_record(census_id):
    conn, cur = get_db_cursor()
    try:
        # Check if census record exists
        cur.execute("SELECT census_id FROM census_data WHERE census_id = %s", (census_id,))
        if not cur.fetchone():
            flash('Census record not found.', 'danger')
            return redirect(url_for('admin.manage_census'))
        
        # Delete the census record
        cur.execute("DELETE FROM census_data WHERE census_id = %s", (census_id,))
        
        flash('Census record deleted successfully.', 'success')
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
    finally:
        close_db_connection(conn, cur)
    
    return redirect(url_for('admin.manage_census'))

@admin_bp.route('/census/citizen/<int:citizen_id>')
@admin_required
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
            return redirect(url_for('admin.manage_census'))
        
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
        
        return render_template('admin/citizen_census.html', citizen=citizen, census_records=census_records)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_census'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/census/household/<int:household_id>')
@admin_required
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
            return redirect(url_for('admin.manage_census'))
        
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
        
        return render_template('admin/household_census.html', 
                              household=household, 
                              members=members,
                              census_records=census_records)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_census'))
    finally:
        close_db_connection(conn, cur)

# ===== Assets Management =====
@admin_bp.route('/assets')
@admin_required
def manage_assets():
    conn, cur = get_db_cursor()
    try:
        # Fetch all assets
        cur.execute("""
            SELECT asset_id, type, location, installation_date
            FROM assets
            ORDER BY asset_id
        """)
        records = cur.fetchall()
        
        # Format the data for template
        assets = []
        for record in records:
            assets.append({
                'asset_id': record[0],
                'type': record[1],
                'location': record[2],
                'installation_date': record[3]
            })
        
        return render_template('admin/manage_assets.html', assets=assets)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/assets/add', methods=['GET', 'POST'])
@admin_required
def add_asset():
    if request.method == 'POST':
        # Extract form data
        asset_type = request.form['type']
        location = request.form['location']
        installation_date = request.form.get('installation_date') or None
        
        # Validate required fields
        if not asset_type or not location:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('admin.add_asset'))
        
        conn, cur = get_db_cursor()
        try:
            # Insert new asset
            if installation_date:
                cur.execute(
                    "INSERT INTO assets (type, location, installation_date) VALUES (%s, %s, %s) RETURNING asset_id",
                    (asset_type, location, installation_date)
                )
            else:
                cur.execute(
                    "INSERT INTO assets (type, location) VALUES (%s, %s) RETURNING asset_id",
                    (asset_type, location)
                )
            asset_id = cur.fetchone()[0]
            
            flash(f'Asset added successfully with ID: {asset_id}', 'success')
            return redirect(url_for('admin.manage_assets'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.add_asset'))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form
    # Define common asset types
    asset_types = [
        "Road", "Bridge", "Building", "Water Tank", "Street Light", "Drainage", 
        "Public Toilet", "Playground", "Community Center", "School", "Health Center", "Other"
    ]
    
    return render_template('admin/add_asset.html', asset_types=asset_types)

@admin_bp.route('/assets/edit/<int:asset_id>', methods=['GET', 'POST'])
@admin_required
def edit_asset(asset_id):
    if request.method == 'POST':
        # Extract form data
        asset_type = request.form['type']
        location = request.form['location']
        installation_date = request.form.get('installation_date') or None
        
        # Validate required fields
        if not asset_type or not location:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('admin.edit_asset', asset_id=asset_id))
        
        conn, cur = get_db_cursor()
        try:
            # Update asset
            if installation_date:
                cur.execute(
                    "UPDATE assets SET type = %s, location = %s, installation_date = %s WHERE asset_id = %s",
                    (asset_type, location, installation_date, asset_id)
                )
            else:
                cur.execute(
                    "UPDATE assets SET type = %s, location = %s WHERE asset_id = %s",
                    (asset_type, location, asset_id)
                )
            
            flash('Asset updated successfully.', 'success')
            return redirect(url_for('admin.manage_assets'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.edit_asset', asset_id=asset_id))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form with asset data
    conn, cur = get_db_cursor()
    try:
        # Get asset information
        cur.execute("SELECT asset_id, type, location, installation_date FROM assets WHERE asset_id = %s", (asset_id,))
        record = cur.fetchone()
        
        if not record:
            flash('Asset not found.', 'danger')
            return redirect(url_for('admin.manage_assets'))
        
        asset = {
            'asset_id': record[0],
            'type': record[1],
            'location': record[2],
            'installation_date': record[3]
        }
        
        # Define common asset types
        asset_types = [
            "Road", "Bridge", "Building", "Water Tank", "Street Light", "Drainage", 
            "Public Toilet", "Playground", "Community Center", "School", "Health Center", "Other"
        ]
        
        return render_template('admin/edit_asset.html', asset=asset, asset_types=asset_types)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_assets'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/assets/delete/<int:asset_id>', methods=['POST'])
@admin_required
def delete_asset(asset_id):
    conn, cur = get_db_cursor()
    try:
        # Check if asset exists
        cur.execute("SELECT asset_id FROM assets WHERE asset_id = %s", (asset_id,))
        if not cur.fetchone():
            flash('Asset not found.', 'danger')
            return redirect(url_for('admin.manage_assets'))
        
        # Delete the asset
        cur.execute("DELETE FROM assets WHERE asset_id = %s", (asset_id,))
        
        flash('Asset deleted successfully.', 'success')
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
    finally:
        close_db_connection(conn, cur)
    
    return redirect(url_for('admin.manage_assets'))

@admin_bp.route('/assets/view/<int:asset_id>')
@admin_required
def view_asset(asset_id):
    conn, cur = get_db_cursor()
    try:
        # Get asset information
        cur.execute("""
            SELECT asset_id, type, location, installation_date
            FROM assets
            WHERE asset_id = %s
        """, (asset_id,))
        record = cur.fetchone()
        
        if not record:
            flash('Asset not found.', 'danger')
            return redirect(url_for('admin.manage_assets'))
        
        asset = {
            'asset_id': record[0],
            'type': record[1],
            'location': record[2],
            'installation_date': record[3]
        }
        
        # Get age of the asset
        if asset['installation_date']:
            from datetime import datetime
            installation_date = datetime.strptime(str(asset['installation_date']), '%Y-%m-%d')
            today = datetime.today()
            age_days = (today - installation_date).days
            
            years = age_days // 365
            remaining_days = age_days % 365
            months = remaining_days // 30
            days = remaining_days % 30
            
            age_str = ""
            if years > 0:
                age_str += f"{years} year{'s' if years != 1 else ''} "
            if months > 0:
                age_str += f"{months} month{'s' if months != 1 else ''} "
            if days > 0:
                age_str += f"{days} day{'s' if days != 1 else ''}"
                
            asset['age'] = age_str.strip()
        else:
            asset['age'] = "Unknown"
        
        return render_template('admin/view_asset.html', asset=asset)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_assets'))
    finally:
        close_db_connection(conn, cur)

# ===== Employees Management =====
@admin_bp.route('/employees')
@admin_required
def manage_employees():
    conn, cur = get_db_cursor()
    try:
        # Fetch all employees with their citizen information
        cur.execute("""
            SELECT e.employee_id, e.role, e.joining_date, 
                c.citizen_id, c.name, 
                COALESCE(h.address, 'Address not available') as address, 
                u.username
            FROM panchayat_employees e
            LEFT JOIN citizens c ON e.citizen_id = c.citizen_id
            LEFT JOIN households h ON c.household_id = h.household_id
            LEFT JOIN users u ON e.user_id = u.user_id
            ORDER BY e.employee_id
        """)
        records = cur.fetchall()
        
        # Format the data for template
        employees = []
        for record in records:
            employees.append({
                'employee_id': record[0],
                'role': record[1],
                'joining_date': record[2],
                'citizen_id': record[3],
                'name': record[4] if record[4] else 'Name not available',
                'address': record[5] if record[5] else 'Address not available',
                'username': record[6] if record[6] else 'No account'
            })

        print(employees)    
        
        return render_template('admin/manage_employees.html', employees=employees)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.admin_dashboard'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/employees/add', methods=['GET', 'POST'])
@admin_required
def add_employee():
    if request.method == 'POST':
        citizen_id = request.form['citizen_id']
        role = request.form['role']
        joining_date = request.form.get('joining_date') or None
        create_account = 'create_account' in request.form
        
        # Validate input
        if not citizen_id or not role:
            flash('Please fill in all required fields', 'danger')
            return redirect(url_for('admin.add_employee'))
        
        conn, cur = get_db_cursor()
        try:
            # Check if citizen exists
            cur.execute("""
                SELECT citizen_id, name, user_id
                FROM citizens
                WHERE citizen_id = %s
            """, (citizen_id,))
            citizen_data = cur.fetchone()
            
            if not citizen_data:
                flash('Citizen not found', 'danger')
                return redirect(url_for('admin.add_employee'))
            
            # Check if citizen is already an employee
            cur.execute("SELECT employee_id FROM panchayat_employees WHERE citizen_id = %s", (citizen_id,))
            if cur.fetchone():
                flash('This citizen is already registered as an employee', 'danger')
                return redirect(url_for('admin.add_employee'))
            
            # Start a transaction
            conn.autocommit = False
            
            user_id = citizen_data[2]
            
            # If create account is checked and citizen doesn't have a user account
            if create_account and not user_id:
                username = request.form.get('username')
                email = request.form.get('email')
                password = request.form.get('password')
                
                if not username or not email or not password:
                    flash('Please fill in all user account fields', 'danger')
                    conn.rollback()
                    return redirect(url_for('admin.add_employee'))
                
                # Check if username or email already exists
                cur.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, email))
                if cur.fetchone():
                    flash('Username or email already exists', 'danger')
                    conn.rollback()
                    return redirect(url_for('admin.add_employee'))
                
                # Create user with panchayat employee role (role_id=2)
                password_hash = generate_password_hash(password)
                cur.execute(
                    "INSERT INTO users (username, email, password_hash, role_id) VALUES (%s, %s, %s, 2) RETURNING user_id",
                    (username, email, password_hash)
                )
                user_id = cur.fetchone()[0]
                
                # Update citizen record with user_id
                cur.execute(
                    "UPDATE citizens SET user_id = %s WHERE citizen_id = %s",
                    (user_id, citizen_id)
                )
            elif create_account and user_id:
                # If citizen already has a user account, update its role to employee
                cur.execute(
                    "UPDATE users SET role_id = 2 WHERE user_id = %s",
                    (user_id,)
                )
            
            # Insert employee record
            if joining_date:
                cur.execute(
                    "INSERT INTO panchayat_employees (citizen_id, role, user_id, joining_date) VALUES (%s, %s, %s, %s) RETURNING employee_id",
                    (citizen_id, role, user_id, joining_date)
                )
            else:
                cur.execute(
                    "INSERT INTO panchayat_employees (citizen_id, role, user_id) VALUES (%s, %s, %s) RETURNING employee_id",
                    (citizen_id, role, user_id)
                )
            employee_id = cur.fetchone()[0]
            
            # Commit the transaction
            conn.commit()
            
            flash(f'Employee added successfully with ID: {employee_id}', 'success')
            return redirect(url_for('admin.manage_employees'))
        except Exception as e:
            # Rollback in case of error
            conn.rollback()
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.add_employee'))
        finally:
            # Restore autocommit mode
            conn.autocommit = True
            close_db_connection(conn, cur)
    
    # GET request - show form
    conn, cur = get_db_cursor()
    try:
        # Get citizens who are not already employees
        cur.execute("""
            SELECT c.citizen_id, c.name, h.address
            FROM citizens c
            JOIN households h ON c.household_id = h.household_id
            WHERE c.citizen_id NOT IN (SELECT citizen_id FROM panchayat_employees)
            ORDER BY c.name
        """)
        citizens = cur.fetchall()
        
        # Define common employee roles
        employee_roles = [
            "Secretary", "Accountant", "Field Officer", "Clerk", "Health Worker", 
            "Agriculture Extension Officer", "Technician", "Supervisor", "Other"
        ]
        
        return render_template('admin/add_employee.html', citizens=citizens, employee_roles=employee_roles)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_employees'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/employees/edit/<int:employee_id>', methods=['GET', 'POST'])
@admin_required
def edit_employee(employee_id):
    if request.method == 'POST':
        role = request.form['role']
        joining_date = request.form.get('joining_date') or None
        
        # Validate input
        if not role:
            flash('Role is required', 'danger')
            return redirect(url_for('admin.edit_employee', employee_id=employee_id))
        
        conn, cur = get_db_cursor()
        try:
            # Update employee record
            if joining_date:
                cur.execute(
                    "UPDATE panchayat_employees SET role = %s, joining_date = %s WHERE employee_id = %s",
                    (role, joining_date, employee_id)
                )
            else:
                cur.execute(
                    "UPDATE panchayat_employees SET role = %s WHERE employee_id = %s",
                    (role, employee_id)
                )
            
            flash('Employee updated successfully', 'success')
            return redirect(url_for('admin.manage_employees'))
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('admin.edit_employee', employee_id=employee_id))
        finally:
            close_db_connection(conn, cur)
    
    # GET request - show form with employee data
    conn, cur = get_db_cursor()
    try:
        # Get employee information
        cur.execute("""
            SELECT e.employee_id, e.role, e.joining_date, e.citizen_id, 
                   c.name, h.address, e.user_id, u.username, u.email
            FROM panchayat_employees e
            JOIN citizens c ON e.citizen_id = c.citizen_id
            JOIN households h ON c.household_id = h.household_id
            LEFT JOIN users u ON e.user_id = u.user_id
            WHERE e.employee_id = %s
        """, (employee_id,))
        record = cur.fetchone()
        
        if not record:
            flash('Employee not found', 'danger')
            return redirect(url_for('admin.manage_employees'))
        
        employee = {
            'employee_id': record[0],
            'role': record[1],
            'joining_date': record[2],
            'citizen_id': record[3],
            'name': record[4],
            'address': record[5],
            'user_id': record[6],
            'username': record[7],
            'email': record[8]
        }
        
        # Define common employee roles
        employee_roles = [
            "Secretary", "Accountant", "Field Officer", "Clerk", "Health Worker", 
            "Agriculture Extension Officer", "Technician", "Supervisor", "Other"
        ]
        
        return render_template('admin/edit_employee.html', employee=employee, employee_roles=employee_roles)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_employees'))
    finally:
        close_db_connection(conn, cur)

@admin_bp.route('/employees/delete/<int:employee_id>', methods=['POST'])
@admin_required
def delete_employee(employee_id):
    conn, cur = get_db_cursor()
    try:
        # Start a transaction
        conn.autocommit = False
        
        # Get employee information
        cur.execute("""
            SELECT e.employee_id, e.citizen_id, e.user_id, c.name, u.username
            FROM panchayat_employees e
            JOIN citizens c ON e.citizen_id = c.citizen_id
            LEFT JOIN users u ON e.user_id = u.user_id
            WHERE e.employee_id = %s
        """, (employee_id,))
        employee_data = cur.fetchone()
        
        if not employee_data:
            flash('Employee not found', 'danger')
            conn.rollback()
            return redirect(url_for('admin.manage_employees'))
        
        employee_id, citizen_id, user_id, employee_name, username = employee_data
        
        # Check if the user wants to delete the associated user account
        delete_user = 'delete_user' in request.form
        
        # Delete the employee record
        cur.execute("DELETE FROM panchayat_employees WHERE employee_id = %s", (employee_id,))
        
        # If selected, delete the user account
        if delete_user and user_id:
            cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        else:
            # Otherwise, just update the role if there is a user account
            if user_id:
                cur.execute("UPDATE users SET role_id = 3 WHERE user_id = %s", (user_id,))
        
        # Commit the transaction
        conn.commit()
        
        flash(f'Employee {employee_name} deleted successfully', 'success')
    except Exception as e:
        # Rollback in case of error
        conn.rollback()
        flash(f'An error occurred: {str(e)}', 'danger')
    finally:
        # Restore autocommit mode
        conn.autocommit = True
        close_db_connection(conn, cur)
    
    return redirect(url_for('admin.manage_employees'))

@admin_bp.route('/employees/view/<int:employee_id>')
@admin_required
def view_employee(employee_id):
    conn, cur = get_db_cursor()
    try:
        # Get comprehensive employee information
        cur.execute("""
            SELECT e.employee_id, e.role, e.joining_date, 
                   c.citizen_id, c.name, c.gender, c.dob, c.educational_qualification,
                   h.household_id, h.address, e.user_id, u.username, u.email
            FROM panchayat_employees e
            JOIN citizens c ON e.citizen_id = c.citizen_id
            JOIN households h ON c.household_id = h.household_id
            LEFT JOIN users u ON e.user_id = u.user_id
            WHERE e.employee_id = %s
        """, (employee_id,))
        record = cur.fetchone()
        
        if not record:
            flash('Employee not found', 'danger')
            return redirect(url_for('admin.manage_employees'))
        
        employee = {
            'employee_id': record[0],
            'role': record[1],
            'joining_date': record[2],
            'citizen_id': record[3],
            'name': record[4],
            'gender': record[5],
            'dob': record[6],
            'education': record[7],
            'household_id': record[8],
            'address': record[9],
            'user_id': record[10],
            'username': record[11],
            'email': record[12]
        }
        
        return render_template('admin/view_employee.html', employee=employee)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_employees'))
    finally:
        close_db_connection(conn, cur)

# ===== System Overview =====
@admin_bp.route('/system')
@admin_required
def system_overview():
    conn, cur = get_db_cursor()
    try:
        # Get counts for each main table
        tables = [
            ('users', 'Users'),
            ('citizens', 'Citizens'),
            ('households', 'Households'),
            ('panchayat_employees', 'Employees'),
            ('land_records', 'Land Records'),
            ('welfare_schemes', 'Welfare Schemes'),
            ('scheme_enrollments', 'Scheme Enrollments'),
            ('vaccinations', 'Vaccinations'),
            ('census_data', 'Census Records'),
            ('assets', 'Assets')
        ]
        
        counts = {}
        for table_name, display_name in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            counts[table_name] = cur.fetchone()[0]
        
        # Get user counts by role
        cur.execute("""
            SELECT r.role_name, COUNT(u.user_id)
            FROM users u
            JOIN user_roles r ON u.role_id = r.role_id
            GROUP BY r.role_name
            ORDER BY COUNT(u.user_id) DESC
        """)
        user_roles = cur.fetchall()
        
        # Get recent activity
        cur.execute("""
            SELECT 'New user' as event, u.username, u.created_at as event_date
            FROM users u
            ORDER BY u.created_at DESC
            LIMIT 5
        """)
        recent_users = cur.fetchall()
        
        cur.execute("""
            SELECT 'New enrollment' as event, c.name as subject, se.enrollment_date as event_date
            FROM scheme_enrollments se
            JOIN citizens c ON se.citizen_id = c.citizen_id
            ORDER BY se.enrollment_date DESC
            LIMIT 5
        """)
        recent_enrollments = cur.fetchall()
        
        cur.execute("""
            SELECT 'Census update' as event, c.name as subject, cd.event_date
            FROM census_data cd
            JOIN citizens c ON cd.citizen_id = c.citizen_id
            ORDER BY cd.event_date DESC
            LIMIT 5
        """)
        recent_census = cur.fetchall()

        # When creating the recent_activity list, convert dates to datetime objects
        recent_activity = []
        for event in recent_users:
            recent_activity.append({
                'type': event[0],
                'subject': event[1],
                'date': event[2]  # This is likely already a datetime
            })

        for event in recent_enrollments:
            # If this is a date object, convert to datetime
            if hasattr(event[2], 'hour'):  # It's already a datetime
                event_date = event[2]
            else:  # It's a date, convert to datetime
                event_date = datetime.combine(event[2], datetime.min.time())
            
            recent_activity.append({
                'type': event[0],
                'subject': event[1],
                'date': event_date
            })

        # Do the same for census events
        for event in recent_census:
            if hasattr(event[2], 'hour'):
                event_date = event[2]
            else:
                event_date = datetime.combine(event[2], datetime.min.time())
            
            recent_activity.append({
                'type': event[0],
                'subject': event[1],
                'date': event_date
            })

        # Now all dates are datetime objects, so sorting will work
        recent_activity.sort(key=lambda x: x['date'] if x['date'] else datetime.min, reverse=True)
        
        # Limit to top 10
        recent_activity = recent_activity[:10]
        
        return render_template(
            'admin/system_overview.html',
            counts=counts,
            user_roles=[{'role': role[0], 'count': role[1]} for role in user_roles],
            recent_activity=recent_activity
        )
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('admin.admin_dashboard'))
    finally:
        close_db_connection(conn, cur)