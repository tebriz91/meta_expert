import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, TypeVar

from langchain_core.documents.base import Document
from langsmith import traceable
from termcolor import colored

from agents.agent_registry import AgentRegistry
from models.llms import (
    ClaudeModel,
    GeminiModel,
    GroqModel,
    MistralModel,
    OllamaModel,
    OpenAIModel,
    VllmModel,
)

StateT = TypeVar("StateT", bound=Dict[str, Any])


class BaseAgent(ABC, Generic[StateT]):
    """
    Abstract base class for all agents in the system.
    Provides common functionality and interface for agent implementations.
    """

    def __init__(
        self,
        name: str,
        model: str = None,
        server: str = None,
        temperature: float = 0,
        model_endpoint: str = None,
        stop: str = None,
    ) -> None:
        """
        Initialize the BaseAgent with common parameters.

        :param name: The name to register the agent
        :param model: The name of the language model to use
        :param server: The server hosting the language model
        :param temperature: Controls randomness in model outputs
        :param model_endpoint: Specific endpoint for the model API
        :param stop: Stop sequence for model generation
        """
        self.name = name  # Store the initialized name
        self.model = model
        self.server = server
        self.temperature = temperature
        self.model_endpoint = model_endpoint
        self.stop = stop
        self.llm = self.get_llm()
        # self.register()

    def get_llm(
        self, json_response: bool = False, prompt_caching: bool = True
    ) -> (
        OpenAIModel
        | ClaudeModel
        | MistralModel
        | OllamaModel
        | GroqModel
        | GeminiModel
        | VllmModel
    ):
        """
        Factory method to create and return the appropriate
        language model instance.
        :param json_response: Whether the model should return JSON responses
        :param prompt_caching: Whether to use prompt caching
        :return: An instance of the appropriate language model
        """
        if self.server == "openai":
            return OpenAIModel(
                temperature=self.temperature,
                model=self.model,
                json_response=json_response,
            )
        elif self.server == "anthropic":
            return ClaudeModel(
                temperature=self.temperature,
                model=self.model,
                json_response=json_response,
                prompt_caching=prompt_caching,
            )
        elif self.server == "mistral":
            return MistralModel(
                temperature=self.temperature,
                model=self.model,
                json_response=json_response,
            )
        elif self.server == "ollama":
            return OllamaModel(
                temperature=self.temperature,
                model=self.model,
                json_response=json_response,
            )
        elif self.server == "groq":
            return GroqModel(
                temperature=self.temperature,
                model=self.model,
                json_response=json_response,
            )
        elif self.server == "gemini":
            return GeminiModel(
                temperature=self.temperature,
                model=self.model,
                json_response=json_response,
            )
        elif self.server == "vllm":
            return VllmModel(
                temperature=self.temperature,
                model=self.model,
                model_endpoint=self.model_endpoint,
                json_response=json_response,
                stop=self.stop,
            )
        else:
            raise ValueError(f"Unsupported server type: {self.server}")

    def register(self, state: StateT) -> None:
        """
        Register the agent in the AgentRegistry using its initialized name.
        Stores the agent's docstring in the AgentRegistry.
        """
        # Extract the docstring from the child class
        agent_docstring = self.__class__.__doc__
        if agent_docstring:
            agent_description = agent_docstring.strip()
        else:
            agent_description = "No description provided."

        # Store the agent's description in the AgentRegistry
        if self.name != "meta_agent":
            AgentRegistry[self.name] = agent_description
            print(f"Agent '{self.name}' registered in AgentRegistry.")

        state[self.name] = []

    def write_to_state(self, state: StateT, response: Any) -> None:
        """
        Write the agent's response to the state under its registered name.

        :param state: The state dictionary to write to.
        :param response: The response to be written to the state.
        """
        response_document = Document(
            page_content=response, metadata={"agent": self.name}
        )

        # Ensure state[self.name] is always a list
        if self.name not in state or not isinstance(state[self.name], list):
            state[self.name] = []

        state[self.name].append(response_document)
        print(f"Agent '{self.name}' wrote to state.")

    def read_instructions(self, state: StateT) -> str:
        """
        Read instructions from the 'meta_agent' in the state.

        :param state: The current state of the agent.
        :return: Instructions as a string.
        """
        try:
            meta_agent_response = state.get("meta_agent", [])[-1].page_content
            meta_agent_response_json = json.loads(meta_agent_response)
            instructions = meta_agent_response_json.get("step_4", {}).get(
                "final_draft", ""
            )
            print(
                colored(
                    text=(
                        f"\n\n{self.name} read instructions from meta_agent: "
                        f"{instructions}\n\n"
                    ),
                    color="green",
                )
            )
        except Exception as e:
            print(f"You must have a meta_agent in your workflow: {e}")
            return ""
        return instructions

    @abstractmethod
    def invoke(self, state: StateT) -> Dict[str, Any]:
        """
        Abstract method to invoke the agent's main functionality.

        :param state: The current state of the agent.
        :return: A dictionary of outputs.
        """
        pass


class ToolCallingAgent(BaseAgent[StateT]):
    """
    An agent capable of calling external tools based on instructions.
    """

    @abstractmethod
    def get_guided_json(self, state: StateT) -> Dict[str, Any]:
        """
        Abstract method to get guided JSON for tool calling.

        :param state: The current state of the agent.
        :return: A dictionary representing the guided JSON.
        """
        pass

    def call_tool(
        self, instructions: str, guided_json: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call an external tool based on instructions and guided JSON.

        :param instructions: Instructions for the tool.
        :param guided_json: Guided JSON for structuring the tool call.
        :return: The response from the LLM as a JSON string.
        """
        guided_json_str = (
            json.dumps(guided_json)
            .encode(encoding="unicode_escape")
            .decode(encoding="utf-8")
        )

        messages = [
            {
                "role": "system",
                "content": f"Take the following instructions and return the specified JSON: {guided_json_str}.",  # noqa: E501
            },
        ] + [{"role": "user", "content": instructions}]

        json_llm = self.get_llm(json_response=True)
        response = json_llm.invoke(messages, guided_json=guided_json)
        return response

    @abstractmethod
    def execute_tool(
        self,
        tool_response: Dict[str, Any],
        state: StateT,
    ) -> StateT:
        """
        Abstract method to execute a tool based on its response.

        :param tool_response: The response from the called tool.
        :param state: The current state of the agent.
        :return: Updated state after tool execution.
        """
        pass

    def invoke(self, state: StateT) -> Dict[str, Any]:
        """
        Invoke the agent's main functionality.
        """
        # Read instructions from the state
        instructions = self.read_instructions(state=state)
        if not instructions:
            print(f"No instructions provided to {self.name}.")
            return {}

        # Get guided JSON schema for tool calling
        guided_json = self.get_guided_json(state=state)

        # Call the external tool and get the response
        tool_response_str = self.call_tool(
            instructions=instructions, guided_json=guided_json
        )

        # Parse the JSON string returned by LLM into a dictionary
        try:
            tool_response = json.loads(tool_response_str)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response from LLM: {e}")
            raise ValueError("Invalid JSON response from LLM.") from e

        # Execute the tool and get the results
        result = self.execute_tool(tool_response=tool_response, state=state)

        # Write the results to the state
        self.write_to_state(state=state, response=result)
        print(f"{self.name} wrote results to state.")

        # Return the output
        return state


class MetaAgent(BaseAgent[StateT]):
    """
    An agent that generates responses based on instructions and state.
    """

    def read_instructions(self, state: StateT) -> str:
        """
        Read instructions from the 'meta_prompt.md' file
        in the 'prompt_engineering' folder.

        :param state: The current state of the agent.
        :return: Instructions as a string.
        """
        # Construct the path to the meta_prompt.md file
        prompt_path = os.path.join(
            os.path.dirname(p=__file__),
            "..",
            "prompt_engineering",
            "meta_prompt.md",
        )
        try:
            with open(file=prompt_path, mode="r", encoding="utf-8") as file:
                instructions = file.read()
            return instructions
        except FileNotFoundError:
            print(f"File not found: {prompt_path}")
            return ""
        except Exception as e:
            print(f"Error reading instructions from {prompt_path}: {e}")
            return ""

    def get_guided_json(self, state: StateT) -> Dict[str, Any]:
        """
        Get guided JSON schema for response generation,
        aligning with meta_prompt.md.

        :param state: The current state of the agent.
        :return: Guided JSON schema as a dictionary.
        """
        guided_json_schema = {
            "type": "object",
            "properties": {
                "step_1": {
                    "type": "object",
                    "properties": {
                        "workpad_summary": {
                            "type": "string",
                            "description": "Extractively summarize information you have in the workpad, including the relevant sources as they relate to the requirements.",  # noqa: E501
                        },
                        "reasoning_steps": {
                            "type": "string",
                            "description": "Based on the workpad summary and the agents available to you, outline your reasoning steps for solving the requirements.",  # noqa: E501
                        },
                        "work_completion": {
                            "type": "string",
                            "description": "Based on the workpad, determine if you have enough information to provide Type_2 work.",  # noqa: E501
                        },
                    },
                    "required": [
                        "workpad_summary",
                        "reasoning_steps",
                        "work_completion",
                    ],
                    "description": "First set of actions",
                    "additionalProperties": False,
                },
                "step_2": {
                    "type": "object",
                    "properties": {
                        "review": {
                            "type": "string",
                            "description": "Review your reasoning steps.",
                        },
                        "reasoning_steps_draft_2": {
                            "type": "string",
                            "description": "Provide another draft of your reasoning steps with any amendments from your review.",  # noqa: E501
                        },
                    },
                    "required": ["review", "reasoning_steps_draft_2"],
                    "description": "Second set of actions",
                    "additionalProperties": False,
                },
                "Agent": {
                    "type": "string",
                    "description": "Carefully select the agent to instruct from the Agent Register; ensure you provide the agent name exactly as it appears on the register.",  # noqa: E501
                },
                "step_3": {
                    "type": "object",
                    "properties": {
                        "draft_instructions": {
                            "type": "string",
                            "description": "Provide draft Type_1 or Type_2 work based on the workpad; use the workpad summary and reasoning steps to inform your response.",  # noqa: E501
                        },
                        "review": {
                            "type": "string",
                            "description": "Review the draft.",
                        },
                    },
                    "required": ["draft_instructions", "review"],
                    "description": "Third set of actions",
                    "additionalProperties": False,
                },
                "step_4": {
                    "type": "object",
                    "properties": {
                        "agent_alignment": {
                            "type": "string",
                            "description": "Check that your draft aligns with the agent's capabilities.",  # noqa: E501
                        },
                        "final_draft": {
                            "type": "string",
                            "description": "Provide a final draft of your Type_1 or Type_2 work.",  # noqa: E501
                        },
                    },
                    "required": ["agent_alignment", "final_draft"],
                    "description": "Final steps",
                    "additionalProperties": False,
                },
            },
            "required": ["step_1", "step_2", "Agent", "step_3", "step_4"],
            "additionalProperties": False,
        }

        return guided_json_schema

    def respond(
        self,
        instructions: str,
        requirements: str,
        state: StateT,
        agent_registry: StateT = AgentRegistry,
    ) -> str:
        """
        Generate a response based on instructions and state.

        :param instructions: Instructions for generating the response.
        :param requirements: User requirements.
        :param state: The current state of the agent.
        :param agent_registry: The agent registry.
        :return: Generated response as a string.
        """
        guided_json = self.get_guided_json(state)
        guided_json_str = (
            json.dumps(obj=guided_json)
            .encode(encoding="unicode_escape")
            .decode(encoding="utf-8")
        )

        # Unpack all key-value pairs in the state and include them in the msg
        if state:
            # workpad = "\n".join(f"{key}: {value}" for key, value in state.items()) # noqa: E501
            workpad = "\n".join(
                f"{key}: {value}"
                for key, value in state.items()
                if key != "meta_agent"  # noqa: E501
            )
        else:
            workpad = "No previous state."

        if agent_registry:
            agent_registry_content = "\n".join(
                f"{key}: {value}" for key, value in agent_registry.items()
            )
        else:
            agent_registry_content = "No previous agent registry."

        user_message = f"<user_requirements>\n{requirements}\n</user_requirements>\n<workpad>\n{workpad}\n</workpad>"  # noqa: E501

        system_prompt = f"{instructions}\n\n<agent_registry>\n{agent_registry_content}\n</agent_registry>\n\n You must respond in the following JSON format: {guided_json_str}"  # noqa: E501

        messages = [{"role": "system", "content": system_prompt}] + [
            {"role": "user", "content": user_message}
        ]

        json_llm = self.get_llm(json_response=True)
        response = json_llm.invoke(messages, guided_json=guided_json)
        return response

    def invoke(self, state: StateT, requirements: str) -> Dict[str, Any]:
        """
        Invoke the response generation process.

        :param state: The current state of the agent.
        :param requirements: User requirements.
        :return: A dictionary containing the output.
        """
        instructions = self.read_instructions(state)
        response = self.respond(
            instructions,
            requirements,
            state,
        )

        # Write the response to the state
        print(
            colored(
                text=f"DEBUG: MetaAgent response: {response}",
                color="red",
            )
        )
        self.write_to_state(state, response)

        # Return the output
        return state


class ReporterAgent(BaseAgent[StateT]):
    """
    # Functionality:
    This agent delivers the final response to the user exactly
    as provided, without any modifications or additional commentary.
    Use this agent when you have a final response to deliver to the user.

    ## Inputs:
        - 'instruction': The complete and final response to be delivered
        to the user verbatim.

    ## Outputs:
        - 'response': The final response, delivered to the user without
        any alterations.

    ## Important Notes:
        - This agent does not generate or modify content. It only relays
        the given response.
        - Ensure that the input 'instruction' is the fully prepared,
        final response intended for the user.
        - No preamble, commentary, or additional formatting will be added
        to the response.

    ## Remember:
        - I cannot generate any response, I can only relay your response
        to the user.
    """

    def __init__(
        self,
        name: str,
        model: str = "gpt-4o",
        server: str = "openai",
        temperature: float = 0,
    ) -> None:
        super().__init__(
            name=name,
            model=model,
            server=server,
            temperature=temperature,
        )
        print(f"ReporterAgent '{self.name}' initialized.")

    @traceable
    def invoke(self, state: StateT) -> Dict[str, Any]:
        """
        Invoke the agent's main functionality: process the instruction
        and return a response.

        :param state: The current state of the agent.
        :return: A dictionary containing the output.
        """
        instruction = self.read_instructions(state=state)
        if not instruction:
            print(f"No instruction provided to {self.name}.")
            return {}

        print(f"{self.name} is reporting the response to user")

        # Write the response to the state
        self.write_to_state(state=state, response=instruction)
        print(f"{self.name} wrote response to state.")

        # Return the output
        return state

    # return _invoke()


class SimpleAgent(BaseAgent[StateT]):
    def invoke(self, state: StateT) -> Dict[str, Any]:
        # Implement the required method, even if it's just
        # a pass or a simple implementation
        return {}
