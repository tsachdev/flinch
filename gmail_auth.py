from google_auth_oauthlib.flow import InstalledAppFlow
from pathlib import Path

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose',
]

def main():
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)
    Path("token.json").write_text(creds.to_json())
    print("token.json saved")

if __name__ == "__main__":
    main()
