import os
import base64
import re
import pickle
import time
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://mail.google.com/']
CREDENTIALS_PATH = 'config/credentials.json'
TOKEN_PATH = 'config/token.pickle'


def authenticate_gmail():
    creds = None

    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)

    service = build('gmail', 'v1', credentials=creds)
    return service


def get_email_body(payload):
    """
    Extracts plain text content from email payload.
    Handles both text/plain and text/html formats.
    Strips HTML tags if only HTML version is available.
    """
    body = ""

    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                data = part['body'].get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode(
                        'utf-8', errors='ignore')
                    break
            elif part['mimeType'] == 'text/html' and not body:
                data = part['body'].get('data', '')
                if data:
                    html = base64.urlsafe_b64decode(data).decode(
                        'utf-8', errors='ignore')
                    body = re.sub(r'<[^>]+>', ' ', html)
                    body = re.sub(r'\s+', ' ', body).strip()
    else:
        data = payload['body'].get('data', '')
        if data:
            body = base64.urlsafe_b64decode(data).decode(
                'utf-8', errors='ignore')

    return body[:500].strip()


def fetch_email_details(service, message_id, retries=3):
    """
    Fetches full details of a single email including body text.
    Retries on network errors up to 3 times.
    """
    for attempt in range(retries):
        try:
            msg = service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()

            headers = msg['payload']['headers']
            subject = next(
                (h['value'] for h in headers if h['name'] == 'Subject'),
                'No Subject')
            sender = next(
                (h['value'] for h in headers if h['name'] == 'From'),
                'Unknown')
            date = next(
                (h['value'] for h in headers if h['name'] == 'Date'),
                'Unknown')
            body = get_email_body(msg['payload'])

            return {
                'id': message_id,
                'subject': subject,
                'sender': sender,
                'date': date,
                'body': body
            }

        except Exception as e:
            if attempt < retries - 1:
                print(f"Network error, retrying ({attempt + 1}/{retries})...")
                time.sleep(3)
            else:
                raise e


def fetch_emails(service, max_results=500, after_date=None):
    """
    Fetches emails from inbox.
    If after_date provided - only fetches emails newer than that date.
    after_date format: 'YYYY/MM/DD'
    """
    # Build query filter
    query = ""
    if after_date:
        query = f"after:{after_date}"

    results = service.users().messages().list(
        userId='me',
        labelIds=['INBOX'],
        maxResults=max_results,
        q=query
    ).execute()

    messages = results.get('messages', [])

    if not messages:
        print("No new emails found.")
        return []

    emails = []
    for message in messages:
        try:
            email = fetch_email_details(service, message['id'])
            emails.append(email)
            print(f"Subject: {email['subject'][:60]}")
            print(f"From: {email['sender'][:60]}")
            print(f"Date: {email['date']}")
            print("-" * 50)
        except Exception as e:
            print(f"Failed to fetch email {message['id']}: {e}")
            continue

    return emails


def delete_email(service, email_id):
    """
    Moves an email to trash in Gmail.
    Safer than permanent delete - emails stay for 30 days.
    """
    try:
        service.users().messages().trash(
            userId='me',
            id=email_id
        ).execute()
        return True
    except Exception as e:
        print(f"Failed to delete email {email_id}: {e}")
        return False


if __name__ == "__main__":
    service = authenticate_gmail()
    emails = fetch_emails(service)
    print(f"\nTotal emails fetched: {len(emails)}")