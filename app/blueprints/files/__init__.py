from flask import Blueprint

files_bp = Blueprint('files', __name__, template_folder='../../templates/files')

from app.blueprints.files import routes  # noqa: E402,F401
