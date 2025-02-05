#  Golla Meghanandh Manvith Prabhash
#  22CS30027

import psycopg2

def execute_query(conn, query, answer_label):
    print(f"\n{answer_label}",end="")
    cursor = conn.cursor()
    cursor.execute(query)

    rows = cursor.fetchall()

    columns = [desc[0] for desc in cursor.description]
    
    for row in rows:
        for value in row:
            print(f"{value}\t", end="")
        print()
    cursor.close()

def main():
    conninfo = "host=10.5.18.72 dbname=22CS30027 user=22CS30027 password=5243y6!J"
    try:
        conn = psycopg2.connect(conninfo)
        execute_query(conn, "SELECT a.name FROM citizens a JOIN land_records r ON a.citizen_id = r.citizen_id GROUP BY a.name HAVING SUM(r.area_acres) > 1;", "names of all citizens who holds more than 1 acre of land is : \n")
        execute_query(conn, "SELECT b.name FROM citizens b JOIN households h ON b.household_id = h.household_id WHERE b.gender = 'Female' AND h.income < 100000 AND b.education_status = 'Yes' AND DATE_PART('year', AGE(b.dob)) BETWEEN 5 AND 18;", "Girls who study in school with household income less than 1 Lakh per year : \n")
        execute_query(conn, "SELECT SUM(area_acres) AS total_land_area_inacres FROM land_records l WHERE l.crop_type = 'rice';", "Acres of land cultivate rice : ")
        execute_query(conn, "SELECT COUNT(citizen_id) AS total_citizens FROM citizens WHERE dob > '2000-01-01' AND educational_qualification = '10th';", "Number of citizens who are born after 1.1.2000 and have educational qualification of 10th class : ")
        execute_query(conn, "SELECT e.name FROM panchayat_employees p JOIN citizens e ON p.citizen_id = e.citizen_id JOIN land_records l ON l.citizen_id = e.citizen_id GROUP BY e.name HAVING SUM(l.area_acres) > 1;", "Name of all employees of panchayat who also hold more than 1 acre land : \n")
        execute_query(conn, "SELECT c2.name FROM citizens c1 JOIN panchayat_employees pe ON c1.citizen_id = pe.citizen_id JOIN citizens c2 ON c1.household_id = c2.household_id WHERE pe.role = 'Panchayat Pradhan';", "Name of the household members of Panchayat Pradhan : \n")
        execute_query(conn, "SELECT COUNT(*) AS total_street_lights FROM assets WHERE type = 'Street Light' AND location = 'Phulera' AND EXTRACT(YEAR FROM installation_date) = 2024;", "Total number of street light assets installed in a particular locality named Phulera that are installed in 2024 : ")
        execute_query(conn, "SELECT COUNT(v.vaccination_id) AS num_vaccinations FROM citizens c JOIN citizens children ON c.citizen_id = children.father_id OR c.citizen_id = children.mother_id JOIN vaccinations v ON children.citizen_id = v.citizen_id WHERE c.educational_qualification = '10th' AND EXTRACT(YEAR FROM v.date_administered) = 2024 AND DATE_PART('year', AGE(children.dob)) <= 18;", "Number of vaccinations done in 2024 for the children of citizens whose educational qualification is class 10 : ")
        execute_query(conn, "SELECT COUNT(*) AS total_births FROM census_data cd JOIN citizens c ON cd.citizen_id = c.citizen_id WHERE cd.event_type = 'Birth' AND EXTRACT(YEAR FROM cd.event_date) = 2024 AND c.gender = 'Male';", "Total number of births of boy child in the year 2024 : ")
        execute_query(conn, "SELECT COUNT(DISTINCT c.citizen_id) AS total_citizens FROM citizens c WHERE c.household_id IN (SELECT DISTINCT h.household_id FROM households h JOIN panchayat_employees pe ON h.household_id = (SELECT household_id FROM citizens WHERE citizen_id = pe.citizen_id));", "Number of citizens who belong to the household of at least one panchayat employee : ")
        conn.close()

    except Exception as e:
        print(f"Connection to database failed: {e}")


if __name__ == "__main__":
    main()
