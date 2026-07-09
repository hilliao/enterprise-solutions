// Promo code redemption — vanilla JS, no jQuery required.
// PUT {email, name} to the promotions service keyed by the Firestore doc ID.
const PROMO_SERVICE_URL = 'http://services.googlecloud.fr:5001/promotions/';

document.addEventListener('DOMContentLoaded', () => {
    const promoInput = document.getElementById('promo');
    const queryParam = new URLSearchParams(window.location.search).get('promo-code');
    if (queryParam) {
        promoInput.value = queryParam;
    }

    document.getElementById('promo-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        console.log('clicked redeem');

        const log = document.getElementById('put_response');
        const promo = promoInput.value.trim();
        const email = document.getElementById('email').value.trim();
        const name = document.getElementById('name').value.trim();

        try {
            const response = await fetch(PROMO_SERVICE_URL + encodeURIComponent(promo), {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, name}),
            });
            const result = await response.json();
            if (!response.ok) {
                throw new Error(JSON.stringify(result));
            }
            log.insertAdjacentHTML('beforeend',
                `<p class="log-ok">${JSON.stringify(result)}<br>` +
                `Please proceed to submit <a href="${result['form-url']}">the Google form</a> ` +
                'to complete the process.</p>');
        } catch (error) {
            log.insertAdjacentHTML('beforeend', `<p class="log-err">${error}</p>`);
        }
    });
});
