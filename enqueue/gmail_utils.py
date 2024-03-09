import base64
import json
import os
import quopri
import re
from datetime import datetime, timedelta
from typing import Optional

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pydantic import BaseModel
from supabase import create_client, Client

import tiktoken

enc = tiktoken.get_encoding("cl100k_base")

# Gmail API scopes for reading the email and creating labels
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
]


def clean_whitespace(text):
    """
    Replace HTML non-breaking spaces, multiple spaces, newlines, tabs, zero-width spaces,
    and non-breaking spaces with a single space.
    """
    # Replace known invisible characters and HTML entities
    replacements = {
        "&nbsp;": " ",
        "&zwnj;": "",
        "\u200B": "",  # Zero-width space
        "\u200C": "",  # Zero-width non-joiner
        "\u2800": "",  # Braille blank
    }
    for search, replace in replacements.items():
        text = text.replace(search, replace)
    text = re.sub(r"[\u200B\u200C\u200D\uFEFF]+", "", text)
    text = re.sub(r"[\s]+", " ", text)
    return text.strip()


def decode_quoted_printable(data):
    """
    Attempts to decode quoted-printable data to plain text.
    Removes non-ASCII characters before decoding and handles UnicodeDecodeError.
    """
    # First, remove non-ASCII characters to ensure quopri.decodestring receives clean input
    ascii_data = data.encode("ascii", "ignore").decode("ascii")

    try:
        # Attempt to decode the cleaned ASCII data
        decoded_data = quopri.decodestring(ascii_data).decode("utf-8")
    except UnicodeDecodeError:
        # If a UnicodeDecodeError occurs, use 'replace' to handle undecodable bytes
        decoded_data = quopri.decodestring(ascii_data).decode("utf-8", "replace")

    return decoded_data


def truncate_url_at_query_parameter(text):
    """
    Truncates URLs at the '?' character to remove query parameters.
    """
    url_pattern = re.compile(r"https?://[^\s]+")

    def truncate_match(match):
        url = match.group(0)
        query_start = url.find("?")
        if query_start != -1:
            return url[:query_start]
        return url

    truncated_text = re.sub(url_pattern, truncate_match, text)
    return truncated_text


# gmail authentication function
def gmail_authenticate(access_token: str, refresh_token: str):
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError(
            "Environment variables GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are required."
        )

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    # Refresh the credentials if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

    service = build("gmail", "v1", credentials=creds)
    return service


# create or find a gmail label
def create_label(service, label_name, label_color):
    existing_labels = (
        service.users().labels().list(userId="me").execute().get("labels", [])
    )
    for label in existing_labels:
        if label["name"].lower() == label_name.lower():
            return label["id"]

    label_body = {"name": label_name}

    if label_color:
        label_body["color"] = {"textColor": "#000000", "backgroundColor": label_color}

    label = service.users().labels().create(userId="me", body=label_body).execute()
    return label["id"]


def assign_label_to_email(service, message_id, label_id):
    service.users().messages().modify(
        userId="me", id=message_id, body={"addLabelIds": [label_id]}
    ).execute()


def get_email_body_and_unsubscribe_link(
    parts, prefer_html=False, token_encoder=enc, snippet=""
):
    body = ""
    unsubscribe_link = None
    link_count = 0  # Initialize link count

    for part in parts:
        mime_type = part.get("mimeType", "")
        data = part.get("body", {}).get("data", "")
        if data:
            decoded_data = base64.urlsafe_b64decode(data.encode("ASCII")).decode(
                "utf-8"
            )

            is_quoted_printable = False
            if "headers" in part:
                for header in part["headers"]:
                    if (
                        header.get("name") == "Content-Transfer-Encoding"
                        and header.get("value") == "quoted-printable"
                    ):
                        is_quoted_printable = True
                        break

            if is_quoted_printable:
                decoded_data = decode_quoted_printable(decoded_data)

            decoded_data = truncate_url_at_query_parameter(decoded_data)

            if "text/plain" in mime_type:
                part_body = clean_whitespace(decoded_data)
                body += " " + part_body  # Ensure separation between parts

            elif "text/html" in mime_type:
                soup = BeautifulSoup(decoded_data, "html.parser")
                part_body = soup.get_text(
                    " ", strip=True
                )  # Use get_text() to extract text
                part_body = clean_whitespace(part_body)  # Clean the extracted text
                unsubscribe_link = find_unsubscribe_link(str(soup)) or unsubscribe_link
                link_count += len(
                    soup.find_all("a", href=True)
                )  # Count links in the HTML part
                body += " " + part_body

            if len(token_encoder.encode(body)) >= 2000:
                break  # Stop processing if the limit is reached

        elif "parts" in part:  # Nested parts
            (
                nested_body,
                nested_link,
                nested_link_count,
            ) = get_email_body_and_unsubscribe_link(
                part.get("parts", []), prefer_html, token_encoder, snippet
            )
            body += " " + nested_body
            unsubscribe_link = nested_link or unsubscribe_link
            link_count += nested_link_count
            if len(token_encoder.encode(body)) >= 2000:
                break

    body = body.strip() or clean_whitespace(snippet)

    return body, unsubscribe_link, link_count


def find_unsubscribe_link(html: str) -> Optional[str]:
    """
    Find the unsubscribe link in an email HTML content, looking both in
    the anchor text and in the text nodes near anchor tags.
    """
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    unsubscribe_keywords = [
        "unsubscribe",
        "email preferences",
        "manage preferences",
        "email settings",
        "email options",
        "notification preferences",
    ]

    # Check both anchor texts and parent anchors of matching text nodes
    links = soup.find_all("a", href=True)
    for link in links:
        text = link.text.strip().lower()
        if any(keyword in text for keyword in unsubscribe_keywords):
            return link["href"]

    # Check for text nodes containing unsubscribe information and their parent anchor tags
    text_nodes = soup.find_all(
        string=lambda text: any(
            keyword in text.lower() for keyword in unsubscribe_keywords
        )
    )
    for node in text_nodes:
        parent = node.find_parent("a", href=True)
        if parent:
            return parent["href"]

    return None


# read emails in the last 1 day by default
def read_emails(service, days=1):
    after_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    query = f"after:{after_date} -from:me"

    email_contents = []
    page_token = None

    while True:
        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, pageToken=page_token)
            .execute()
        )
        messages = response.get("messages", [])

        for message_info in messages:
            msg_id = message_info["id"]
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )
            headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
            parts = msg["payload"].get("parts", [msg["payload"]])
            snippet = msg.get("snippet", "")
            (
                email_body,
                unsubscribe_link,
                num_links,
            ) = get_email_body_and_unsubscribe_link(parts, snippet=snippet)

            # Conditionally include Cc and Bcc if they exist
            email_headers = [
                f"From: {headers.get('From')}",
                f"To: {headers.get('To')}",
                f"Subject: {headers.get('Subject')}",
            ]

            if headers.get("Cc"):
                email_headers.append(f"Cc: {headers.get('Cc')}")
            if headers.get("Bcc"):
                email_headers.append(f"Bcc: {headers.get('Bcc')}")

            email_headers.append(
                f"Email has Unsubscribe Link: {'Yes' if unsubscribe_link else 'No'}"
            )
            email_headers.append(f"Number of Links in Email: {num_links}")

            email_content = "\n".join(email_headers) + "\n---\n" + email_body

            email_contents.append(
                {
                    "id": msg_id,
                    "content": email_content,
                    "unsubscribe_link": unsubscribe_link,
                }
            )

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return email_contents


class OAuth2Token(BaseModel):
    refresh_token: str
    access_token: str


def retrieve_and_decrypt_tokens(user_id: str) -> Optional[OAuth2Token]:
    """
    Retrieve and decrypt OAuth tokens for a given user.

    Args:
    user_id (str): Unique identifier for the user.

    Returns:
    Optional[dict]: A dictionary containing the decrypted OAuth tokens or None if not found.
    """
    supabase: Client = create_client(
        os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
    )

    result = supabase.table("users").select("tokens").eq("id", user_id).execute()
    tokens_data = result.data

    if not tokens_data or not tokens_data[0].get("tokens"):
        return None

    token_data = supabase.rpc(
        "decrypt_secret", {"secret_id": tokens_data[0]["tokens"]}
    ).execute()

    # Check if the decryption was successful
    if not token_data.data:
        return None

    decrypted_secret = token_data.data[0].get("decrypted_secret")
    if not decrypted_secret:
        return None

    oauth_tokens = json.loads(decrypted_secret)
    return {
        "access_token": oauth_tokens.get("access_token"),
        "refresh_token": oauth_tokens.get("refresh_token"),
    }
