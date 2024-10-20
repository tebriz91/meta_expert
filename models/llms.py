import json
import logging
import os
import time
from typing import Any, Dict, List

import requests
from langsmith import Client
from langsmith.run_helpers import traceable
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from utils.logging import setup_logging

setup_logging(level=logging.INFO)
logger = logging.getLogger(__name__)
client = Client()


class BaseModel:
    """
    Base class for all language models.
    Provides common functionality for invoking models and handling retries.
    """

    def __init__(
        self,
        temperature: float,
        model: str,
        json_response: bool,
        prompt_caching: bool = False,
        max_retries: int = 3,
        retry_delay: int = 1,
    ):
        """
        Initialize the BaseModel with common parameters.

        :param temperature: Controls randomness in model outputs
        :param model: The name of the language model to use
        :param json_response: Whether the model should return JSON responses
        :param prompt_caching: Whether to use prompt caching
        :param max_retries: Maximum number of retries for requests
        :param retry_delay: Delay between retries in seconds
        """
        self.temperature = temperature
        self.model = model
        self.json_response = json_response
        self.prompt_caching = prompt_caching
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def _make_request(self, url, headers, payload):
        """
        Make a POST request to the specified URL with retries.

        :param url: The URL to send the request to
        :param headers: The headers to include in the request
        :param payload: The payload to include in the request
        :return: The JSON response from the server
        """
        response = requests.post(url, headers=headers, json=payload)
        try:
            response.raise_for_status()
        except requests.HTTPError as http_err:
            error_content = response.content.decode("utf-8")
            print(f"HTTP error occurred: {http_err}\nResponse content: {error_content}")
            raise
        return response.json()

    def invoke(
        self, messages: List[Dict[str, str]], guided_json: Dict[str, Any] = None
    ) -> str:
        """
        Abstract method to invoke the model's main functionality.

        :param messages: The messages to send to the model
        :param guided_json: Optional guided JSON schema for the model
        :return: The model's response as a string
        """
        pass


class MistralModel(BaseModel):
    """
    Mistral language model class.
    """

    def __init__(
        self,
        temperature: float,
        model: str,
        json_response: bool,
        max_retries: int = 3,
        retry_delay: int = 1,
    ):
        """
        Initialize the MistralModel with specific parameters.

        :param temperature: Controls randomness in model outputs
        :param model: The name of the language model to use
        :param json_response: Whether the model should return JSON responses
        :param max_retries: Maximum number of retries for requests
        :param retry_delay: Delay between retries in seconds
        """
        super().__init__(temperature, model, json_response, max_retries, retry_delay)
        self.api_key = os.getenv("MISTRAL_API_KEY")
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        self.model_endpoint = "https://api.mistral.ai/v1/chat/completions"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def _make_request(self, url, headers, payload):
        """
        Make a POST request to the specified URL with retries.

        :param url: The URL to send the request to
        :param headers: The headers to include in the request
        :param payload: The payload to include in the request
        :return: The JSON response from the server
        """
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        return response.json()

    def invoke(
        self, messages: List[Dict[str, str]], guided_json: Dict[str, Any] = None
    ) -> str:
        """
        Invoke the Mistral model with the provided messages.

        :param messages: The messages to send to the model
        :param guided_json: Optional guided JSON schema for the model
        :return: The model's response as a string
        """
        system = messages[0]["content"]
        user = messages[1]["content"]

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
        }

        if self.json_response:
            payload["response_format"] = {"type": "json_object"}

        try:
            request_response_json = self._make_request(
                self.model_endpoint, self.headers, payload
            )

            if (
                "choices" not in request_response_json
                or len(request_response_json["choices"]) == 0
            ):
                raise ValueError("No choices in response")

            response_content = request_response_json["choices"][0]["message"]["content"]

            if self.json_response:
                response = json.dumps(json.loads(response_content))
            else:
                response = response_content

            return response
        except requests.RequestException as e:
            return json.dumps({
                "error": f"Error in invoking model after {self.max_retries} retries: {str(e)}"
            })
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            return json.dumps({"error": f"Error processing response: {str(e)}"})


class ClaudeModel(BaseModel):
    """
    Claude language model class.
    """

    def __init__(
        self,
        temperature: float,
        model: str,
        json_response: bool,
        prompt_caching: bool = False,
        max_retries: int = 3,
        retry_delay: int = 1,
    ):
        """
        Initialize the ClaudeModel with specific parameters.

        :param temperature: Controls randomness in model outputs
        :param model: The name of the language model to use
        :param json_response: Whether the model should return JSON responses
        :param prompt_caching: Whether to use prompt caching
        :param max_retries: Maximum number of retries for requests
        :param retry_delay: Delay between retries in seconds
        """
        super().__init__(
            temperature, model, json_response, prompt_caching, max_retries, retry_delay
        )
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        self.model_endpoint = "https://api.anthropic.com/v1/messages"

    @traceable(
        run_type="llm",
        metadata={
            "ls_provider": "anthropic",
            "ls_model_name": "claude-3-5-sonnet-20240620",
        },
    )
    def invoke(
        self, messages: List[Dict[str, str]], guided_json: Dict[str, Any] = None
    ) -> str:
        """
        Invoke the Claude model with the provided messages.

        :param messages: The messages to send to the model
        :param guided_json: Optional guided JSON schema for the model
        :return: The model's response as a string
        """
        # Extract system message if present
        system = next(
            (msg["content"] for msg in messages if msg["role"] == "system"), None
        )

        # Prepare messages for the API
        api_messages = []
        for msg in messages:
            if msg["role"] != "system":
                content = msg["content"]
                if self.json_response and msg["role"] == "user":
                    content += " Your output must be JSON formatted. Just return the specified JSON format, do not prepend your response with anything."
                api_messages.append({"role": msg["role"], "content": content})

        # Prepare payload
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": self.temperature,
            "messages": api_messages,
        }

        # Add system message and handle prompt caching if enabled
        if self.prompt_caching:
            self.headers["anthropic-beta"] = "prompt-caching-2024-07-31"
            if system:
                payload["system"] = [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
        elif system:
            payload["system"] = system

        try:
            request_response_json = self._make_request(
                self.model_endpoint, self.headers, payload
            )

            if (
                "content" not in request_response_json
                or not request_response_json["content"]
            ):
                raise ValueError("No content in response")

            response_content = request_response_json["content"][0]["text"]

            if self.json_response:
                response = json.dumps(json.loads(response_content))
            else:
                response = response_content

            return response
        except requests.RequestException as e:
            return json.dumps({
                "error": f"Error in invoking model after {self.max_retries} retries: {str(e)}"
            })
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            return json.dumps({"error": f"Error processing response: {str(e)}"})


class GeminiModel(BaseModel):
    """
    Gemini language model class.
    """

    def __init__(
        self,
        temperature: float,
        model: str,
        json_response: bool,
        max_retries: int = 3,
        retry_delay: int = 1,
    ):
        """
        Initialize the GeminiModel with specific parameters.

        :param temperature: Controls randomness in model outputs
        :param model: The name of the language model to use
        :param json_response: Whether the model should return JSON responses
        :param max_retries: Maximum number of retries for requests
        :param retry_delay: Delay between retries in seconds
        """
        super().__init__(temperature, model, json_response, max_retries, retry_delay)
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.headers = {"Content-Type": "application/json"}
        self.model_endpoint = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={self.api_key}"

    def invoke(
        self, messages: List[Dict[str, str]], guided_json: Dict[str, Any] = None
    ) -> str:
        """
        Invoke the Gemini model with the provided messages.

        :param messages: The messages to send to the model
        :param guided_json: Optional guided JSON schema for the model
        :return: The model's response as a string
        """
        system = messages[0]["content"]
        user = messages[1]["content"]

        content = f"system:{system}\n\nuser:{user}"
        if self.json_response:
            content += ". Your output must be JSON formatted. Just return the specified JSON format, do not prepend your response with anything."

        payload = {
            "contents": [{"parts": [{"text": content}]}],
            "generationConfig": {"temperature": self.temperature},
        }

        if self.json_response:
            payload = {
                "contents": [{"parts": [{"text": content}]}],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "temperature": self.temperature,
                },
            }

        try:
            request_response_json = self._make_request(
                self.model_endpoint, self.headers, payload
            )

            if (
                "candidates" not in request_response_json
                or not request_response_json["candidates"]
            ):
                raise ValueError("No content in response")

            response_content = request_response_json["candidates"][0]["content"][
                "parts"
            ][0]["text"]

            if self.json_response:
                response = json.dumps(json.loads(response_content))
            else:
                response = response_content

            return response
        except requests.RequestException as e:
            return json.dumps({
                "error": f"Error in invoking model after {self.max_retries} retries: {str(e)}"
            })
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            return json.dumps({"error": f"Error processing response: {str(e)}"})


class GroqModel(BaseModel):
    """
    Groq language model class.
    """

    def __init__(
        self,
        temperature: float,
        model: str,
        json_response: bool,
        max_retries: int = 3,
        retry_delay: int = 1,
    ):
        """
        Initialize the GroqModel with specific parameters.

        :param temperature: Controls randomness in model outputs
        :param model: The name of the language model to use
        :param json_response: Whether the model should return JSON responses
        :param max_retries: Maximum number of retries for requests
        :param retry_delay: Delay between retries in seconds
        """
        super().__init__(temperature, model, json_response, max_retries, retry_delay)
        self.api_key = os.getenv("GROQ_API_KEY")
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        self.model_endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def invoke(
        self, messages: List[Dict[str, str]], guided_json: Dict[str, Any] = None
    ) -> str:
        """
        Invoke the Groq model with the provided messages.

        :param messages: The messages to send to the model
        :param guided_json: Optional guided JSON schema for the model
        :return: The model's response as a string
        """
        system = messages[0]["content"]
        user = messages[1]["content"]

        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": f"system:{system}\n\n user:{user}"}
            ],
            "temperature": self.temperature,
        }

        time.sleep(10)

        if self.json_response:
            payload["response_format"] = {"type": "json_object"}

        try:
            request_response_json = self._make_request(
                self.model_endpoint, self.headers, payload
            )

            if (
                "choices" not in request_response_json
                or len(request_response_json["choices"]) == 0
            ):
                raise ValueError("No choices in response")

            response_content = request_response_json["choices"][0]["message"]["content"]

            if self.json_response:
                response = json.dumps(json.loads(response_content))
            else:
                response = response_content

            return response
        except requests.RequestException as e:
            return json.dumps({
                "error": f"Error in invoking model after {self.max_retries} retries: {str(e)}"
            })
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            return json.dumps({"error": f"Error processing response: {str(e)}"})


class OllamaModel(BaseModel):
    """
    Ollama language model class.
    """

    def __init__(
        self,
        temperature: float,
        model: str,
        json_response: bool,
        max_retries: int = 3,
        retry_delay: int = 1,
    ):
        """
        Initialize the OllamaModel with specific parameters.

        :param temperature: Controls randomness in model outputs
        :param model: The name of the language model to use
        :param json_response: Whether the model should return JSON responses
        :param max_retries: Maximum number of retries for requests
        :param retry_delay: Delay between retries in seconds
        """
        super().__init__(temperature, model, json_response, max_retries, retry_delay)
        self.headers = {"Content-Type": "application/json"}
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model_endpoint = f"{self.ollama_host}/api/generate"

    def _check_and_pull_model(self):
        """
        Check if the model exists and pull it if necessary.
        """
        response = requests.get(f"{self.ollama_host}/api/tags")
        if response.status_code == 200:
            models = response.json().get("models", [])
            if not any(model["name"] == self.model for model in models):
                print(f"Model {self.model} not found. Pulling the model...")
                self._pull_model()
            else:
                print(f"Model {self.model} is already available.")
        else:
            print(f"Failed to check models. Status code: {response.status_code}")

    def _pull_model(self):
        """
        Pull the model from the server.
        """
        pull_endpoint = f"{self.ollama_host}/api/pull"
        payload = {"name": self.model}
        response = requests.post(pull_endpoint, json=payload, stream=True)

        if response.status_code == 200:
            for line in response.iter_lines():
                if line:
                    status = json.loads(line.decode("utf-8"))
                    print(f"Pulling model: {status.get('status')}")
            print(f"Model {self.model} pulled successfully.")
        else:
            print(f"Failed to pull model. Status code: {response.status_code}")

    def invoke(
        self, messages: List[Dict[str, str]], guided_json: Dict[str, Any] = None
    ) -> str:
        """
        Invoke the Ollama model with the provided messages.

        :param messages: The messages to send to the model
        :param guided_json: Optional guided JSON schema for the model
        :return: The model's response as a string
        """
        self._check_and_pull_model()  # Check and pull the model if necessary

        system = messages[0]["content"]
        user = messages[1]["content"]

        payload = {
            "model": self.model,
            "prompt": user,
            "system": system,
            "stream": False,
            "temperature": self.temperature,
        }

        if self.json_response:
            payload["format"] = "json"

        try:
            request_response_json = self._make_request(
                self.model_endpoint, self.headers, payload
            )

            if self.json_response:
                response = json.dumps(json.loads(request_response_json["response"]))
            else:
                response = str(request_response_json["response"])

            return response
        except requests.RequestException as e:
            return json.dumps({
                "error": f"Error in invoking model after {self.max_retries} retries: {str(e)}"
            })
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Error processing response: {str(e)}"})


class VllmModel(BaseModel):
    """
    Vllm language model class.
    """

    def __init__(
        self,
        temperature: float,
        model: str,
        model_endpoint: str,
        json_response: bool,
        stop: str = None,
        max_retries: int = 5,
        retry_delay: int = 1,
    ):
        """
        Initialize the VllmModel with specific parameters.

        :param temperature: Controls randomness in model outputs
        :param model: The name of the language model to use
        :param model_endpoint: Specific endpoint for the model API
        :param json_response: Whether the model should return JSON responses
        :param stop: Stop sequence for model generation
        :param max_retries: Maximum number of retries for requests
        :param retry_delay: Delay between retries in seconds
        """
        super().__init__(temperature, model, json_response, max_retries, retry_delay)
        self.headers = {"Content-Type": "application/json"}
        self.model_endpoint = model_endpoint + "v1/chat/completions"
        self.stop = stop

    def invoke(
        self, messages: List[Dict[str, str]], guided_json: Dict[str, Any] = None
    ) -> str:
        """
        Invoke the Vllm model with the provided messages.

        :param messages: The messages to send to the model
        :param guided_json: Optional guided JSON schema for the model
        :return: The model's response as a string
        """
        system = messages[0]["content"]
        user = messages[1]["content"]

        prefix = self.model.split("/")[0]

        if prefix == "mistralai":
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": f"system:{system}\n\n user:{user}"}
                ],
                "temperature": self.temperature,
                "stop": None,
            }
        else:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": self.temperature,
                "stop": self.stop,
            }

        if self.json_response:
            payload["response_format"] = {"type": "json_object"}
            payload["guided_json"] = guided_json

        try:
            request_response_json = self._make_request(
                self.model_endpoint, self.headers, payload
            )
            response_content = request_response_json["choices"][0]["message"]["content"]

            if self.json_response:
                response = json.dumps(json.loads(response_content))
            else:
                response = str(response_content)

            return response
        except requests.RequestException as e:
            return json.dumps({
                "error": f"Error in invoking model after {self.max_retries} retries: {str(e)}"
            })
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Error processing response: {str(e)}"})


class OpenAIModel(BaseModel):
    """
    OpenAI language model class.
    """

    def __init__(
        self,
        temperature: float,
        model: str,
        json_response: bool,
        max_retries: int = 3,
        retry_delay: int = 1,
    ):
        """
        Initialize the OpenAIModel with specific parameters.

        :param temperature: Controls randomness in model outputs
        :param model: The name of the language model to use
        :param json_response: Whether the model should return JSON responses
        :param max_retries: Maximum number of retries for requests
        :param retry_delay: Delay between retries in seconds
        """
        super().__init__(temperature, model, json_response, max_retries, retry_delay)
        self.model_endpoint = "https://api.openai.com/v1/chat/completions"
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    @traceable(
        run_type="llm", metadata={"ls_provider": "openai", "ls_model_name": "gpt-4o"}
    )
    def invoke(
        self, messages: List[Dict[str, str]], guided_json: Dict[str, Any] = None
    ) -> str:
        """
        Invoke the OpenAI model with the provided messages.

        :param messages: The messages to send to the model
        :param guided_json: Optional guided JSON schema for the model
        :return: The model's response as a string
        """
        # Extract system message if present
        system = next(
            (msg["content"] for msg in messages if msg["role"] == "system"), None
        )

        # Prepare messages for the API
        api_messages = []
        for msg in messages:
            if msg["role"] != "system":
                content = msg["content"]
                if self.json_response and msg["role"] == "user":
                    content += "\nYou must respond in JSON format."
                api_messages.append({"role": msg["role"], "content": content})

        # Prepare payload with the same structure
        if self.model == "o1-preview" or self.model == "o1-mini":
            # Special handling for o1 models
            if system:
                combined_content = f"{system}\n\n{api_messages[0]['content']}"
            else:
                combined_content = api_messages[0]["content"]
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": combined_content}],
            }
        else:
            payload = {
                "model": self.model,
                "messages": [],
                "temperature": self.temperature,
                "stream": False,
            }
            if system:
                payload["messages"].append({"role": "system", "content": system})
            payload["messages"].extend(api_messages)

        if self.json_response:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "open_ai_agent",
                    "strict": True,
                    "schema": guided_json,
                },
            }

        # print(f"DEBUG PAYLOAD: {payload}")

        try:
            response_json = self._make_request(
                self.model_endpoint, self.headers, payload
            )

            if self.json_response:
                response = json.dumps(
                    json.loads(response_json["choices"][0]["message"]["content"])
                )
            else:
                response = response_json["choices"][0]["message"]["content"]

            return response
        except requests.RequestException as e:
            return json.dumps({
                "error": f"Error in invoking model after {self.max_retries} retries: {str(e)}"
            })
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Error processing response: {str(e)}"})


if __name__ == "__main__":
    from langsmith.run_helpers import traceable

    @traceable(run_type="llm")
    def test_function():
        """
        Test function to demonstrate tracing.
        """
        return "This is a test."

    result = test_function()
    print(result)
