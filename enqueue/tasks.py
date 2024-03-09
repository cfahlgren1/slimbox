from supabase import create_client, Client
from rich.console import Console
from dotenv import load_dotenv
from enqueue.gmail_utils import (
    retrieve_and_decrypt_tokens,
    read_emails,
    gmail_authenticate,
    assign_label_to_email,
    create_label,
)
from enqueue.classify import classify_email, Label
from typing import List, Optional
import asyncio
import os

load_dotenv("../")

console = Console()

supabase_url = os.getenv("SUPABASE_URL")
service_role_key = os.getenv("SUPABASE_KEY")
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = os.getenv("REDIS_PORT", 6379)

supabase: Client = create_client(supabase_url, service_role_key)

# Global cache dictionary to store email ID and its classification
email_classification_cache = {}


def get_labels(user_id: str) -> List[Label]:
    labels_result = (
        supabase.table("labels").select("*").eq("user_id", user_id).execute()
    )
    labels = labels_result.data

    return [
        Label(
            name=label["label_name"],
            description=label.get("description"),
            color=label["color"],
        )
        for label in labels
    ]


def get_label_color_from_classification(
    classification: str, labels: List[Label]
) -> Optional[str]:
    for label in labels:
        if label.name == classification:
            return label.color
    return None


async def read_and_label_emails(user_id: str):
    labels = get_labels(user_id)
    auth_tokens = retrieve_and_decrypt_tokens(user_id)

    if auth_tokens:
        access_token = auth_tokens["access_token"]
        refresh_token = auth_tokens["refresh_token"]

        service = gmail_authenticate(access_token, refresh_token)
        emails = read_emails(service=service)

        # classify emails in a batch
        classification_tasks = []
        emails_to_classify = []

        for email in emails:
            # add email to classification queue if not already classified
            if email["id"] not in email_classification_cache:
                emails_to_classify.append(email)
                classification_tasks.append(classify_email(email["content"], labels))

        classification_results = await asyncio.gather(*classification_tasks)

        if len(emails_to_classify) == 0:
            console.print(
                f"No emails to classify for user {user_id}",
                style="bold yellow",
            )
            return

        # create labels and assign to emails
        for email, classification in zip(emails_to_classify, classification_results):
            # skip emails that are not classified
            if classification == "other":
                continue

            color = get_label_color_from_classification(classification, labels)
            label_id = create_label(service, classification, color)
            assign_label_to_email(service, email["id"], label_id)
            email_classification_cache[email["id"]] = classification

        # update last_run_at timestamp
        supabase.table("user_cron_schedules").update({"last_run_at": "now()"}).eq(
            "user_id", user_id
        ).execute()
    else:
        console.print(
            f"User {user_id} has no access tokens, skipping email retrieval",
            style="bold yellow",
        )
