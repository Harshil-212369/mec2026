# Rubric (verbatim where available)

Sources, extracted 2026-11-07:
- Scorecard table: `competition documents/Programming Competition Rulebook.pdf`, section 1.7.1 (text extracted with pypdf; the docx does not contain this table).
- Everything else: `competition documents/Programming_Competition_Documents_Revised.docx` (rulebook 1.7 and abstract 3.2).

## Scorecard (rulebook PDF 1.7.1, verbatim; table layout rebuilt from extracted text)
| Category | Judging Criteria | Points |
|---|---|---|
| Core Algorithms & Data Structures | A. Routing: Evaluates the correctness, efficiency, and adaptability of the routing algorithm, including its ability to process network changes and recalculate routes when necessary. | /15 |
| | B. Priority Queue: Evaluates the implementation of an appropriate priority queue, correct prioritization logic, and efficient processing of requests or tasks. | /10 |
| | C. Resource Matching: Assesses the effectiveness of resource allocation, consideration of availability and constraints, and the suitability of matching decisions. | /15 |
| | Core Algorithms & Data Structures Subtotal | /40 |
| System Design: Inputs, Scoring & State Machine | A. Crisis Input & Scoring: Evaluates input validation, data processing, and the consistency and justification of the system's scoring or prioritization methodology. | /15 |
| | B. Crisis State Machine: Evaluates the correctness of state transitions, handling of changing conditions, and consistency of system behaviour. | /10 |
| | C. Real-Time Communication: Assesses the implementation of event-driven communication, information updates, and coordination between system components. | /10 |
| | System Design Subtotal | /35 |
| Dashboard, Constraints & Deliverables | A. Optional Live Website Dashboard: Evaluates the functionality, usability, and clarity of an optional live website dashboard for displaying system information and results. | /5 |
| | B. Constraints & Hidden Test Cases: Evaluates the program's ability to handle technical constraints, unexpected inputs, edge cases, and additional testing scenarios. | /10 |
| | C. Expected Output & Engineering Decisions: Evaluates the completeness and correctness of outputs, required deliverables, and the team's ability to justify its technical decisions. | /10 |
| | Dashboard, Constraints & Deliverables Subtotal | /25 |
| | TOTAL | /100 |

## Rulebook 1.7.1 Judging Matrix (verbatim)
Competitors will be evaluated using the official Programming Competition Scorecard provided by the Competition Organizers. The scorecard will outline the judging categories, evaluation criteria, and maximum points available for each criterion. The total score will be calculated out of one hundred (100) points before any applicable deductions.

## Abstract 3.2 Assessment (verbatim)
Judges will also consider how well the system performs across both datasets. Teams should demonstrate that their solution can adapt to different environments, handle limited resources, and respond to unexpected events such as road closures and vehicle breakdowns. A strong solution should not only work when conditions are ideal, but should also be able to explain what happens when a delivery cannot be completed or when an alternative route or resource is needed.Judges will assess projects using the following criteria:

- Algorithmic Effectiveness: How well the system prioritizes emergencies, finds efficient delivery routes, and assigns available food and vehicles to those in need.
- System Design and Reliability: How effectively the system tracks emergencies, responds to changing situations, and handles challenges such as road closures, food shortages, and vehicle breakdowns.
- User Experience: How easy the system is to understand and use, including how clearly it displays emergency priorities, delivery routes, available resources, and live updates.
- Innovation and Scalability: How creatively the team approaches the challenge and how well their system could adapt to larger cities, more emergencies, and changing resource availability.

## Rulebook 1.1 Goal (verbatim, last sentence)
The winning solution will not necessarily be the most technically correct but the one that has the most real-world application and is most thoroughly thought out.

## Rulebook 1.7.2 Penalty Matrix (verbatim)
| Infraction | Point Penalty |
|---|---|
| Confirmed plagiarism or deliberate misrepresentation of another person's work as original | Disqualification |
| Insufficient Citation | -50 |
| Documents Received After Deadline | -50 |
| Absent Team Member | -25 |
| Entering the presentation room before the assigned time without authorization | First offence: warning; each subsequent offence: -10 |

## Presentation format (rulebook 1.6.2.5, verbatim)
Competitors will have a maximum of ten (10) minutes to present and demonstrate their solutions. All team members must be present and participate in the presentation or be penalized by the judges. Judges then have a maximum of five (5) minutes to ask questions. Judges can ask a question at any time during the presentation. The clock must be stopped during these interruptions. Once the development period has ended, teams may not modify their submitted code or presentation materials. During judging, teams may run and demonstrate their submitted programs using the competition datasets and explain the results generated by their systems.
