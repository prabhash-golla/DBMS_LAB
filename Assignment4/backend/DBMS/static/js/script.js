// Form validation for registration
document.addEventListener('DOMContentLoaded', function() {
    const registrationForm = document.querySelector('form[action="/register"]');
    
    if (registrationForm) {
        registrationForm.addEventListener('submit', function(event) {
            const password = document.getElementById('password').value;
            const role = document.getElementById('role_id').value;
            let isValid = true;
            
            // Basic password validation
            if (password.length < 6) {
                alert('Password must be at least 6 characters long.');
                isValid = false;
            }
            
            // If citizen role is selected, validate required fields
            if (role === '3') {
                const name = document.getElementById('name').value;
                const gender = document.getElementById('gender').value;
                const dob = document.getElementById('dob').value;
                const address = document.getElementById('address').value;
                
                if (!name || !gender || !dob || !address) {
                    alert('Please fill in all required citizen information fields.');
                    isValid = false;
                }
            }
            
            if (!isValid) {
                event.preventDefault();
            }
        });
    }
});

// Toggle visibility of citizen-specific fields based on selected role
function toggleCitizenFields() {
    const roleSelect = document.getElementById('role_id');
    const citizenFields = document.getElementById('citizenFields');
    
    if (roleSelect && citizenFields) {
        if (roleSelect.value === '3') { // Citizen role
            citizenFields.style.display = 'block';
        } else {
            citizenFields.style.display = 'none';
        }
    }
}

// Initialize tooltips and popovers
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize Bootstrap popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function(popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
    
    // Set up role change listener
    const roleSelect = document.getElementById('role_id');
    if (roleSelect) {
        roleSelect.addEventListener('change', toggleCitizenFields);
        // Initial check
        toggleCitizenFields();
    }
});