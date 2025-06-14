# utils/get_onedrive_token.py

import webbrowser
import os
import http.server
import socketserver
import threading
import requests  # We will use requests for the final step
from urllib.parse import urlparse, parse_qs, urlencode

# --- CONFIGURATION ---
# IMPORTANT: Paste the credentials you got from the Azure Portal here.
CLIENT_ID = "8c3622f8-3c7c-41dc-a8c1-e608c17ada52"
CLIENT_SECRET = "okk8Q~JxuHIYwDhnYP1sEdmo3eThJt8R_syzwcdu"

# This should match the Redirect URI in your Azure App Registration
PORT = 8000
REDIRECT_URI = f"http://localhost:{PORT}"

AUTHORITY = "https://login.microsoftonline.com/consumers"
SCOPES = ["Files.ReadWrite.AppFolder", "offline_access"]

# This global variable will store the authorization code
auth_code = None
auth_code_received = threading.Event()

class AuthCodeHandler(http.server.BaseHTTPRequestHandler):
    """A simple handler to catch the OAuth redirect and grab the auth code."""
    def do_GET(self):
        global auth_code
        query_components = parse_qs(urlparse(self.path).query)
        
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        
        if "code" in query_components:
            auth_code = query_components["code"][0]
            self.wfile.write(b"<h1>Authentication Successful!</h1>")
            self.wfile.write(b"<p>You can now close this browser tab and return to your terminal.</p>")
        else:
            self.wfile.write(b"<h1>Authentication Failed</h1>")
            self.wfile.write(b"<p>No authorization code was received. Please try running the script again.</p>")
        
        auth_code_received.set()

def start_server():
    """Starts the local web server in a background thread."""
    handler = AuthCodeHandler
    httpd = socketserver.TCPServer(("", PORT), handler)
    server_thread = threading.Thread(target=httpd.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    print(f"Temporary server started on http://localhost:{PORT}")
    return httpd

def main():
    httpd = start_server()

    # Step 1: Manually construct the authorization URL to get the user's consent and a code.
    auth_endpoint = f"{AUTHORITY}/oauth2/v2.0/authorize"
    params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': ' '.join(SCOPES),
        'response_mode': 'query'
    }
    auth_url = f"{auth_endpoint}?{urlencode(params)}"

    print("\nYour browser will now open for you to log in and grant permissions.")
    print("If it doesn't, please open this URL manually:")
    print(f"\n{auth_url}\n")
    webbrowser.open(auth_url)

    print("Waiting for you to complete the login process in your browser...")
    auth_code_received.wait()

    httpd.shutdown()
    print("Temporary server shut down.")

    # Step 2: Manually exchange the authorization code for a refresh token.
    if auth_code:
        print("\nAuthorization code received. Exchanging it for tokens...")
        
        token_endpoint = f"{AUTHORITY}/oauth2/v2.0/token"
        
        token_data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'scope': ' '.join(SCOPES),
            'code': auth_code,
            'redirect_uri': REDIRECT_URI,
            'grant_type': 'authorization_code'
        }
        
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        
        response = requests.post(token_endpoint, data=token_data, headers=headers)
        result = response.json()

    else:
        result = {"error": "No auth code", "error_description": "The local server did not receive an authorization code."}

    # Step 3: Process the final result.
    if "access_token" in result and "refresh_token" in result:
        print("\n" + "="*50)
        print("✅✅✅ Authentication Successful! ✅✅✅")
        print("-" * 50)
        print("Your REFRESH TOKEN is below. This is the one.")
        print("Copy this entire value and save it as a secret in Render.")
        print("-" * 50)
        print(f"\n{result['refresh_token']}\n")
    else:
        print("\n" + "="*50)
        print("❌ Authentication Failed at the final step.")
        print(f"Error: {result.get('error')}")
        print(f"Description: {result.get('error_description')}")
        print("Full Error Response:", result)
        print("="*50)

if __name__ == "__main__":
    main()