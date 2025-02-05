CREATE TABLE Families (
    Family_ID INT PRIMARY KEY,
    Address VARCHAR(255) NOT NULL,
    Total_Income DECIMAL(15, 2) GENERATED ALWAYS AS (
        SELECT SUM(Income) FROM Citizens WHERE Citizens.Family_ID = Families.Family_ID
    ) STORED,
    Total_Number_of_Members INT GENERATED ALWAYS AS (
        SELECT COUNT(*) FROM Citizens WHERE Citizens.Family_ID = Families.Family_ID
    ) STORED
);

CREATE TABLE Citizens (
    Citizen_ID INT PRIMARY KEY,
    Family_ID INT,
    Parent_ID INT,
    Citizen_Name VARCHAR(100) NOT NULL,
    Gender CHAR(1) CHECK (Gender IN ('M', 'F', 'O')),
    Date_of_Birth DATE NOT NULL,
    Marital_Status VARCHAR(20) CHECK (Marital_Status IN ('Single', 'Married', 'Divorced', 'Widowed')),
    Phone_Number VARCHAR(15) UNIQUE,
    Fathers_ID INT,
    Mothers_ID INT,
    Income DECIMAL(15, 2) NOT NULL,
    Spouse_ID INT,
    Educational_Qualification VARCHAR(100),
    FOREIGN KEY (Family_ID) REFERENCES Families(Family_ID) ON DELETE SET NULL,
    FOREIGN KEY (Fathers_ID) REFERENCES Citizens(Citizen_ID),
    FOREIGN KEY (Mothers_ID) REFERENCES Citizens(Citizen_ID),
    FOREIGN KEY (Spouse_ID) REFERENCES Citizens(Citizen_ID)
);

CREATE TABLE Taxation (
    Tax_ID INT PRIMARY KEY,
    Tax_Slab_ID INT NOT NULL,
    Citizen_ID INT NOT NULL,
    Tax_Exemptions DECIMAL(15, 2),
    Taxable_Amount DECIMAL(15, 2) NOT NULL,
    Due_Date DATE NOT NULL,
    FOREIGN KEY (Citizen_ID) REFERENCES Citizens(Citizen_ID) ON DELETE CASCADE
);

CREATE TABLE Tax_Slabs (
    Tax_Slab_ID INT PRIMARY KEY,
    Slab_Range VARCHAR(50) NOT NULL,
    Tax_Rate DECIMAL(5, 2) NOT NULL
);

CREATE TABLE Agriculture_Data (
    Agriculture_Land_ID INT PRIMARY KEY,
    Citizen_ID INT NOT NULL,
    Number_of_Acres DECIMAL(10, 2) NOT NULL,
    Nominee_ID INT,
    Cost_Per_Acre DECIMAL(15, 2) NOT NULL,
    Location VARCHAR(255) NOT NULL,
    Yield_Type VARCHAR(100),
    FOREIGN KEY (Citizen_ID) REFERENCES Citizens(Citizen_ID) ON DELETE CASCADE,
    FOREIGN KEY (Nominee_ID) REFERENCES Citizens(Citizen_ID) ON DELETE SET NULL
);

CREATE TABLE Panchayat_Member (
    Panchayat_Member_ID INT PRIMARY KEY,
    Citizen_ID INT NOT NULL UNIQUE,
    Post VARCHAR(100) NOT NULL,
    Joining_Date DATE NOT NULL,
    Expected_Ending_Date DATE,
    FOREIGN KEY (Citizen_ID) REFERENCES Citizens(Citizen_ID) ON DELETE CASCADE
);

CREATE TABLE Welfare_Schemes (
    Scheme_ID INT PRIMARY KEY,
    Scheme_Name VARCHAR(255) NOT NULL,
    Budget DECIMAL(15, 2) NOT NULL,
    Details TEXT NOT NULL
);

CREATE TABLE Citizen_Schemes (
    Citizen_ID INT NOT NULL,
    Scheme_ID INT NOT NULL,
    Eligibility_Status BOOLEAN NOT NULL,
    PRIMARY KEY (Citizen_ID, Scheme_ID),
    FOREIGN KEY (Citizen_ID) REFERENCES Citizens(Citizen_ID) ON DELETE CASCADE,
    FOREIGN KEY (Scheme_ID) REFERENCES Welfare_Schemes(Scheme_ID) ON DELETE CASCADE
);

CREATE TABLE Expenditure (
    Bill_ID INT PRIMARY KEY,
    Citizen_ID INT NOT NULL,
    Amount DECIMAL(15, 2) NOT NULL,
    Transaction_Mode VARCHAR(50),
    Transaction_Date DATE NOT NULL,
    Item_Name VARCHAR(100),
    Description TEXT,
    Buyer_Name VARCHAR(100),
    FOREIGN KEY (Citizen_ID) REFERENCES Citizens(Citizen_ID) ON DELETE CASCADE
);

CREATE TABLE Income (
    Income_ID INT PRIMARY KEY,
    Citizen_ID INT NOT NULL,
    Income_Type VARCHAR(100) NOT NULL,
    Amount DECIMAL(15, 2) NOT NULL,
    Description TEXT,
    FOREIGN KEY (Citizen_ID) REFERENCES Citizens(Citizen_ID) ON DELETE CASCADE
);

CREATE TABLE Certificates (
    Certificate_ID INT PRIMARY KEY,
    Citizen_ID INT NOT NULL,
    Panchayat_Member_ID INT NOT NULL,
    Certificate_Type VARCHAR(100) NOT NULL,
    Issued_By VARCHAR(100) NOT NULL,
    Validity_Date DATE NOT NULL,
    FOREIGN KEY (Citizen_ID) REFERENCES Citizens(Citizen_ID) ON DELETE CASCADE,
    FOREIGN KEY (Panchayat_Member_ID) REFERENCES Panchayat_Member(Panchayat_Member_ID) ON DELETE CASCADE
);

CREATE TABLE Asset_Management (
    Asset_ID INT PRIMARY KEY,
    Panchayat_Member_ID INT NOT NULL,
    Asset_Type VARCHAR(100) NOT NULL,
    Description TEXT,
    Amount_Spent DECIMAL(15, 2) NOT NULL,
    FOREIGN KEY (Panchayat_Member_ID) REFERENCES Panchayat_Member(Panchayat_Member_ID) ON DELETE CASCADE
);

CREATE TABLE Census_Data (
    Census_ID INT PRIMARY KEY,
    Panchayat_Member_ID INT NOT NULL,
    Year YEAR NOT NULL,
    Population INT NOT NULL,
    Birth_Rate DECIMAL(5, 2),
    Death_Rate DECIMAL(5, 2),
    Gender_Ratio DECIMAL(10, 2),
    Migration_Rate DECIMAL(5, 2),
    FOREIGN KEY (Panchayat_Member_ID) REFERENCES Panchayat_Member(Panchayat_Member_ID) ON DELETE CASCADE
);

CREATE TABLE Environmental_Data (
    Record_ID INT PRIMARY KEY,
    Panchayat_Member_ID INT NOT NULL,
    Record_Date DATE NOT NULL,
    Solid_Reports TEXT,
    Air_Pollution_Reports TEXT,
    Tree_Plantation_Rate DECIMAL(10, 2),
    Deforestation_Report TEXT,
    Water_Reports TEXT,
    Waste_Management TEXT,
    FOREIGN KEY (Panchayat_Member_ID) REFERENCES Panchayat_Member(Panchayat_Member_ID) ON DELETE CASCADE
);

