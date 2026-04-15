"""
backfill_emails.py — connect to Gmail via IMAP and backfill expenses
by forwarding bank alert emails to the /parse-email API endpoint.

Usage:
    python backfill_emails.py [--days N] [--person NAME] [--dry-run] [--api URL]

Options:
    --days N        How many days back to search (default: 90)
    --person NAME   Person to tag expenses as (default: Saket)
    --dry-run       Parse emails but do NOT save to Google Sheet
    --api URL       API base URL (default: http://localhost:8000)
"""

import argparse
import email
import getpass
import imaplib
import os
import sys
from datetime import date, timedelta
from email.header import decode_header as _decode_header

import requests

# ── Bank sender addresses to search for ──────────────────────────────────────

BANK_SENDERS = [
    "alerts@hdfcbank.net",
    "noreply@hdfcbank.com",
    "phishingmail@hdfcbank.net",
    "alerts@icicibank.com",
    "credit_cards@icicibank.com",
]

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


# ── Helpers ───────────────────────────────────────────────────────────────────

def _decode_str(value: str | bytes, charset: str | None) -> str:
    if isinstance(value, bytes):
        return value.decode(charset or "utf-8", errors="replace")
    return value


def get_plain_body(msg: email.message.Message) -> str:
    """Return the plain-text body of an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        if payload:
            return payload.decode(charset, errors="replace")
    return ""


def get_sender(msg: email.message.Message) -> str:
    raw = msg.get("From", "")
    # Extract bare address from "Name <addr@domain>"
    if "<" in raw and ">" in raw:
        return raw[raw.index("<") + 1 : raw.index(">")].strip().lower()
    return raw.strip().lower()


def fetch_bank_emails(
    imap: imaplib.IMAP4_SSL,
    since_date: date,
) -> list[tuple[str, str]]:
    """
    Search all bank senders and return list of (from_address, body) tuples.
    De-duplicates by message-id.
    """
    since_str = since_date.strftime("%d-%b-%Y")  # e.g. "06-Jan-2026"
    seen_ids: set[str] = set()
    results: list[tuple[str, str]] = []

    imap.select("INBOX")

    for sender in BANK_SENDERS:
        # IMAP search: FROM + SINCE
        status, data = imap.search(None, f'(FROM "{sender}" SINCE "{since_str}")')
        if status != "OK" or not data[0]:
            continue

        msg_nums = data[0].split()
        print(f"  {sender}: {len(msg_nums)} email(s) found")

        for num in msg_nums:
            status, raw = imap.fetch(num, "(RFC822)")
            if status != "OK":
                continue
            raw_bytes = raw[0][1]
            msg = email.message_from_bytes(raw_bytes)

            mid = msg.get("Message-ID", "").strip()
            if mid and mid in seen_ids:
                continue
            if mid:
                seen_ids.add(mid)

            from_addr = get_sender(msg)
            body = get_plain_body(msg)
            if body:
                results.append((from_addr, body))

    return results


def call_parse_email(
    api_url: str,
    email_from: str,
    email_body: str,
    person: str,
    dry_run: bool,
) -> dict:
    """POST to /parse-email (or simulate if dry_run)."""
    if dry_run:
        # Import the parsing helpers directly so dry-run works offline
        try:
            from api import (
                _detect_bank,
                _extract_amount,
                _extract_date,
                _extract_merchant_hdfc,
                _extract_merchant_icici,
                _is_credit_alert,
                _is_refund,
                _extract_refund_merchant,
                _categorize,
            )
            bank = _detect_bank(email_from)
            body = email_body
            if _is_credit_alert(body, bank):
                return {"status": "success", "transaction_type": "skipped",
                        "amount": None, "merchant": None, "category": None}
            amount = _extract_amount(body)
            if amount is None:
                return {"status": "skipped", "reason": "Could not extract amount",
                        "transaction_type": "unknown"}
            if _is_refund(body):
                merchant = _extract_refund_merchant(body)
                category = "refund"
                txn_type = "refund"
            else:
                if bank == "HDFC":
                    merchant = _extract_merchant_hdfc(body)
                else:
                    merchant = _extract_merchant_icici(body)
                category = _categorize(merchant)
                txn_type = "expense"
            return {"status": "success", "transaction_type": txn_type,
                    "amount": amount, "merchant": merchant, "category": category}
        except ImportError:
            return {"status": "error", "reason": "api.py not importable for dry-run"}

    resp = requests.post(
        f"{api_url}/parse-email",
        json={"email_body": email_body, "email_from": email_from, "person": person},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill expenses from Gmail bank alerts")
    parser.add_argument("--days",   type=int, default=90,                   help="Days back to search (default: 90)")
    parser.add_argument("--person", type=str, default="Saket",              help="Person tag for expenses (default: Saket)")
    parser.add_argument("--api",    type=str, default="http://localhost:8000", help="API base URL")
    parser.add_argument("--dry-run", action="store_true",                   help="Parse only, do not save")
    args = parser.parse_args()

    since = date.today() - timedelta(days=args.days)
    dry_label = " [DRY RUN]" if args.dry_run else ""
    print(f"\nBackfill{dry_label}: searching last {args.days} days (since {since}) for {args.person}\n")

    # ── Credentials ───────────────────────────────────────────────────────────
    gmail_user = input("Gmail address: ").strip()
    gmail_pass = getpass.getpass("Gmail app password: ")

    # ── Connect via IMAP ──────────────────────────────────────────────────────
    print(f"\nConnecting to {IMAP_HOST}...")
    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        imap.login(gmail_user, gmail_pass)
    except imaplib.IMAP4.error as exc:
        print(f"Login failed: {exc}")
        print("Tip: use a Gmail App Password (myaccount.google.com/apppasswords), not your regular password.")
        sys.exit(1)

    print("Connected. Searching for bank emails...\n")

    # ── Fetch & process ───────────────────────────────────────────────────────
    try:
        emails = fetch_bank_emails(imap, since)
    finally:
        imap.logout()

    if not emails:
        print("\nNo bank emails found.")
        return

    print(f"\nProcessing {len(emails)} email(s)...\n")

    saved = skipped = errors = 0
    rows: list[dict] = []

    for from_addr, body in emails:
        try:
            result = call_parse_email(args.api, from_addr, body, args.person, args.dry_run)
        except requests.RequestException as exc:
            print(f"  API error: {exc}")
            errors += 1
            continue

        txn = result.get("transaction_type", "unknown")
        amount   = result.get("amount")
        merchant = result.get("merchant", "")
        category = result.get("category", "")
        status   = result.get("status", "")
        reason   = result.get("reason", "")

        if status == "skipped" or txn == "skipped":
            skipped += 1
            rows.append({"status": "SKIPPED", "amount": "-", "merchant": reason or "credit/unknown", "category": "-"})
        elif status == "success" and amount is not None:
            saved += 1
            tag = "SAVED" if not args.dry_run else "PARSED"
            rows.append({"status": f"{tag} ({txn})", "amount": f"Rs.{amount:,.2f}", "merchant": merchant, "category": category})
        else:
            skipped += 1
            rows.append({"status": "SKIPPED", "amount": "-", "merchant": reason or txn, "category": "-"})

    # ── Summary table ─────────────────────────────────────────────────────────
    print(f"{'STATUS':<22} {'AMOUNT':>12}  {'MERCHANT':<30}  CATEGORY")
    print("-" * 80)
    for r in rows:
        print(f"{r['status']:<22} {r['amount']:>12}  {r['merchant']:<30}  {r['category']}")

    print("-" * 80)
    action = "Parsed" if args.dry_run else "Saved"
    print(f"\n{action}: {saved}  |  Skipped: {skipped}  |  Errors: {errors}\n")


if __name__ == "__main__":
    main()
