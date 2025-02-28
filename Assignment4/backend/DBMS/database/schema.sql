-- Users and Authentication Tables
CREATE TABLE user_roles (
    role_id SERIAL PRIMARY KEY,
    role_name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role_id INTEGER REFERENCES user_roles(role_id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Gram Panchayat Data Tables
CREATE TABLE households (
    household_id SERIAL PRIMARY KEY,
    address TEXT NOT NULL,
    income DECIMAL(12, 2)
);

CREATE TABLE citizens (
    citizen_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    gender TEXT,
    dob DATE,
    household_id INTEGER REFERENCES households(household_id),
    educational_qualification TEXT,
    user_id INTEGER REFERENCES users(user_id) NULL
);

CREATE TABLE land_records (
    land_id SERIAL PRIMARY KEY,
    citizen_id INTEGER REFERENCES citizens(citizen_id),
    area_acres DECIMAL(10, 2),
    crop_type TEXT
);

CREATE TABLE panchayat_employees (
    employee_id SERIAL PRIMARY KEY,
    citizen_id INTEGER REFERENCES citizens(citizen_id),
    role TEXT,
    joining_date DATE DEFAULT CURRENT_DATE
);

CREATE TABLE assets (
    asset_id SERIAL PRIMARY KEY,
    type TEXT,
    location TEXT,
    installation_date DATE
);

CREATE TABLE welfare_schemes (
    scheme_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE scheme_enrollments (
    enrollment_id SERIAL PRIMARY KEY,
    citizen_id INTEGER REFERENCES citizens(citizen_id),
    scheme_id INTEGER REFERENCES welfare_schemes(scheme_id),
    enrollment_date DATE DEFAULT CURRENT_DATE
);

CREATE TABLE vaccinations (
    vaccination_id SERIAL PRIMARY KEY,
    citizen_id INTEGER REFERENCES citizens(citizen_id),
    vaccine_type TEXT,
    date_administered DATE
);

CREATE TABLE census_data (
    census_id SERIAL PRIMARY KEY,
    household_id INTEGER REFERENCES households(household_id),
    citizen_id INTEGER REFERENCES citizens(citizen_id),
    event_type TEXT,
    event_date DATE
);

-- Insert default user roles
INSERT INTO user_roles (role_name) VALUES 
    ('admin'),
    ('panchayat_employee'),
    ('citizen'),
    ('government_monitor');