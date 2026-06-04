const launchDate = new Date('2026-06-05T18:00:00');

const cdDays = document.getElementById('cd-days');
const cdHours = document.getElementById('cd-hours');
const cdMins = document.getElementById('cd-mins');
const cdSecs = document.getElementById('cd-secs');
const countdown = document.getElementById('countdown');

const count = document.getElementById('count');
const form = document.getElementById('f');
const nameInput = document.getElementById('name');
const emailInput = document.getElementById('email');
const newsletterInput = document.getElementById('newsletter');
const result = document.getElementById('result');

const pad = (n) => String(n).padStart(2, '0');

function tickCountdown() {
  const diff = launchDate - new Date();

  if (diff <= 0) {
    countdown.innerHTML =
      '<div class="cd-box" style="min-width:auto;padding:14px 24px;"><span>🎉 We\'re Live!</span></div>';
    return;
  }

  const days = Math.floor(diff / 86400000);
  const hours = Math.floor((diff % 86400000) / 3600000);
  const mins = Math.floor((diff % 3600000) / 60000);
  const secs = Math.floor((diff % 60000) / 1000);

  cdDays.innerText = pad(days);
  cdHours.innerText = pad(hours);
  cdMins.innerText = pad(mins);
  cdSecs.innerText = pad(secs);
}

tickCountdown();
setInterval(tickCountdown, 1000);

async function loadSubscriberCount() {
  try {
    const response = await fetch('/launch/count');
    if (!response.ok) throw new Error(`Count request failed: ${response.status}`);
    const data = await response.json();
    count.innerText = data.count + ' people on the waitlist';
  } catch (error) {
    console.error('Unable to load subscriber count:', error);
  }
}

loadSubscriberCount();

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  const submitBtn = form.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  submitBtn.innerText = 'Joining...';

  try {
    const response = await fetch('/launch/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: nameInput.value,
        email: emailInput.value,
        newsletter: newsletterInput.checked,
      }),
    });

    if (!response.ok) throw new Error(`Subscribe request failed: ${response.status}`);

    const data = await response.json();
    const message = data.already
      ? `You're already on the list, ${nameInput.value}! We'll be in touch soon.`
      : `Thank you, ${nameInput.value}! You're on the launch list.`;

    result.innerHTML = `
      <div class="alert alert-success mb-0">
        <strong>✨ ${message}</strong>
        <div class="mt-2">
          <a href="${data.link}" target="_blank" class="btn btn-afrigen btn-sm">Join Launch Event →</a>
        </div>
      </div>`;
    form.reset();
    loadSubscriberCount();
  } catch (error) {
    console.error('Subscription failed:', error);
    result.innerHTML = `
      <div class="alert alert-danger mb-0">
        ⚠️ Something went wrong. Please try again shortly.
      </div>`;
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerText = 'Join the Waitlist 🚀';
  }
});
