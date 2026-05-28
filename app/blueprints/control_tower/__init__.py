from flask import Blueprint, jsonify

from app.services.control_tower.snapshot import build_snapshot

control_tower_bp = Blueprint("control_tower", __name__)


@control_tower_bp.route("/api/control-tower/snapshot")
def control_tower_snapshot():
    return jsonify(build_snapshot())
