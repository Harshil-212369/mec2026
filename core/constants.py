"""Problem-critical constants in one place. Each one cites where it comes from.

"Statement" = docs/problem_statement.md (organizers' text). "Ours" = a team decision we must
justify to the judges; change it here only, and the tests will tell you what moved.

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""

# Statement 3.1 "Crisis state machine": the nine states, spelled exactly as in Aadil's
# tickets_status_check constraint.
STATES = (
    "Open", "Prioritized", "Resource Assigned", "In Progress", "Re-Routing",
    "Delivered", "Resolved", "Delayed", "Failed",
)

# Statement 3.1 "System events": the seven required events, hyphenated exactly as Aadil's
# system_events rows already use them ("crisis-created").
REQUIRED_EVENTS = (
    "crisis-created", "priority-changed", "route-updated", "resource-depleted",
    "road-closed", "vehicle-breakdown", "crisis-resolved",
)
# Ours: extra events the dashboard needs.
EXTRA_EVENTS = ("road-reopened", "vehicle-repaired", "vehicle-moved", "ticket-status", "stock-changed")
EVENTS = REQUIRED_EVENTS + EXTRA_EVENTS

# Statement 3.1 "Crisis submission" lists severity level; range 1..5 from the original schema
# CHECK (severity >= 1 AND severity <= 5).
SEVERITY_MIN, SEVERITY_MAX = 1, 5

# ---------------------------------------------------------------- scoring (ours) ----
# Statement 3.1 "Priority scoring": consider severity, people affected, food shortage,
# deadlines, location type, travel/response time. Plus a waiting-time adjustment (queue bullet).
SCORE_TERMS = ("S", "P", "F", "C", "D", "W")
P_REF = 500          # people: log-damped, 500 people = full marks (big sites matter more, not unboundedly)
F_REF = 200          # servings still needed: 200 = full marks
H_MIN = 120.0        # deadline pressure horizon: slack >= 120 min -> no pressure
AGING_CAP_MIN = 120.0  # waiting time: 120 min waiting = full aging term
CATEGORY_WEIGHT = {"hospital": 1.0, "shelter": 0.9, "community": 0.7}
CATEGORY_DEFAULT = 0.5   # any other category (Dataset 2 may add new ones); flagged when used

# Weights per policy preset; each preset sums to 1.0 (checked by tests and at scoring time).
POLICIES = {
    "balanced":       {"S": 0.30, "P": 0.20, "F": 0.10, "C": 0.10, "D": 0.20, "W": 0.10},
    "deadline_first": {"S": 0.20, "P": 0.10, "F": 0.05, "C": 0.05, "D": 0.50, "W": 0.10},
    "max_people":     {"S": 0.20, "P": 0.45, "F": 0.10, "C": 0.05, "D": 0.10, "W": 0.10},
    "equity":         {"S": 0.25, "P": 0.10, "F": 0.10, "C": 0.10, "D": 0.15, "W": 0.30},
}
DEFAULT_POLICY = "balanced"

# ------------------------------------------------------------ matching (ours) ----
# Dataset gives fuel as 100 = full and nothing else; ARCHITECTURE.md section 5 assumptions.
FUEL_PCT_PER_KM = {False: 0.25, True: 0.30}   # truck 25 L/100 km, reefer 30 L/100 km, 100 L tank
FUEL_RESERVE_PCT = 15.0                         # never plan a trip that ends below 15 %
LOAD_MIN = 10.0     # loading at the supplier
UNLOAD_MIN = 10.0   # unloading at the requester

# ------------------------------------------------------------ engine (ours) ----
# Statement 3.1 "Route planning": clearly indicate when a route is unavailable. A ticket with
# no route stays Delayed (it may reopen) and becomes Failed only this long after its deadline.
FAIL_GRACE_MIN = 60.0
