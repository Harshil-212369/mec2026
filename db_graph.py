
from contextlib import closing

from db import get_connection


def load_graph_from_db(dataset_id):

    with closing(get_connection()) as conn:
        with conn.cursor() as cursor:

            # Retrieve road nodes
            cursor.execute("""
                SELECT node_id, name, lat, lng
                FROM nodes
                WHERE dataset_id = %s
            """, (dataset_id,))

            nodes = {}

            for node_id, name, lat, lng in cursor.fetchall():
                nodes[node_id] = {
                    "name": name,
                    "lat": float(lat),
                    "lng": float(lng)
                }

            # Retrieve all roads, including closures
            cursor.execute("""
                SELECT
                    road_id, node_a, node_b,
                    distance_km, weight, is_closed
                FROM roads
                WHERE dataset_id = %s
            """, (dataset_id,))

            edges = {}
            adj = {node_id: [] for node_id in nodes}
            closed = set()

            for road in cursor.fetchall():
                road_id, a, b, km, w, is_closed = road

                km = float(km)
                w = float(w)

                edges[road_id] = {
                    "id": road_id,
                    "a": a,
                    "b": b,
                    "km": km,
                    "w": w
                }

                adj[a].append((b, road_id, w))
                adj[b].append((a, road_id, w))

                if is_closed:
                    closed.add(road_id)

    ratios = [
        e["w"] / e["km"]
        for e in edges.values()
        if e["km"] > 0
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "adj": adj,
        "closed": closed,
        "min_w_per_km": min(ratios, default=0.0)
    }
