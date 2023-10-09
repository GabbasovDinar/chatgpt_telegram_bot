import openai


class OpenAIAgent:
    def __init__(self, api_key, settings=None):
        openai.api_key = api_key
        self.settings = settings or {
            "model": "gpt-3.5-turbo",
            "temperature": 0.8,
            "max_tokens": 300,
            "stop": ["assistant", "user"],
        }

    def process_message(self, conversation_context) -> str:
        # Retrieve AI's response from OpenAI API
        response = self.get_ai_response(conversation_context)
        # Return AI's response
        return response

    def get_ai_response(self, conversation: list) -> str:
        try:
            # Generate AI's response using OpenAI API
            response = openai.ChatCompletion.create(
                messages=conversation, **self.settings
            )
            # Extract AI's response from the API response
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error while getting response from OpenAI: {e}")
            return "Sorry, I'm having some trouble right now. Please try again later."
