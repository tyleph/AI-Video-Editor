import argparse
import requests
import json
import os

# Assuming the FastAPI app is running locally at this URL
BASE_URL = "http://127.0.0.1:8000"

def ask_question_cli(user_id: str, project_id: str, session_id: str = None):
    print(f"Starting VideoChat CLI for User: {user_id}, Project: {project_id}")
    print("Type your questions. Type 'exit' to quit.")

    current_session_id = session_id

    while True:
        question = input("You: ")
        if question.lower() == 'exit':
            break

        payload = {
            "question": question,
            "user_id": user_id,
            "project_id": project_id,
            "session_id": current_session_id
        }

        try:
            response = requests.post(f"{BASE_URL}/videochat/ask", json=payload)
            response.raise_for_status() # Raise an exception for HTTP errors
            response_data = response.json()
            
            print(f"AI: {response_data['response']}")
            current_session_id = response_data['session_id'] # Update session ID for continuity
            print(f"(Session ID: {current_session_id})")

        except requests.exceptions.RequestException as e:
            print(f"Error communicating with the backend: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                print(f"Response body: {e.response.text}")
        except json.JSONDecodeError:
            print("Error: Could not decode JSON response from the server.")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

def main():
    parser = argparse.ArgumentParser(description="VideoChat CLI tester for AI Video Editor Backend.")
    parser.add_argument("--user-id", required=True, help="The user ID for the chat session.")
    parser.add_argument("--project-id", required=True, help="The project ID for the chat session.")
    parser.add_argument("--session-id", help="Optional existing session ID to continue a chat.")
    args = parser.parse_args()

    ask_question_cli(args.user_id, args.project_id, args.session_id)

if __name__ == "__main__":
    main()
