from flask import Blueprint, jsonify

from app.models import ElectivePosition

bp = Blueprint("positions", __name__, url_prefix="/api/positions")


@bp.get("")
def list_positions():
    """The 6 elective seats — static reference data, seeded once (see
    import_geography.py). Used by the campaign manager's assignment UI."""
    return jsonify([p.to_dict() for p in ElectivePosition.query.order_by(ElectivePosition.form_series)])
