
from flask import Flask, render_template, jsonify
from psycopg2.extras import RealDictCursor
from db import get_connection
from datetime import datetime, timezone
from psycopg2.extras import Json
from contextlib import closing
from flask import request, session, abort, redirect, url_for
from functools import wraps
import os
import json
import tempfile
from pathlib import Path
from werkzeug.exceptions import RequestEntityTooLarge
from load_dataset import import_dataset
from priority_service import recalculate_priorities
from dispatcher import run_db_once

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


# Demo-only session secret
# For local use; change before any real deployment.
app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "hackathon-demo-only-secret"
)

DEMO_USERS = {
    "operations": {
        "username": "operations",
        "password": "demo123"
    },
    "requester": {
        "username": "requester",
        "password": "demo123"
    }
}


def get_active_dataset():
    with closing(get_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT active_dataset_id
                FROM app_settings
                WHERE setting_id = 1
            """)

            result = cursor.fetchone()

            if result is None:
                raise RuntimeError(
                    "No active dataset configured"
                )

            return result[0]


@app.route("/api/active-dataset")
def active_dataset_api():
    dataset_id = get_active_dataset()

    return jsonify({
        "dataset_id": dataset_id
    })

def login_required(role):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if session.get("role") != role:
                return redirect(
                    url_for("login", role=role)
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator


@app.route("/api/datasets")
def get_datasets():
    with closing(get_connection()) as conn:
        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute("""
                SELECT
                    d.dataset_id,
                    d.name,
                    (
                        d.dataset_id =
                        a.active_dataset_id
                    ) AS is_active
                FROM datasets d
                CROSS JOIN app_settings a
                WHERE a.setting_id = 1
                ORDER BY d.name
            """)

            datasets = cursor.fetchall()

    return jsonify(datasets)

def operations_api_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        if session.get("role") != "operations":
            return jsonify({
                "error": "Operations login required"
            }), 403

        return func(*args, **kwargs)

    return wrapper

@app.route("/api/datasets/activate",methods=["POST"])
@operations_api_required
def activate_dataset():
    data = request.get_json(silent=True) or {}
    dataset_id = data.get("dataset_id")

    if not isinstance(dataset_id, str) or not dataset_id:
        return jsonify({
            "error": "Dataset ID required"
        }), 400

    with closing(get_connection()) as conn:
        with conn:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT 1
                    FROM datasets
                    WHERE dataset_id = %s
                """, (dataset_id,))

                if cursor.fetchone() is None:
                    return jsonify({
                        "error": "Dataset not found"
                    }), 404

                cursor.execute("""
                    UPDATE app_settings
                    SET active_dataset_id = %s
                    WHERE setting_id = 1
                """, (dataset_id,))

    return jsonify({
        "message": "Active region updated",
        "dataset_id": dataset_id
    })


@app.route("/api/datasets/upload",methods=["POST"])
@operations_api_required
def upload_dataset():
    uploaded = request.files.get("file")

    if uploaded is None or not uploaded.filename:
        return jsonify({
            "error": "No file selected"
        }), 400

    if not uploaded.filename.lower().endswith(".json"):
        return jsonify({
            "error": "Only JSON files are supported"
        }), 400

    temp_path = None

    try:
        # Read and validate JSON structure
        data = json.load(uploaded.stream)

        required = [
            "id", "name", "center", "nodes",
            "edges", "pois", "hubs", "trucks"
        ]

        if not isinstance(data, dict):
            raise ValueError("Dataset must be a JSON object")

        missing = [k for k in required if k not in data]

        if missing:
            raise ValueError(
                "Missing dataset fields: " +
                ", ".join(missing)
            )

        dataset_id = data["id"]

        if not isinstance(dataset_id, str) or not dataset_id:
            raise ValueError("Invalid dataset ID")

        # Prevent importing over an existing region
        with closing(get_connection()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 1 FROM datasets
                    WHERE dataset_id = %s
                """, (dataset_id,))

                if cursor.fetchone():
                    return jsonify({
                        "error": "Dataset ID already exists"
                    }), 409

        # Reuse existing JSON importer
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            delete=False
        ) as temporary:
            json.dump(data, temporary)
            temp_path = Path(temporary.name)

        import_dataset(temp_path)

        # Activate if selected
        activate = (
            request.form.get("activate", "true").lower()
            == "true"
        )

        if activate:
            with closing(get_connection()) as conn:
                with conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            UPDATE app_settings
                            SET active_dataset_id = %s
                            WHERE setting_id = 1
                        """, (dataset_id,))

        return jsonify({
            "message": "Dataset imported successfully",
            "dataset_id": dataset_id,
            "activated": activate
        }), 201

    except (ValueError, KeyError, TypeError) as error:
        return jsonify({
            "error": str(error)
        }), 400

    except Exception:
        app.logger.exception("Dataset import failed")
        return jsonify({
            "error": "Import failed. Check server logs."
        }), 500

    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@app.route("/login/<role>", methods=["GET", "POST"])
def login(role):

    if role not in DEMO_USERS:
        return "Invalid role", 404

    if request.method == "POST":

        username = request.form.get(
            "username", ""
        ).strip()

        password = request.form.get(
            "password", ""
        )

        user = DEMO_USERS[role]

        if (
            username == user["username"]
            and password == user["password"]
        ):
            session.clear()
            session["role"] = role
            session["username"] = username

            return redirect(
                url_for(role)
            )

        return render_template(
            "login.html",
            role=role,
            error="Invalid username or password"
        )

    return render_template(
        "login.html",
        role=role,
        error=None
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/operations")
@login_required("operations")
def operations():
    return render_template("index.html")


@app.route("/requester")
@login_required("requester")
def requester():
    return render_template("requester.html")



@app.route(
    "/api/priorities/recalculate",
    methods=["POST"]
)
@operations_api_required
def refresh_priorities():

    try:
        ranked = recalculate_priorities()

        return jsonify({
            "message": "Priorities recalculated",
            "tickets": ranked
        }), 200

    except Exception:
        app.logger.exception(
            "Priority calculation failed"
        )

        return jsonify({
            "error": "Priority calculation failed"
        }), 500


@app.route("/api/requesters")
def get_requesters():
    dataset_id = get_active_dataset()
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT r.*, n.lat, n.lng
                FROM requesters r
                JOIN nodes n
                  ON r.dataset_id = n.dataset_id
                 AND r.location_node = n.node_id
                WHERE r.dataset_id = %s
                ORDER BY r.req_id
            """, (dataset_id,))

            requesters = cursor.fetchall()

    return jsonify(requesters)


@app.route("/api/map")
def get_map_data():
    dataset_id = request.args.get("dataset_id")

    if not dataset_id:
        dataset_id = get_active_dataset()

    with get_connection() as conn:
        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            # Road intersections
            cursor.execute("""
                SELECT node_id, name, lat, lng
                FROM nodes
                WHERE dataset_id = %s
                ORDER BY node_id
            """, (dataset_id,))
            nodes = cursor.fetchall()

            # Road connections
            cursor.execute("""
                SELECT road_id, node_a, node_b,
                       street, distance_km, weight,
                       is_closed
                FROM roads
                WHERE dataset_id = %s
                ORDER BY road_id
            """, (dataset_id,))
            roads = cursor.fetchall()

            # Food suppliers
            cursor.execute("""
                SELECT s.supp_id, s.name,
                       s.normal_stock, s.cold_stock,
                       n.node_id, n.lat, n.lng
                FROM suppliers s
                JOIN nodes n
                  ON s.dataset_id = n.dataset_id
                 AND s.location_node = n.node_id
                WHERE s.dataset_id = %s
            """, (dataset_id,))
            suppliers = cursor.fetchall()

            # Emergency destinations
            cursor.execute("""
                SELECT r.req_id, r.name, r.category,
                       n.node_id, n.lat, n.lng
                FROM requesters r
                JOIN nodes n
                  ON r.dataset_id = n.dataset_id
                 AND r.location_node = n.node_id
                WHERE r.dataset_id = %s
            """, (dataset_id,))
            requesters = cursor.fetchall()

    return jsonify({
        "dataset_id": dataset_id,
        "nodes": nodes,
        "roads": roads,
        "suppliers": suppliers,
        "requesters": requesters
    })

@app.route("/requester")
def request_page():
    return render_template("requester.html")


@app.route("/api/tickets", methods=["POST"])
def create_ticket():

    # 1. Receive JSON from requester form
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body"}), 400

    # 2. Validate submitted information
    try:
        req_id = str(data["req_id"]).strip()
        crisis_type = "food_shortage"

        servings = int(data["servings_requested"])
        people = int(data["people_affected"])
        refrigerated = data["refrigerated"]

        deadline = datetime.fromisoformat(
            data["deadline"].replace("Z", "+00:00")
        )

        if not req_id:
            raise ValueError("Requester ID is required")

        if isinstance(data["servings_requested"], bool) or \
           isinstance(data["people_affected"], bool):
            raise ValueError("Invalid numeric fields")

        if servings <= 0 or people <= 0:
            raise ValueError("Quantities must be positive")

        if type(refrigerated) is not bool:
            raise ValueError("Refrigerated must be true or false")

        if deadline.tzinfo is None:
            raise ValueError("Deadline requires a timezone")

        if deadline <= datetime.now(timezone.utc):
            raise ValueError("Deadline must be in the future")

    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        return jsonify({"error": str(exc)}), 400

    # 3. Save ticket to Neon
    try:
        with closing(get_connection()) as conn:
            with conn:
                with conn.cursor() as cursor:

                    # Retrieve current active dataset
                    cursor.execute("""
                        SELECT active_dataset_id
                        FROM app_settings
                        WHERE setting_id = 1
                        FOR SHARE
                    """)

                    result = cursor.fetchone()

                    if result is None:
                        return jsonify({
                            "error": "No active dataset configured"
                        }), 500

                    dataset_id = result[0]

                    # Verify requester exists in selected region
                    cursor.execute("""
                        SELECT 1
                        FROM requesters
                        WHERE dataset_id = %s
                          AND req_id = %s
                    """, (dataset_id, req_id))

                    if cursor.fetchone() is None:
                        return jsonify({
                            "error": "Requester not found in active region"
                        }), 400

                    # Create emergency ticket
                    cursor.execute("""
                        INSERT INTO tickets (
                            dataset_id,
                            req_id,
                            crisis_type,
                            servings_requested,
                            people_affected,
                            refrigerated,
                            deadline,
                            status
                        )
                        VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s, 'Open'
                        )
                        RETURNING ticket_id
                    """, (
                        dataset_id,
                        req_id,
                        crisis_type,
                        servings,
                        people,
                        refrigerated,
                        deadline
                    ))

                    ticket_id = cursor.fetchone()[0]

                    # Record initial ticket status
                    cursor.execute("""
                        INSERT INTO ticket_history (
                            dataset_id,
                            ticket_id,
                            old_status,
                            new_status,
                            reason
                        )
                        VALUES (
                            %s, %s, NULL, 'Open', %s
                        )
                    """, (
                        dataset_id,
                        ticket_id,
                        "Emergency ticket submitted"
                    ))

                    # Record system event
                    cursor.execute("""
                        INSERT INTO system_events (
                            dataset_id,
                            event_type,
                            details
                        )
                        VALUES (%s, %s, %s)
                    """, (
                        dataset_id,
                        "crisis-created",
                        Json({
                            "ticket_id": ticket_id,
                            "req_id": req_id,
                            "servings_requested": servings
                        })
                    ))

        # Transaction committed successfully
        return jsonify({
            "message": "Ticket submitted successfully",
            "ticket_id": ticket_id,
            "dataset_id": dataset_id,
            "status": "Open"
        }), 201

    except Exception:
        app.logger.exception("Ticket creation failed")

        return jsonify({
            "error": "Unable to save ticket"
        }), 500


@app.route("/api/dispatch", methods=["POST"])
@operations_api_required
def run_dispatch():

    try:
        # 1. Calculate priority scores
        ranked = recalculate_priorities()

        # 2. Get current active region
        dataset_id = get_active_dataset()

        # 3. Execute dispatch using priority scores
        result = run_db_once(dataset_id)

        # 4. Return assignments to Operations
        return jsonify({
            "success": True,
            "dataset_id": dataset_id,
            "tickets_prioritized": len(ranked),
            "assignments_created": len(
                result["assignments"]
            ),
            "assignments": result["assignments"],
            "status_changes": [
                {
                    "ticket_id": tid,
                    "old_status": old,
                    "new_status": new,
                    "reason": reason
                }
                for tid, old, new, reason
                in result["changes"]
            ]
        }), 200

    except Exception:
        app.logger.exception("Dispatch failed")

        return jsonify({
            "error": "Dispatch failed. See Flask terminal."
        }), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
