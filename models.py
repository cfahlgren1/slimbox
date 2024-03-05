from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum

# colors must be one of the valid hex colors here
# https://developers.google.com/gmail/api/reference/rest/v1/users.labels#color
example_local_labels = [
    {
        "label_name": "work",
        "description": "Includes all work-related correspondence, meeting invites, and project updates.",
        "color": "#4a86e8",
    },
    {
        "label_name": "personal",
        "description": "Personal emails from friends and family or personal interests subscriptions.",
        "color": "#f691b3",
    },
    {
        "label_name": "spam",
        "description": "Unsolicited emails, including bulk advertisements and potentially harmful or phishing emails.",
        "color": "#e66550",
    },
    {
        "label_name": "social",
        "description": "Notifications from social media platforms, including friend requests, tags, and direct messages.",
        "color": "#6d9eeb",
    },
    {
        "label_name": "promotional",
        "description": "Emails related to sales, special offers, newsletters, and marketing campaigns. Most things with lots of links and an unsubscribe link are promotional.",
        "color": "#ffad47",
    },
    {
        "label_name": "financial",
        "description": "Bank statements, bills, investment alerts, and other financial-related notifications.",
        "color": "#f2c960",
    },
    {
        "label_name": "Other",
        "description": "Other emails that do not fit into the other categories.",
    },
]


class Label(BaseModel):
    label_name: str = Field(..., alias="label_name")
    description: Optional[str] = Field(None, alias="description")
    color: Optional[str] = Field(None, alias="color")


class User(BaseModel):
    fullName: str
    id: str
    tokens: str


class LabelJob(BaseModel):
    labels: List[Label]
    user: User


local_labels = [Label(**label) for label in example_local_labels]
