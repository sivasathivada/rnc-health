import urllib.request, json

BASE = 'http://localhost:8000/api'

# Login
data = json.dumps({'email': 'siva@gmail.com', 'password': 'siva'}).encode()
req = urllib.request.Request(BASE + '/auth/login/', data=data,
                              headers={'Content-Type': 'application/json'}, method='POST')
try:
    resp = urllib.request.urlopen(req)
    tokens = json.loads(resp.read())
    token = tokens['access_token']
    print(f'[OK] Login — user: {tokens["user"]["email"]} role: {tokens["user"]["role"]}')
except Exception as e:
    print(f'[FAIL] Login: {e}')
    exit(1)

H = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

def get(path):
    r = urllib.request.Request(BASE + path, headers=H)
    res = urllib.request.urlopen(r)
    return json.loads(res.read())

def check(label, path, count_key=None):
    try:
        data = get(path)
        if isinstance(data, list):
            print(f'[OK] {label}: {len(data)} records')
        else:
            if count_key:
                print(f'[OK] {label}: {data.get(count_key, data)}')
            else:
                print(f'[OK] {label}: {list(data.keys())}')
        return data
    except Exception as e:
        print(f'[FAIL] {label}: {e}')
        return None

print('\n=== ADMIN API TEST ===')
stats = check('Stats', '/v1/admin/stats/')
if stats:
    print(f'       users={stats["total_users"]} consultants={stats["total_consultants"]} patients={stats["total_patients"]} revenue={stats["total_revenue"]}')

consultants = check('Consultants', '/v1/admin/consultants/')
if consultants:
    for c in consultants:
        name = c.get('user', {}).get('full_name', 'Unknown')
        is_verified = c.get('is_verified', False)
        email_ok = c.get('user', {}).get('is_verified', False)
        print(f'       Dr.{name} | profile_verified={is_verified} | email_verified={email_ok}')

check('Patients', '/v1/admin/patients/')
check('Appointments', '/v1/admin/appointments/')
check('Payments', '/v1/admin/payments/')
check('Specialities', '/v1/admin/specialities/')
check('Reviews', '/v1/admin/consultant-reviews/')
check('Call Sessions', '/v1/admin/call-sessions/')
check('Prescriptions', '/v1/admin/prescriptions/')
check('Slots', '/v1/admin/appointment-slots/')
check('Wallets', '/v1/admin/wallets/')
check('Wallet Transactions', '/v1/admin/wallet-transactions/')
check('Email Tokens', '/v1/admin/verification-tokens/')
check('Stripe Events', '/v1/admin/stripe-events/')
check('Medical History', '/v1/admin/medical-history/')

analytics = check('Analytics', '/v1/admin/analytics/')
if analytics:
    print(f'       roles={analytics.get("user_role_distribution")}')
    print(f'       verification={analytics.get("consultant_verification_rate")}')

print('\n=== ALL TESTS COMPLETE ===')
