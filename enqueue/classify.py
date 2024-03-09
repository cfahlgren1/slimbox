import os
import re
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, constr
from typing import List, Optional
from instructor import patch, Mode

base_url = os.getenv(
    "BASE_URL"
)  # use vLLM / Ollama compatible API endpoint with OSS model

aclient = patch(
    AsyncOpenAI(api_key="N/A", base_url=base_url),
    mode=Mode.JSON,
)


class Label(BaseModel):
    name: str
    description: Optional[str]
    color: str


def create_dynamic_label_model(valid_labels: List[str]):
    pattern = f"^({'|'.join(re.escape(label) for label in valid_labels)})$"

    class DynamicLabelModel(BaseModel):
        category: constr(pattern=pattern)
        confidence: float = Field(ge=0, le=1)

    return DynamicLabelModel


async def classify_email(content: str, label_descriptions: List[Label]) -> str:
    try:
        if not any(label.name == "other" for label in label_descriptions):
            label_descriptions.append(
                Label(
                    name="other",
                    description="If the email doesn't fit any of the other categories with high confidence.",
                    color="default",
                )
            )

        label_options_message = (
            "Only choose one of these categories for the email:\n\n"
            + "\n".join(
                [
                    f"- {label.name} ({label.description})"
                    for label in label_descriptions
                ]
            )
        )

        label_names = [label.name for label in label_descriptions]

        task = await aclient.chat.completions.create(
            model="solidrust/Nous-Hermes-2-Mistral-7B-DPO-AWQ",
            response_model=create_dynamic_label_model(label_names),
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": f"You are an email assistant that categorizes emails.",
                },
                {
                    "role": "user",
                    "content": f"{label_options_message}\n\nLabel the following email: `{content}`",
                },
            ],
        )

        return task.category

    except Exception as e:
        return "other"
