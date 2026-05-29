from flask import Blueprint, current_app, jsonify, render_template

from app.services.control_tower.snapshot import build_snapshot

control_tower_bp = Blueprint("control_tower", __name__)


@control_tower_bp.route("/control-tower")
def control_tower_page():
    """Page publique Tour de Contrôle (grille des 53 sondes santé).

    Accessible en direct ET en mode embed (?embed=1) pour intégration
    dans l'iframe du portail. Aucune donnée sensible n'est exposée :
    le filtrage des détails (IP, PID, chemins absolus) est appliqué
    côté template (JS) avant affichage.
    """
    try:
        return render_template("control_tower.html")
    except Exception as e:
        current_app.logger.error("control-tower page error: %s", e)
        return f"Control Tower page error: {e}", 500


@control_tower_bp.route("/api/control-tower/snapshot")
def control_tower_snapshot():
    return jsonify(build_snapshot())
