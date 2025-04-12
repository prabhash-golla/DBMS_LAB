from quart import Blueprint

# Import individual blueprints
from .read import read_bp
from .write import write_bp
from .update import update_bp
from .delete import delete_bp

# Create a list of blueprints to register
blueprints = [read_bp, write_bp, update_bp, delete_bp]