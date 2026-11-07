
from db_graph import load_graph_from_db
from routing import shortest_path

graph = load_graph_from_db("toronto-downtown")

print("Nodes:", len(graph["nodes"]))
print("Roads:", len(graph["edges"]))
print("Closed roads:", graph["closed"])

route = shortest_path(graph, 33, 34)
print("Supplier P0 to hospital P3:", route)
