import json
import os
from enum import Enum
from typing import List, Optional

from modal import Image, Secret, Stub, enter, method, web_endpoint
from pydantic import BaseModel

from gmail_utils import (
    gmail_authenticate,
    read_emails,
    create_label,
    assign_label_to_email,
)
from models import Label, LabelJob, local_labels
from prompts import LOCAL_PROMPT, PROD_PROMPT
from fastapi import HTTPException

MODEL_DIR = "/model"
BASE_MODEL = "NurtureAI/OpenHermes-2.5-Mistral-7B-16k"
GPU_TYPE = "A100"


def colored_print(color, message):
    colors = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "cyan": "\033[96m",
        "reset": "\033[0m",
    }
    print(f"{colors[color]}{message}{colors['reset']}")


def download_model_to_folder():
    from huggingface_hub import snapshot_download
    from transformers.utils import move_cache

    os.makedirs(MODEL_DIR, exist_ok=True)

    snapshot_download(
        BASE_MODEL,
        local_dir=MODEL_DIR,
        token=os.environ["HF_TOKEN"],
    )
    move_cache()


image = (
    Image.from_registry("nvidia/cuda:12.1.0-base-ubuntu22.04", add_python="3.10")
    .pip_install(
        "huggingface_hub==0.19.4",
        "hf-transfer==0.1.4",
        "outlines==0.0.34",
        "pydantic==2.6.3",
        "tiktoken==0.6.0",
        "google-auth",
        "google-auth-oauthlib",
        "google-auth-httplib2",
        "google-api-python-client",
        "transformers==4.38.1",
        "vllm==0.3.2",
        "beautifulsoup4==4.12.3",
        "supabase==2.4.0",
    )
    # Use the barebones hf-transfer package for maximum download speeds. No progress bar, but expect 700MB/s.
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
    .run_function(
        download_model_to_folder,
        secrets=[Secret.from_name("my-huggingface-secret")],
        timeout=60 * 20,
    )
)

stub = Stub("email-labeler-job", image=image)


@stub.cls(
    gpu=GPU_TYPE,
    secrets=[
        Secret.from_name("my-huggingface-secret"),
    ],
)
class Model:
    @enter()
    def load(self):
        from vllm import LLM

        self.llm = LLM(model=BASE_MODEL, enforce_eager=True)

    @method()
    def generate(self, prompts: List[str], schema: BaseModel):
        from outlines.serve.vllm import JSONLogitsProcessor

        from vllm import SamplingParams

        logits_processor = JSONLogitsProcessor(
            schema=schema, llm=self.llm, whitespace_pattern=""
        )

        result = self.llm.generate(
            prompts,
            sampling_params=SamplingParams(
                max_tokens=150, logits_processors=[logits_processor], temperature=0
            ),
        )

        labels = [output.outputs[0].text for output in result]
        return labels


def assign_labels_to_emails(gmail_service, prompts_with_ids, generated_labels, labels):
    """
    Assigns generated labels to emails based on prompts and labels information.

    :param gmail_service: Authenticated Gmail service instance.
    :param prompts_with_ids: List of dictionaries containing prompts and corresponding email IDs.
    :param generated_labels: List of generated label names from the model.
    :param labels: List of Label objects containing label names and additional metadata.
    """
    for prompt_info, label_name in zip(prompts_with_ids, generated_labels):
        if (
            not label_name
        ):  # Skip if label_name is None (indicating JSON parsing failed or label was not generated)
            continue

        email_id = prompt_info["email_id"]
        matching_label = next(
            (label for label in labels if label.label_name == label_name), None
        )

        if matching_label:
            try:
                # Check if the label already exists in Gmail, otherwise create it
                label_id = create_label(
                    gmail_service, matching_label.label_name, matching_label.color
                )

                # Assign the label to the email
                assign_label_to_email(gmail_service, email_id, label_id)
            except Exception:
                continue


def generate_email_labels(
    prompts: List[str], labels: List[Label]
) -> List[Optional[str]]:
    """
    Generates labels based on prompts with error handling for JSON parsing.
    """
    # Dynamically create an Enum for label names
    LabelsEnum = Enum(
        "LabelsEnum",
        {f"OPTION_{i+1}": labels[i].label_name for i in range(len(labels))},
    )

    class DynamicEmail(BaseModel):
        label: LabelsEnum

    model = Model()
    generated_labels = model.generate.remote(prompts, DynamicEmail)

    labels = []
    for label in generated_labels:
        try:
            parsed_label = json.loads(label).get("label")
            labels.append(parsed_label)
        except json.JSONDecodeError:
            # If JSON parsing fails, append None to indicate failure
            labels.append(None)
    return labels


def read_emails_and_create_prompts(
    service, prompt: str, labels: List[Label]
) -> List[dict]:
    colored_print("yellow", "READING EMAILS")
    emails = read_emails(service, 1)  # only read emails from the past day
    colored_print("green", "READING EMAIL COMPLETE")

    labels_with_descriptions = "- " + "\n- ".join(
        [
            f"{label.label_name.strip()} ({label.description.strip()})"
            for label in labels
        ]
    )

    prompts_with_ids = []

    # generate prompts for 500 recent emails
    for email_data in emails[:500]:
        email_id = email_data["id"]
        email_content = email_data["content"]

        generated_prompt = prompt.format(
            labels_with_descriptions=labels_with_descriptions,
            email_content=email_content,
        )

        # Combine each prompt with its corresponding email ID in a dictionary
        prompts_with_ids.append({"prompt": generated_prompt, "email_id": email_id})

    return prompts_with_ids


@stub.function(
    secrets=[Secret.from_name("supabase"), Secret.from_name("GMAIL_CREDENTIALS")]
)
@web_endpoint(method="POST")
def label_job_webhook(job: LabelJob):
    try:
        colored_print("cyan", "Starting webhook processing...")
        from supabase import create_client, Client

        supabase: Client = create_client(
            os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        )

        # decrypt token for user google oauth2 tokens
        colored_print("yellow", "Decrypting user tokens...")
        token_data = supabase.rpc(
            "decrypt_secret", {"secret_id": job.user.tokens}
        ).execute()
        decrypted_secret = token_data.data[0]
        auth_tokens = json.loads(decrypted_secret.get("decrypted_secret"))

        colored_print("green", "Tokens decrypted successfully.")

        if not auth_tokens:
            colored_print("red", "Decryption failed, secret is None.")
            raise HTTPException(
                status_code=400, detail="Decryption failed, secret is None."
            )

        auth_token = auth_tokens.get("access_token")
        refresh_token = auth_tokens.get("refresh_token")

        gmail_service = gmail_authenticate(auth_token, refresh_token)
        colored_print("green", "Gmail service authenticated.")

        prompts_with_ids = read_emails_and_create_prompts(
            gmail_service, PROD_PROMPT, job.labels
        )
        colored_print(
            "green",
            f"Emails read and prompts created.",
        )

        prompts = [item["prompt"] for item in prompts_with_ids]

        generated_labels = generate_email_labels(prompts, job.labels)
        colored_print("green", "Labels generated from model.")

        # iterate over generated labels and assign them to emails
        assign_labels_to_emails(
            gmail_service, prompts_with_ids, generated_labels, job.labels
        )
        colored_print("green", "Labels assigned to emails successfully.")
        return {"message": "Emails labeled successfully."}
    except Exception as e:
        print(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@stub.local_entrypoint()
def main():
    """
    SET THESE ENVIRONMENT VARIABLES:
      - GOOGLE_ACCESS_TOKEN
      - GOOGLE_REFRESH_TOKEN
      - GOOGLE_CLIENT_ID
      - GOOGLE_CLIENT_SECRET
    """
    auth_token = os.getenv("GOOGLE_ACCESS_TOKEN")
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")

    if not auth_token or not refresh_token:
        raise ValueError("Google access token and refresh token are required.")

    gmail_service = gmail_authenticate(auth_token, refresh_token)

    prompts_with_ids = read_emails_and_create_prompts(
        gmail_service, LOCAL_PROMPT, local_labels
    )
    prompts = [item["prompt"] for item in prompts_with_ids]
    generated_labels = generate_email_labels(prompts, local_labels)

    # iterate over generated labels and assign them to emails
    assign_labels_to_emails(
        gmail_service, prompts_with_ids, generated_labels, local_labels
    )
