import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Define the scopes your application needs (e.g., Drive read-only)
# Change this to match the exact API scopes you are using!
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main():
    creds = None

    # 1. The script looks for token.json (which you deleted, so it skips this)
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # 2. If there are no valid credentials, make the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # This opens the browser window using your credentials.json file
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        # 3. Save the brand-new, healthy credentials back to token.json
        with open("token.json", "w") as token:
            token.write(creds.to_json())
            print("\nSUCCESS: Brand new token.json has been created!")


if __name__ == "__main__":
    main()
