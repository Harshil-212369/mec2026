
import json
import sys
from pathlib import Path

from db import get_connection


def import_dataset(path: Path):

    # Read the JSON file
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    dataset_id = data["id"]

    # Organize points of interest by ID
    pois_by_id = {
        poi["id"]: poi for poi in data["pois"]
    }

    hub_ids = {
        hub["poiId"] for hub in data["hubs"]
    }

    # Map supplier nodes to supplier IDs
    supplier_by_node = {}

    for hub in data["hubs"]:
        poi = pois_by_id[hub["poiId"]]
        node = poi["node"]

        if node in supplier_by_node:
            raise ValueError(
                f"Multiple suppliers at node {node}"
            )

        supplier_by_node[node] = poi["id"]

    # Connect to Neon
    with get_connection() as conn:
        with conn.cursor() as cursor:

            # 1. DATASET
            cursor.execute("""
                INSERT INTO datasets
                (dataset_id, name, center_lat, center_lng, zoom)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (dataset_id) DO NOTHING
            """, (
                dataset_id,
                data["name"],
                data["center"][0],
                data["center"][1],
                data.get("zoom")
            ))

            # 2. NODES
            for node in data["nodes"]:
                cursor.execute("""
                    INSERT INTO nodes
                    (dataset_id, node_id, name, lat, lng)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (dataset_id, node_id) DO NOTHING
                """, (
                    dataset_id,
                    node["id"],
                    node["name"],
                    node["lat"],
                    node["lng"]
                ))

            # 3. ROADS
            for edge in data["edges"]:
                cursor.execute("""
                    INSERT INTO roads
                    (dataset_id, road_id, node_a, node_b,
                     street, distance_km, weight,
                     is_highway, terrain)
                    VALUES (%s, %s, %s, %s, %s,
                            %s, %s, %s, %s)
                    ON CONFLICT (dataset_id, road_id) DO NOTHING
                """, (
                    dataset_id,
                    edge["id"],
                    edge["a"],
                    edge["b"],
                    edge.get("street"),
                    edge["km"],
                    edge["w"],
                    edge.get("hwy", False),
                    edge.get("terrain")
                ))

            # 4. REQUESTERS
            # All POIs that are not suppliers
            for poi in data["pois"]:

                if poi["id"] in hub_ids:
                    continue

                cursor.execute("""
                    INSERT INTO requesters
                    (dataset_id, req_id, name,
                     category, location_node, address)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (dataset_id, req_id) DO NOTHING
                """, (
                    dataset_id,
                    poi["id"],
                    poi["name"],
                    poi["kind"],
                    poi["node"],
                    poi.get("address")
                ))

            # 5. SUPPLIERS
            for hub in data["hubs"]:

                poi = pois_by_id[hub["poiId"]]

                cursor.execute("""
                    INSERT INTO suppliers
                    (dataset_id, supp_id, name,
                     location_node, address,
                     normal_stock, cold_stock)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (dataset_id, supp_id) DO NOTHING
                """, (
                    dataset_id,
                    poi["id"],
                    poi["name"],
                    poi["node"],
                    poi.get("address"),
                    hub["normal"],
                    hub["cold"]
                ))

            # 6. VEHICLES
            for truck in data["trucks"]:

                home = truck["home"]

                if home not in supplier_by_node:
                    raise ValueError(
                        f"Vehicle {truck['id']} has no home supplier"
                    )

                supplier_id = supplier_by_node[home]

                cursor.execute("""
                    INSERT INTO vehicles
                    (dataset_id, vehicle_id, supp_id,
                     name, start_node, current_node,
                     capacity, refrigerated, fuel)
                    VALUES (%s, %s, %s, %s, %s,
                            %s, %s, %s, %s)
                    ON CONFLICT (dataset_id, vehicle_id) DO NOTHING
                """, (
                    dataset_id,
                    truck["id"],
                    supplier_id,
                    truck["name"],
                    home,
                    home,
                    truck["capacity"],
                    truck["refrigerated"],
                    truck["fuel"]
                ))

            # 7. VERIFY IMPORT
            print(f"\nDataset: {dataset_id}")
            print("---------------------------")

            tables = [
                "datasets",
                "nodes",
                "roads",
                "requesters",
                "suppliers",
                "vehicles"
            ]

            for table in tables:
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table} "
                    "WHERE dataset_id = %s",
                    (dataset_id,)
                )

                count = cursor.fetchone()[0]
                print(f"{table}: {count}")

    # Connection context commits if successful
    print("\nImport committed successfully!")


if __name__ == "__main__":

    file_path = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).with_name("toronto-downtown.json")
    )

    try:
        import_dataset(file_path)

    except Exception as error:
        print(f"Import failed: {error}")
        sys.exit(1)
