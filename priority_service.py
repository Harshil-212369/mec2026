
import heapq
from contextlib import closing
from datetime import datetime, timezone

from psycopg2.extras import RealDictCursor, Json

from db import get_connection
from priority import calculate_priority


AVERAGE_SPEED_KMH = 20


def recalculate_priorities():

    now = datetime.now(timezone.utc)

    with closing(get_connection()) as conn:
        with conn:
            with conn.cursor(
                cursor_factory=RealDictCursor
            ) as cursor:

                # Get active dataset
                cursor.execute("""
                    SELECT active_dataset_id
                    FROM app_settings
                    WHERE setting_id = 1
                    FOR SHARE
                """)

                setting = cursor.fetchone()

                if not setting:
                    raise ValueError("No active dataset")

                dataset_id = setting["active_dataset_id"]

                # Load tickets and their assigned routes
                cursor.execute("""
                    SELECT
                        t.ticket_id,
                        t.req_id,
                        t.people_affected,
                        t.deadline,
                        t.created_at,
                        t.status,
                        t.priority_score,

                        (
                            SELECT MIN(d.route_distance_km)
                            FROM deliveries d
                            WHERE d.dataset_id = t.dataset_id
                              AND d.ticket_id = t.ticket_id
                              AND d.status IN (
                                  'Assigned',
                                  'In Progress'
                              )
                        ) AS route_distance_km

                    FROM tickets t

                    WHERE t.dataset_id = %s
                      AND t.status IN (
                          'Open',
                          'Prioritized',
                          'Resource Assigned',
                          'In Progress',
                          'Delayed',
                          'Re-Routing'
                      )

                    ORDER BY t.ticket_id
                    FOR UPDATE OF t
                """, (dataset_id,))

                tickets = cursor.fetchall()

                priority_heap = []

                for ticket in tickets:

                    distance = ticket["route_distance_km"]

                    # Estimate delivery time if a route exists
                    if distance is not None:
                        estimated_minutes = (
                            float(distance)
                            / AVERAGE_SPEED_KMH
                            * 60
                        )
                    else:
                        # Provisional estimate:
                        # no route has been assigned yet.
                        estimated_minutes = 0

                    score = calculate_priority(
                        people_affected=ticket["people_affected"],
                        deadline=ticket["deadline"],
                        estimated_delivery_minutes=estimated_minutes,
                        created_at=ticket["created_at"]
                    )

                    old_score = ticket["priority_score"]
                    old_status = ticket["status"]

                    # Only change Open -> Prioritized.
                    # Preserve Assigned/In Progress statuses.
                    new_status = (
                        "Prioritized"
                        if old_status == "Open"
                        else old_status
                    )

                    cursor.execute("""
                        UPDATE tickets
                        SET priority_score = %s,
                            status = %s
                        WHERE dataset_id = %s
                          AND ticket_id = %s
                    """, (
                        score,
                        new_status,
                        dataset_id,
                        ticket["ticket_id"]
                    ))

                    if old_status != new_status:
                        cursor.execute("""
                            INSERT INTO ticket_history (
                                dataset_id,
                                ticket_id,
                                old_status,
                                new_status,
                                reason
                            )
                            VALUES (%s, %s, %s, %s, %s)
                        """, (
                            dataset_id,
                            ticket["ticket_id"],
                            old_status,
                            new_status,
                            "Priority calculated"
                        ))

                    # Record meaningful priority changes
                    if (
                        old_score is None
                        or abs(float(old_score) - score) >= 0.01
                    ):
                        cursor.execute("""
                            INSERT INTO system_events (
                                dataset_id,
                                event_type,
                                details
                            )
                            VALUES (%s, %s, %s)
                        """, (
                            dataset_id,
                            "priority-changed",
                            Json({
                                "ticket_id": ticket["ticket_id"],
                                "old_score": (
                                    float(old_score)
                                    if old_score is not None
                                    else None
                                ),
                                "new_score": score,
                                "route_assigned": distance is not None
                            })
                        ))

                    # Heap: higher score comes first
                    # Deadline and creation time break ties.
                    heapq.heappush(
                        priority_heap,
                        (
                            -score,
                            ticket["deadline"],
                            ticket["created_at"],
                            ticket["ticket_id"],
                            {
                                "ticket_id": ticket["ticket_id"],
                                "req_id": ticket["req_id"],
                                "priority_score": score,
                                "estimated_minutes": (
                                    round(estimated_minutes, 2)
                                    if distance is not None
                                    else None
                                ),
                                "status": new_status
                            }
                        )
                    )

    ranked_tickets = []

    while priority_heap:
        ranked_tickets.append(
            heapq.heappop(priority_heap)[4]
        )

    return ranked_tickets
