import requests
import time

API_URL = "https://expense-api-5azs.onrender.com/parse-email"

emails = [
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.1851.00 is debited from your HDFC Bank Credit Card ending 0175 towards MYNTRA VIA SMARTBUY on 14 Apr, 2026 at 19:54:00.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-14"},
    {"snippet": "Dear Customer, Rs.1200.00 has been debited from account 6788 to VPA paytmqr6txtce@ptys MANAK MEWA SAHAKARA NAGAR on 12-04-26.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-12"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.515.00 is debited from your HDFC Bank Credit Card ending 9549 towards WWW SWIGGY IN on 12 Apr, 2026 at 14:19:15.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-12"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.706.03 is debited from your HDFC Bank Credit Card ending 0175 towards FIRSTCRY on 12 Apr, 2026 at 14:03:08.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-12"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.364.00 is debited from your HDFC Bank Credit Card ending 9549 towards PYU*Swiggy Food on 12 Apr, 2026 at 13:59:03.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-12"},
    {"snippet": "Dear Customer, Rs.4000.00 has been debited from account 6788 to VPA 9205059645@pthdfc ANSHUL ARORA on 11-04-26.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-11"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.4203.50 is debited from your HDFC Bank Credit Card ending 0175 towards FIRSTCRY on 11 Apr, 2026 at 12:37:44.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-11"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.393.00 is debited from your HDFC Bank Credit Card ending 9549 towards RSP*INSTAMART on 10 Apr, 2026 at 08:34:37.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-10"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.553.00 is debited from your HDFC Bank Credit Card ending 9549 towards RSP*INSTAMART on 09 Apr, 2026 at 18:08:53.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-09"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.10413.00 is debited from your HDFC Bank Credit Card ending 0175 towards GYFTR VIA SMARTBUY on 09 Apr, 2026 at 11:43:32.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-09"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.1198.00 is debited from your HDFC Bank Credit Card ending 0175 towards CONFIRMTKT SMART BUY on 06 Apr, 2026 at 23:04:44.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-06"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.3357.00 is debited from your HDFC Bank Credit Card ending 0175 towards SB EMT FLIGHT on 06 Apr, 2026 at 23:01:03.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-06"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.3803.00 is debited from your HDFC Bank Credit Card ending 0175 towards SB EMT FLIGHT on 06 Apr, 2026 at 22:57:20.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-06"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.461.00 is debited from your HDFC Bank Credit Card ending 9549 towards Swiggy on 05 Apr, 2026 at 14:43:08.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-05"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.7695.00 is debited from your HDFC Bank Credit Card ending 0175 towards BALMAPP on 05 Apr, 2026 at 14:32:34.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-05"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.336.00 is debited from your HDFC Bank Credit Card ending 9549 towards PYU*Swiggy Food on 05 Apr, 2026 at 13:49:11.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-05"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.415.00 is debited from your HDFC Bank Credit Card ending 9549 towards RSP*INSTAMART on 04 Apr, 2026 at 13:43:52.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-04"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.595.00 is debited from your HDFC Bank Credit Card ending 9549 towards PYU*Swiggy Food on 04 Apr, 2026 at 12:46:10.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-04"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.630.00 is debited from your HDFC Bank Credit Card ending 9549 towards Swiggy on 04 Apr, 2026 at 08:57:36.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-04"},
    {"snippet": "Dear Customer, Greetings from HDFC Bank! Rs.18694.00 is debited from your HDFC Bank Credit Card ending 0175 towards WWW ACKO COM on 03 Apr, 2026 at 21:45:14.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-03"},
    {"snippet": "Dear Customer, Rs.20000.00 has been debited from account 6788 to VPA zerodha.iccl3.brk@validhdfc ICCL ZERODHA on 02-04-26.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-02"},
    {"snippet": "Dear Customer, Rs.10000.00 has been debited from account 6788 to VPA zerodha.rzpiccl.brk@validicici Zerodha Broking Limited on 02-04-26.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-02"},
    {"snippet": "Dear Customer, Rs.20000.00 has been debited from account 6788 to VPA zerodha.rzpiccl.brk@validicici Zerodha Broking Limited on 02-04-26.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-02"},
    {"snippet": "Dear Customer, Rs.1654.00 has been debited from account 6788 to VPA zerodha.rzpiccl.brk@validicici Zerodha Broking Limited on 01-04-26.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-01"},
    {"snippet": "Dear Customer, Rs.68000.00 has been debited from account 6788 to VPA 9886177077@kotak MURALI KRISHNA G on 01-04-26.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-01"},
    {"snippet": "Dear Customer, Rs.20000.00 has been debited from account 6788 to VPA 8112804282@ybl TARKESHWAR TIWARI on 01-04-26.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-01"},
    {"snippet": "Dear Customer, Rs.20000.00 has been debited from account 6788 to VPA 8112804282@ybl TARKESHWAR TIWARI on 01-04-26.", "from": "alerts@hdfcbank.bank.in", "date": "2026-04-01"},
]

print(f"Starting backfill of {len(emails)} emails from April 2026...\n")

success = 0
skipped = 0
errors = 0

for i, email in enumerate(emails):
    try:
        response = requests.post(API_URL, json={
            "email_body": email["snippet"],
            "email_from": email["from"],
            "person": "Saket"
        }, timeout=30)

        if response.status_code == 200:
            result = response.json()
            status = result.get("status", "unknown")
            if status == "success":
                print(f"✅ [{email['date']}] {result.get('merchant','?')} — Rs.{result.get('amount','?')} — {result.get('category','?')}")
                success += 1
            elif status == "skipped":
                print(f"⏭️  [{email['date']}] Skipped: {result.get('reason','?')}")
                skipped += 1
            else:
                print(f"❓ [{email['date']}] Unknown: {result}")
                errors += 1
        else:
            print(f"❌ [{email['date']}] HTTP {response.status_code}: {response.text[:100]}")
            errors += 1
    except Exception as e:
        print(f"❌ [{email['date']}] Exception: {e}")
        errors += 1

    time.sleep(1)

print(f"\n{'='*50}")
print(f"Total emails: {len(emails)}")
print(f"✅ Successfully logged: {success}")
print(f"⏭️  Skipped: {skipped}")
print(f"❌ Errors: {errors}")
