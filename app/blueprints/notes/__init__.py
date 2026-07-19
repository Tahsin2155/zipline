from flask import Blueprint

notes_bp = Blueprint('notes', __name__, template_folder='../../templates/notes')

from app.blueprints.notes import routes  # noqa: E402,F401
