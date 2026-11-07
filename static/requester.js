
const form = document.getElementById("ticketForm");
const requesterSelect = document.getElementById("req_id");
const message = document.getElementById("formMessage");
const submitBtn = document.getElementById("submitBtn");

async function loadRequesters() {
    try {
        const response = await fetch("/api/requesters");

        if (!response.ok) {
            throw new Error("Could not load requesters");
        }

        const requesters = await response.json();

        requesterSelect.innerHTML =
            '<option value="">Select location</option>';

        requesters.forEach(req => {
            const option = document.createElement("option");
            option.value = req.req_id;
            option.textContent = req.name;
            requesterSelect.appendChild(option);
        });

    } catch (error) {
        message.textContent = error.message;
    }
}

function formatLocalDate(date) {
    const pad = n => String(n).padStart(2, "0");

    return (
        date.getFullYear() + "-" +
        pad(date.getMonth() + 1) + "-" +
        pad(date.getDate()) + "T" +
        pad(date.getHours()) + ":" +
        pad(date.getMinutes())
    );
}

// Suggest a two-hour deadline
const initialDeadline = new Date(
    Date.now() + 2 * 60 * 60 * 1000
);

document.getElementById("deadline").value =
    formatLocalDate(initialDeadline);


form.addEventListener("submit", async event => {
    event.preventDefault();

    message.textContent = "";

    const deadlineValue =
        document.getElementById("deadline").value;

    const deadlineDate = new Date(deadlineValue);

    if (
        !Number.isFinite(deadlineDate.getTime()) ||
        deadlineDate <= new Date()
    ) {
        message.textContent =
            "Please select a future deadline.";
        return;
    }

    const ticket = {
        req_id: requesterSelect.value,
        servings_requested:
            Number(document.getElementById("servings").value),
        people_affected:
            Number(document.getElementById("people").value),
        refrigerated:
            document.getElementById("refrigerated").checked,
        deadline: deadlineDate.toISOString()
    };

    submitBtn.disabled = true;
    submitBtn.textContent = "Submitting...";

    try {
        const response = await fetch("/api/tickets", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(ticket)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.error || "Submission failed"
            );
        }

        message.textContent =
            `Ticket #${result.ticket_id} created! ` +
            `Status: ${result.status}`;

        form.reset();
        document.getElementById("deadline").value =
            formatLocalDate(new Date(
                Date.now() + 2 * 60 * 60 * 1000
            ));

    } catch (error) {
        message.textContent = error.message;

    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent =
            "Submit Emergency Request";
    }
});

loadRequesters();


let displayedDataset = null;

async function checkActiveDataset() {
    try {
        const response = await fetch(
            "/api/active-dataset"
        );

        if (!response.ok) return;

        const data = await response.json();

        if (displayedDataset !== data.dataset_id) {
            displayedDataset = data.dataset_id;

            // Reload requester dropdown
            await loadRequesters();

            console.log(
                "Requester region updated:",
                displayedDataset
            );
        }

    } catch (error) {
        console.error(error);
    }
}

// Check for region changes every 5 seconds
checkActiveDataset();
setInterval(checkActiveDataset, 5000);

