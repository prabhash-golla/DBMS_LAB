-- Table Creation Part :

-- Table: households
CREATE TABLE households (
    household_id SERIAL PRIMARY KEY,
    address TEXT NOT NULL,
    income DECIMAL(15, 2) NOT NULL CHECK (income >= 0)
);

-- Table: citizens
CREATE TABLE citizens (
    citizen_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    gender TEXT CHECK (gender IN ('Male', 'Female', 'Other')),
    dob DATE NOT NULL,
    household_id INT REFERENCES households(household_id) ON DELETE CASCADE,
    education_status TEXT CHECK (education_status IN ('Yes','No')),
    educational_qualification TEXT,
    occupation TEXT,
    father_id INT REFERENCES citizens(citizen_id) ON DELETE SET NULL,
    mother_id INT REFERENCES citizens(citizen_id) ON DELETE SET NULL,
    spouse_id INT REFERENCES citizens(citizen_id) ON DELETE SET NULL
);


-- Table: land_records
CREATE TABLE land_records (
    land_id SERIAL PRIMARY KEY,
    citizen_id INT REFERENCES citizens(citizen_id) ON DELETE CASCADE,
    area_acres DECIMAL(10, 2) NOT NULL CHECK (area_acres > 0),
    crop_type TEXT
);

-- Table: panchayat_employees
CREATE TABLE panchayat_employees (
    employee_id SERIAL PRIMARY KEY,
    citizen_id INT REFERENCES citizens(citizen_id) ON DELETE CASCADE,
    role TEXT NOT NULL
);

-- Table: assets
CREATE TABLE assets (
    asset_id SERIAL PRIMARY KEY,
    type TEXT NOT NULL,
    location TEXT NOT NULL,
    installation_date DATE NOT NULL
);

-- Table: welfare_schemes
CREATE TABLE welfare_schemes (
    scheme_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);

-- Table: scheme_enrollments
CREATE TABLE scheme_enrollments (
    enrollment_id SERIAL PRIMARY KEY,
    citizen_id INT REFERENCES citizens(citizen_id) ON DELETE CASCADE,
    scheme_id INT REFERENCES welfare_schemes(scheme_id) ON DELETE CASCADE,
    enrollment_date DATE NOT NULL
);

-- Table: vaccinations
CREATE TABLE vaccinations (
    vaccination_id SERIAL PRIMARY KEY,
    citizen_id INT REFERENCES citizens(citizen_id) ON DELETE CASCADE,
    vaccine_type TEXT NOT NULL,
    date_administered DATE NOT NULL
);

-- Table: census_data
CREATE TABLE census_data (
    household_id INT REFERENCES households(household_id) ON DELETE CASCADE,
    citizen_id INT REFERENCES citizens(citizen_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('Birth', 'Death', 'Marriage', 'Divorce')),
    event_date DATE NOT NULL,
    PRIMARY KEY (household_id, citizen_id, event_type, event_date)
);

-- Insertion Part :

-- Household
insert into households (household_id, address, income) values (1, 'Eluru,AP,534007',99000);
insert into households (household_id, address, income) values (2, 'Vizag,AP,535001', 11000);
insert into households (household_id, address, income) values (3, 'Viajaywada,AP,534000', 20000);
insert into households (household_id, address, income) values (4, 'Vizianagaram,AP,535007', 120000);
insert into households (household_id, address, income) values (5, 'Nellore,AP,524344',200000.12);

-- Citizens
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (1, 'G Sridhar', 'Male', '07/07/1980', 1, 'MBA',NULL,NULL,NULL,'No');
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (2, 'G Adhi Lakshmi', 'Female', '07/04/1990', 1, '10th',NULL,NULL,1,'No');
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (3, 'G M M Prabahsh', 'Male', '03/12/2004', 1, '12th',1,2,NULL,'Yes');
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (16, 'G Meenakshi', 'Female', '03/12/2010', 1, '8th',1,2,NULL,'Yes');

insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (4, 'G Venu', 'Male', '01/01/1976', 4, 'M Tech',NULL,NULL,NULL,'No');
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (5, 'G Sirisha', 'Female', '09/30/1986', 4, '12th',NULL,NULL,4,'No');
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (6, 'G Shasank', 'Male', '03/05/2005', 4, '12th',4,5,NULL,'Yes');
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (7, 'G Abhiram', 'Male', '02/06/2008', 4, '10th',4,5,NULL,'Yes');

insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (8, 'S Satti Babu', 'Male', '07/07/1977', 5, 'PG',NULL,NULL,NULL,'No');
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (9, 'S Usha Rani', 'Female', '10/21/1979', 5, 'MA',NULL,NULL,8,'No');
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (10, 'S Navaneeth', 'Male', '07/07/2005', 5, '12th',8,9,NULL,'Yes');
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (11, 'S Sharmila', 'Female', '04/04/2007', 5, '12th',8,9,NULL,'Yes');

insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (12, 'S Subba Rami Reddy', 'Male', '06/06/1976', 3, 'BSc',NULL,NULL,NULL,'No');
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (13, 'S Vishnu Priya', 'Female', '10/10/1980', 3, 'BSc',NULL,NULL,12,'No');
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (14, 'S Suchith Reddy', 'Male', '03/03/2005', 3, '12th',12,13,NULL,'Yes');
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (15, 'S Sumith Reddy', 'Male', '04/04/2008', 3, '10th',12,13,NULL,'Yes');

insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (17, 'Ch RamalingeswaraRao', 'Male', '05/06/1974', 2, 'BTech',NULL,NULL,NULL,'No');
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (18, 'Ch Ramalakshmi', 'Female', '12/13/1977', 2, 'BSc',NULL,NULL,17,'No');
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (19, 'Ch Devi Lakshman', 'Male', '04/04/2024', 2, NULL ,17,18,NULL,'No');
insert into citizens (citizen_id, name, gender, dob, household_id, educational_qualification,father_id,mother_id,spouse_id,education_status) values (20, 'Ch Pooja', 'Female', '04/04/2024', 2, NULL,17,18,NULL,'No');


UPDATE citizens SET spouse_id = 2 WHERE citizen_id = 1 ;
UPDATE citizens SET spouse_id = 5 WHERE citizen_id = 4 ;
UPDATE citizens SET spouse_id = 9 WHERE citizen_id = 8 ;
UPDATE citizens SET spouse_id = 13 WHERE citizen_id = 12 ;
UPDATE citizens SET spouse_id = 18 WHERE citizen_id = 17 ;

-- land_records
insert into land_records (land_id, citizen_id, area_acres, crop_type) values (1, 1, 0.7, 'rice');
insert into land_records (land_id, citizen_id, area_acres, crop_type) values (2, 1, 0.5, 'cotton');
insert into land_records (land_id, citizen_id, area_acres, crop_type) values (3, 1, 0.8, 'wheat');
insert into land_records (land_id, citizen_id, area_acres, crop_type) values (4, 4, 1.1, 'rice');
insert into land_records (land_id, citizen_id, area_acres, crop_type) values (5, 4, 0.2, 'wheat');
insert into land_records (land_id, citizen_id, area_acres, crop_type) values (6, 8, 1.5, 'rice');
insert into land_records (land_id, citizen_id, area_acres, crop_type) values (7, 8, 0.8, 'wheat');
insert into land_records (land_id, citizen_id, area_acres, crop_type) values (9, 12, 0.9, 'wheat');

-- pancahayat Employees
insert into panchayat_employees (employee_id, citizen_id, role) values (1, 1, 'Panchayat Pradhan');
insert into panchayat_employees (employee_id, citizen_id, role) values (2, 4, 'Supervisor');
insert into panchayat_employees (employee_id, citizen_id, role) values (3, 8, 'Manager');
insert into panchayat_employees (employee_id, citizen_id, role) values (4, 13,'Manager');


-- Asserts
insert into assets (asset_id, type, location, installation_date) values (1, 'Electronics', 'Eluru', '12/11/2017');
insert into assets (asset_id, type, location, installation_date) values (2, 'Street Light', 'Phulera', '12/9/2024');
insert into assets (asset_id, type, location, installation_date) values (3, 'Street Light', 'Phulera', '3/5/2023');
insert into assets (asset_id, type, location, installation_date) values (4, 'Street Light', 'Eluru', '4/2/2024');

-- Welfare Schemes
insert into welfare_schemes (scheme_id, name, description) values (1, 'Amma Vadi', 'Sed sagittis. Nam congue, risus semper porta volutpat, quam pede lobortis ligula, sit amet eleifend pede libero quis orci. Nullam molestie nibh in lectus.Pellentesque at nulla. Suspendisse potenti. Cras in purus eu magna vulputate luctus.Cum sociis natoque penatibus et magnis dis parturient montes, nascetur ridiculus mus. Vivamus vestibulum sagittis sapien. Cum sociis natoque penatibus et magnis dis parturient montes, nascetur ridiculus mus.');
insert into welfare_schemes (scheme_id, name, description) values (2, 'Anna Canteen', 'Nulla ut erat id mauris vulputate elementum. Nullam varius. Nulla facilisi.Cras non velit nec nisi vulputate nonummy. Maecenas tincidunt lacus at velit. Vivamus vel nulla eget eros elementum pellentesque.Quisque porta volutpat erat. Quisque erat eros, viverra eget, congue eget, semper rutrum, nulla. Nunc purus.');
insert into welfare_schemes (scheme_id, name, description) values (3, 'Arogya Sree', 'Duis bibendum, felis sed interdum venenatis, turpis enim blandit mi, in porttitor pede justo eu massa. Donec dapibus. Duis at velit eu est congue elementum.');
insert into welfare_schemes (scheme_id, name, description) values (4, 'Mid Day Meal', 'Proin eu mi. Nulla ac enim. In tempor, turpis nec euismod scelerisque, quam turpis adipiscing lorem, vitae mattis nibh ligula nec sem.Duis aliquam convallis nunc. Proin at turpis a pede posuere nonummy. Integer non velit.Donec diam neque, vestibulum eget, vulputate ut, ultrices vel, augue. Vestibulum ante ipsum primis in faucibus orci luctus et ultrices posuere cubilia Curae; Donec pharetra, magna vestibulum aliquet ultrices, erat tortor sollicitudin mi, sit amet lobortis sapien sapien non mi. Integer ac neque.');

-- Scheme Enrolements
insert into scheme_enrollments (enrollment_id, citizen_id, scheme_id, enrollment_date) values (1, 3, 1,'1/12/2020');
insert into scheme_enrollments (enrollment_id, citizen_id, scheme_id, enrollment_date) values (2, 7, 1, '3/16/2024');
insert into scheme_enrollments (enrollment_id, citizen_id, scheme_id, enrollment_date) values (3, 4, 2, '10/16/2024');
insert into scheme_enrollments (enrollment_id, citizen_id, scheme_id, enrollment_date) values (4, 1, 3, '12/18/2022');
insert into scheme_enrollments (enrollment_id, citizen_id, scheme_id, enrollment_date) values (5, 15, 4, '12/11/2022');

-- Vaccinations
insert into vaccinations (vaccination_id, citizen_id, vaccine_type, date_administered) values (1, 16, 'Polio', '6/5/2024');
insert into vaccinations (vaccination_id, citizen_id, vaccine_type, date_administered) values (2, 16, 'Covi Sheild', '7/7/2024');
insert into vaccinations (vaccination_id, citizen_id, vaccine_type, date_administered) values (3, 7, 'Polio', '4/28/2024');
insert into vaccinations (vaccination_id, citizen_id, vaccine_type, date_administered) values (4, 6, 'Polio', '4/20/2022');
insert into vaccinations (vaccination_id, citizen_id, vaccine_type, date_administered) values (5, 3, 'Polio', '4/17/2024');

--Census-Data
insert into census_data (household_id, citizen_id, event_type, event_date) values (1, 1, 'Birth', '01/12/2010');
insert into census_data (household_id, citizen_id, event_type, event_date) values (2, 20, 'Birth', '04/04/2024');
insert into census_data (household_id, citizen_id, event_type, event_date) values (2, 19, 'Birth', '04/04/2024');


-- Queries For Required Quetion :

-- A Question
SELECT a.name
FROM citizens a
JOIN land_records r ON a.citizen_id = r.citizen_id
GROUP BY a.name
HAVING SUM(r.area_acres) > 1
;

-- B Question
SELECT b.name
FROM citizens b
JOIN households h ON b.household_id = h.household_id
WHERE b.gender = 'Female'
AND h.income < 100000
AND b.education_status = 'Yes'
AND DATE_PART('year', AGE(b.dob)) BETWEEN 5 and 18
;


-- C Question
SELECT SUM(area_acres) AS total_land_area_inacres
FROM land_records l
WHERE l.crop_type = 'rice'
;

-- D Question
SELECT COUNT(citizen_id) AS total_citizens
FROM citizens 
WHERE dob > '2000-01-01' 
AND educational_qualification = '10th'
;
  
-- E Question
SELECT e.name
FROM panchayat_employees p
JOIN citizens e ON p.citizen_id = e.citizen_id
JOIN land_records l ON l.citizen_id = e.citizen_id
GROUP BY e.name
HAVING SUM(l.area_acres) > 1
;

-- F Question
SELECT c2.name
FROM citizens c1
JOIN panchayat_employees pe ON c1.citizen_id = pe.citizen_id
JOIN citizens c2 ON c1.household_id = c2.household_id
WHERE pe.role = 'Panchayat Pradhan'
;

-- G Question
SELECT COUNT(*) AS total_street_lights
FROM assets
WHERE type = 'Street Light' 
AND location = 'Phulera' 
AND EXTRACT(YEAR FROM installation_date) = 2024
;
  
-- H Question
SELECT COUNT(v.vaccination_id) AS num_vaccinations
FROM citizens c
JOIN citizens children ON c.citizen_id = children.father_id OR c.citizen_id = children.mother_id
JOIN vaccinations v ON children.citizen_id = v.citizen_id
WHERE c.educational_qualification = '10th'
AND EXTRACT(YEAR FROM v.date_administered) = 2024 
AND DATE_PART('year', AGE(children.dob)) <= 18
;

-- I Question
SELECT COUNT(*) AS total_births
FROM census_data cd
JOIN citizens c ON cd.citizen_id = c.citizen_id
WHERE cd.event_type = 'Birth' 
AND EXTRACT(YEAR FROM cd.event_date) = 2024 
AND c.gender = 'Male'
;

--J Question
SELECT COUNT(DISTINCT c.citizen_id) AS total_citizens
FROM citizens c
WHERE c.household_id IN (
    SELECT DISTINCT h.household_id
    FROM households h
    JOIN panchayat_employees pe ON h.household_id = (SELECT household_id FROM citizens WHERE citizen_id = pe.citizen_id)
)
;

-- Table Deletion Part

-- Drop Tables

DROP TABLE scheme_enrollments;
DROP TABLE welfare_schemes;
DROP TABLE vaccinations;
DROP TABLE panchayat_employees;
DROP TABLE land_records;
DROP TABLE assets;
DROP TABLE census_data;
DROP TABLE citizens;
DROP TABLE households;

