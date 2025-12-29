# Ghighi Quotes (Streamlit)

This app lets friends post personal "sports-like" quotes for real-life events and tracks implied probabilities over time.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Data is stored in `data/quotes.csv` by default.

## Connect to Google Sheets (for Streamlit Cloud)

Create a Google Sheet with a worksheet named `quotes` and a header row matching:

```
timestamp_utc,date,player,event,quote,implied_probability
```

Add secrets in Streamlit Cloud:

```toml
GSHEETS_DOC_ID = "your_sheet_id"
GSHEETS_WORKSHEET = "quotes"

GSPREAD_SERVICE_ACCOUNT = """
{
  "type": "service_account",
  "project_id": "...",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "...",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "..."
}
"""
```

Share the sheet with the `client_email` from the service account.
