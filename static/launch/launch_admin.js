let subscribers = [];

async function loadDashboard(){
    try {
        const response = await fetch('/launch/admin/data');

        if (!response.ok) {
            renderLaunchList([]);
            renderTable([]);
            document.getElementById('totalSubs').innerText = '—';
            document.getElementById('newsletterSubs').innerText = '—';
            document.getElementById('todaySubs').innerText = '—';
            return;
        }

        subscribers = await response.json();

        updateCards();
        renderLaunchList(subscribers);
        renderTable(subscribers);
    } catch (error) {
        renderLaunchList([]);
        renderTable([]);
        document.getElementById('totalSubs').innerText = '—';
        document.getElementById('newsletterSubs').innerText = '—';
        document.getElementById('todaySubs').innerText = '—';
    }
}

function updateCards(){
    document.getElementById('totalSubs').innerText = subscribers.length;

    const newsletter = subscribers.filter(x => x.newsletter);
    document.getElementById('newsletterSubs').innerText = newsletter.length;

    const today = new Date().toISOString().split('T')[0];
    const todayCount = subscribers.filter(x => x.date && x.date.startsWith(today));
    document.getElementById('todaySubs').innerText = todayCount.length;
}

function renderLaunchList(data){
    const list = document.getElementById('launchList');
    const latest = data.slice(-10).reverse();

    if (!latest.length) {
        list.innerHTML = '<div style="color:#888;">No joiners yet — this updates after the first signup.</div>';
        return;
    }

    list.innerHTML = latest.map(sub => `
        <div class="launch-item">
            <span class="launch-name">${sub.name}</span>
            <span class="launch-meta">${sub.date ? new Date(sub.date).toLocaleString() : ''}</span>
            <span class="launch-badge">${sub.newsletter ? '✨ Newsletter' : 'Launch'}</span>
        </div>
    `).join('');
}

function renderTable(data){
    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = '';

    data.forEach(sub => {
        tbody.innerHTML += `
        <tr>
            <td>${sub.name}</td>
            <td>${sub.email}</td>
            <td>${sub.newsletter ? 'Yes' : 'No'}</td>
            <td>${sub.date ? new Date(sub.date).toLocaleString() : ''}</td>
        </tr>`;
    });
}

document.getElementById('search').addEventListener('input', e => {
    const term = e.target.value.toLowerCase();
    const filtered = subscribers.filter(sub =>
        sub.name.toLowerCase().includes(term) ||
        sub.email.toLowerCase().includes(term)
    );
    renderTable(filtered);
});

setInterval(loadDashboard, 5000);
loadDashboard();

// Newsletter compose (admin session already authenticated server-side)
const sendNewsletterBtn = document.getElementById('sendNewsletterBtn');
const newsletterSubject = document.getElementById('newsletterSubject');
const newsletterBody = document.getElementById('newsletterBody');
const newsletterStatus = document.getElementById('newsletterStatus');

sendNewsletterBtn.addEventListener('click', async () => {
    newsletterStatus.innerText = 'Sending...';
    try {
        const res = await fetch('/launch/admin/newsletter', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subject: newsletterSubject.value, body: newsletterBody.value })
        });

        if (!res.ok) throw new Error('Send failed');
        const data = await res.json();
        newsletterStatus.innerText = `Sent to ${data.sent} addresses`;
    } catch (err) {
        newsletterStatus.innerText = 'Send failed';
    }
});
