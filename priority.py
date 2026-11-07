
from datetime import datetime, timezone


def calculate_priority(
    people_affected,
    deadline,
    estimated_delivery_minutes,
    created_at
):
    now = datetime.now(timezone.utc)

    # Time remaining before deadline (hours)
    hours_remaining = max(
        0,
        (deadline - now).total_seconds() / 3600
    )

    minutes_remaining = max(1, hours_remaining * 60)

    # 1. Population affected (40 points)
    # Full points for 200 or more people
    population_score = min(
        40,
        (people_affected / 200) * 40
    )

    # 2. Deadline urgency (30 points)
    if hours_remaining <= 1:
        deadline_score = 30
    elif hours_remaining <= 3:
        deadline_score = 24
    elif hours_remaining <= 6:
        deadline_score = 18
    elif hours_remaining <= 12:
        deadline_score = 12
    elif hours_remaining <= 24:
        deadline_score = 6
    else:
        deadline_score = 1.5

    # 3. Delivery-time risk (15 points)
    # Higher travel time relative to deadline means higher risk
    delivery_score = min(
        15,
        (max(0, estimated_delivery_minutes) /
         minutes_remaining) * 15
    )

    # 4. Waiting time (15 points)
    # Full points after waiting 120 minutes
    minutes_waiting = max(
        0,
        (now - created_at).total_seconds() / 60
    )

    waiting_score = min(
        15,
        (minutes_waiting / 120) * 15
    )

    # 5. Calculate final priority
    priority = (
        population_score +
        deadline_score +
        delivery_score +
        waiting_score
    )

    return round(min(100, priority), 2)
