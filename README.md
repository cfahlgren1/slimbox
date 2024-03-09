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
BASE_URL=
SUPABASE_KEY=
SUPABASE_URL=
REDIS_HOST=redis
REDIS_PORT=6379
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```