import random
import string

class PayloadGenerator:
    """
    A class to generate payloads for various endpoints: /read, /write, /update, and /delete.
    
    Attributes:
        available_ids (set): A set of student IDs available for allocation.
        allocated_ids (set): A set of student IDs that have been allocated.
    """

    def __init__(self, low, high):
        """
        Initializes the PayloadGenerator with a range of available student IDs.

        Parameters:
            low (int): Lower bound (inclusive) for student IDs.
            high (int): Upper bound (exclusive) for student IDs.
        """
        self.available_ids = set(range(low, high))
        self.allocated_ids = set()

    def generate_random_payload(self, endpoint):
        """
        Generates a random payload based on the provided endpoint.

        Parameters:
            endpoint (str): One of the following endpoints - "/read", "/write", "/update", "/delete".

        Returns:
            dict: The generated payload appropriate for the endpoint.

        Raises:
            ValueError: If an invalid endpoint is provided.
        """
        if endpoint == "/read":
            return self._read_payload()
        elif endpoint == "/write":
            # Randomly decide how many student entries to create (between 1 and 15)
            return self._write_payload(random.randint(1, 15))
        elif endpoint == "/update":
            return self._update_payload()
        elif endpoint == "/delete":
            return self._delete_payload()
        else:
            raise ValueError("Invalid endpoint.")

    def _read_payload(self):
        """
        Constructs a payload for the /read endpoint using a random range query.

        Returns:
            dict: A dictionary with a query range for student IDs.
        """
        low = random.randint(100000, 999999)
        high = random.randint(low, 999999)
        return {"stud_id": {"low": low, "high": high}}

    def _write_payload(self, num_students):
        """
        Constructs a payload for the /write endpoint. Allocates a number of student IDs
        and creates random student names and marks.

        Parameters:
            num_students (int): Number of student records to generate.

        Returns:
            dict: A dictionary containing the list of student records.

        Raises:
            ValueError: If no more available student IDs exist.
        """
        data = []
        for _ in range(num_students):
            if not self.available_ids:
                raise ValueError("No more available student IDs.")
            stud_id = random.choice(tuple(self.available_ids))
            self.available_ids.remove(stud_id)
            self.allocated_ids.add(stud_id)
            stud_name = ''.join(random.choices(string.ascii_letters, k=random.randint(5, 20)))
            stud_marks = random.randint(0, 100)
            data.append({
                'stud_id': stud_id,
                'stud_name': stud_name,
                'stud_marks': stud_marks
            })
        return {'data': data}

    def _update_payload(self):
        """
        Constructs a payload for the /update endpoint. Selects a random allocated
        student ID and returns updated details for that student.

        Returns:
            dict: A dictionary containing the student ID and the updated data.

        Raises:
            ValueError: If there are no allocated student IDs.
        """
        if not self.allocated_ids:
            raise ValueError("No allocated student IDs.")
        stud_id = random.choice(tuple(self.allocated_ids))
        stud_name = ''.join(random.choices(string.ascii_letters, k=random.randint(5, 20)))
        stud_marks = random.randint(0, 100)
        return {
            'stud_id': stud_id,
            'data': {
                'stud_id': stud_id,
                'stud_name': stud_name,
                'stud_marks': stud_marks
            }
        }

    def _delete_payload(self):
        """
        Constructs a payload for the /delete endpoint. Removes a random allocated
        student ID, making it available again.

        Returns:
            dict: A dictionary with the student ID to be deleted.

        Raises:
            ValueError: If there are no allocated student IDs.
        """
        if not self.allocated_ids:
            raise ValueError("No allocated student IDs.")
        stud_id = random.choice(tuple(self.allocated_ids))
        self.allocated_ids.remove(stud_id)
        self.available_ids.add(stud_id)
        return {'stud_id': stud_id}
