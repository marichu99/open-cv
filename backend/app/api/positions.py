from flask import Blueprint, jsonify

from app.models import ElectivePosition
from app.utils.caching import cache_control

bp = Blueprint("positions", __name__, url_prefix="/api/positions")


@bp.get("")
@cache_control("public, max-age=3600")
def list_positions():
    """The 6 elective seats — static reference data, seeded once (see
    import_geography.py). Used by the campaign manager's assignment UI."""
    return jsonify([p.to_dict() for p in ElectivePosition.query.order_by(ElectivePosition.form_series)])
