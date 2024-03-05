<div align="center">
    <img src="https://app.slimbox.ai/storage/v1/object/public/assets/slimbox-header.png" alt="SlimBox Header">
</div>

<div align="center">
  <a href="https://slimbox.ai">
    <h1 align="center">SlimBox</h1>
  </a>
  <p align="center">
    Privacy-focused, open source, email app for labeling and categorizing emails with a large language model.
  </p>
</div>


### Features
- Label gmail emails dynamically with any open source LLM

### Built With
- [Modal Labs](https://modal.com/) - Serverless Cloud Compute
- [vLLM](https://github.com/vllm-project/vllm) - Batched / Fast Inference
- [OpenHermes-2.5-16k](https://huggingface.co/NurtureAI/OpenHermes-2.5-Mistral-7B-16k) - OpenHermes-2.5 extended to 16k context
- [Outlines](https://outlines-dev.github.io/outlines/) - Structured Output

# Getting Started

#### Step 1: Get Google OAuth 2.0 Credentials

You need to enable these scopes in the Google Cloud Console:
```
https://www.googleapis.com/auth/gmail.modify
```

*The Credentials you need will look like this:*

```json
{
  "token": "",
  "refresh_token": "",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "*.apps.googleusercontent.com",
  "client_secret": "",
  "scopes": [
    "https://www.googleapis.com/auth/gmail.modify"
  ],
  "expiry": ""
}
```
_The modify scope is needed for creating the labels and adding labels to an email._

#### Step 2: Set Modal Environment Variables

You will need to set up these environment variables in Modal:

- `GMAIL_CREDENTIALS` - the auth credentials we retrieved from Google Console above
```
GOOGLE_ACCESS_TOKEN
GOOGLE_REFRESH_TOKEN
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
```

- `HF_TOKEN` - Your HuggingFace token to download the LLM, name it `my-huggingface-secret` in Modal

_Here is a [guide](https://modal.com/docs/guide/secrets) for Modal Secrets._

#### Step 3: Install Requirements

```python
pip3 install -r requirements.txt
```

#### Step 4: Label 🥳

```bash
modal run label_emails.py
```

## Adjusting Labels & Descriptions
You can adjust the labels and descriptions. The LLM will use this when
deciding how to label the email.

```json
{
    "label_name": "work",
    "description": "Includes all work-related correspondence, meeting invites, and project updates.",
    "color": "#4a86e8",
},
{
    "label_name": "personal",
    "description": "Personal emails from friends and family or personal interests subscriptions.",
    "color": "#f691b3",
}
```
**TIP: It is best to have a catch all label like: `Other` for emails that don't fit the main categories since the LLM has to choose a label for every email.**