# constants.py - problem-critical constants and shared reason codes (one place only)
# Author: Jagan (team H/A/J). AI assistance: Claude (Anthropic) generated this
# skeleton; values and comments reviewed by the author.
#
# Every value here is either taken from the problem statement / coordinators,
# or is OUR ASSUMPTION (marked). Change a value here, never inline in code.

# --- Routing -----------------------------------------------------------------
# A* heuristic safety factor. Edge km in Dataset 1 is ~0.2% shorter than the
# straight-line (haversine) distance between its endpoints, so we shrink the
# heuristic slightly to keep it admissible (never overestimates).
ASTAR_SAFETY = 0.99

# --- ETA buffer (OUR ASSUMPTION) ----------------------------------------------
# The buffer covers traffic AND a possible refuelling stop. Fuel is therefore
# not calculated separately: trucks are assumed to refuel at hubs between trips,
# and a mid-trip gas stop fits inside the buffer.
BUFFER_PCT = 0.20        # extra time as a fraction of route travel time
MIN_BUFFER_MIN = 10.0    # minimum extra minutes on any trip (enough for a refuel)
SERVICE_TIME_MIN = 5.0   # minutes to unload at each stop

# --- Multi-stop trips (coordinators: multi-stop allowed) ----------------------
MAX_STOPS = 3            # try every stop order: 3! = 6 orders max

# --- Reason codes shared by routing, matching and the front end ---------------
NO_ROUTE = "NO_ROUTE"
DEADLINE_UNREACHABLE = "DEADLINE_UNREACHABLE"
REROUTE_FAILED = "REROUTE_FAILED"
INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
NO_SUITABLE_VEHICLE = "NO_SUITABLE_VEHICLE"
VEHICLE_BREAKDOWN = "VEHICLE_BREAKDOWN"
