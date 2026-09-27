from ollama import Client
from typing import Callable, Any, get_type_hints
import inspect
from pydantic import BaseModel, ValidationError, create_model

TOOLS: dict[str, dict] = {}

OLLAMA_HOST = "http://192.168.3.237:11434"


def tool(name: str, description: str):
    """Decorator used to register a Python function as a Ollama tool."""

    def decorator(function: Callable):
        TOOLS[name] = {"name": name, "description": description, "function": function}
        return function

    return decorator


class Agent:
    def __init__(
        self,
        name: str,
        model: str,
        system_prompt: str,
        allowed_tools: list[str] | None = None,
    ):
        self.name = name
        self.model = model
        self.system_prompt = system_prompt

        self.client = Client(host=OLLAMA_HOST)

        self.allowed_tools = allowed_tools or []

        self.messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            }
        ]

    def get_tools(self) -> dict[str, dict]:
        """Returns the tools that this agent is allowed to use"""
        tools = {}
        for name in self.allowed_tools:
            if name not in TOOLS:
                raise (ValueError(f"Tool '{name}' s not registered as a tool."))
            tools[name] = TOOLS[name]
        return tools

    def get_ollama_tools(self) -> list[dict]:
        """Convert this agent's tools into Ollama's tool format"""
        ollama_tools = []
        for tool_data in self.get_tools().values():
            function = tool_data["function"]
            parameters = self._get_paramaters(function)
            ollama_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool_data["name"],
                        "description": tool_data["description"],
                        "parameters": parameters,
                    },
                },
            )
        return ollama_tools

    # gets the parameters of a function
    def _get_paramaters(self, function: Callable) -> dict:
        signature = inspect.signature(function)
        type_hints = get_type_hints(function)

        fields = {}

        for name, parameter in signature.parameters.items():
            annotation = type_hints.get(name, str)

            if parameter.default is inspect.Parameter.empty:
                fields[name] = (annotation, ...)
            else:
                fields[name] = (annotation, parameter.default)

        model = create_model(f"{function.__name__}Parameters", **fields)

        return model.model_json_schema()

    def execute_tool(self, name: str, arguments: dict) -> Any:
        # Permission check
        if name not in self.allowed_tools:
            raise PermissionError(
                f"Agent '{self.name}' is not allowed to use tool '{name}'."
            )
        # Check if the tool exists
        if name not in TOOLS:
            raise ValueError(f"Tool '{name}' is not registered.")

        function = TOOLS[name]["function"]

        return function(**arguments)

    def ask(self, prompt: str, output_format=None) -> str:
        self.messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        # if there is a schema tell it that there is
        if output_format is not None:
            # self.messages.append(
            #    {
            #        "role": "user",
            #        "content": f"For this task, please output your FINAL result in the following schema. Please use tools normally, however your final output should be in the following schema. \n \n SCHEMA: \n {output_format.model_json_schema()}",
            #    }
            # )
            pass  # the ai currently is not smart enough to realise that when it is given this prompt, it can still use tools. therefore we must rely on the forced validation below, however it uses to prompts instead of one.

        while True:
            # make the arguments for the new ai message
            chat_kwargs = {
                "model": self.model,
                "messages": self.messages,
                "tools": self.get_ollama_tools(),
            }

            response = self.client.chat(**chat_kwargs)
            message = response["message"]

            # Add model response to conversation
            self.messages.append(message)

            # tool calls
            if not message.get("tool_calls"):  # no tool call
                # if there is a stuctured output
                if output_format is not None:
                    # check if the output is in the correct format
                    try:
                        return output_format.model_validate_json(message["content"])
                    except ValidationError:  # was not in the correct format
                        # force the model output by complete force, no tools, using the ollama format feature
                        print(
                            f"[{self.name}] Output did not pass output validation. Sending a new request to enforce the correct output."
                        )
                        retry_messages = (
                            self.messages
                            + [
                                {
                                    "role": "user",
                                    "content": (
                                        "Your previous response did not match the required output format. Please reformat your answer according to the required schema. Do not use tools or perform additional research."
                                    ),
                                }
                            ]
                        )  # make an 'invisible' message that only this agent that is doing the corrections can see.
                        retry_response = self.client.chat(
                            model=self.model,
                            messages=retry_messages,
                            format=output_format.model_json_schema(),
                        )
                        retry_message = retry_response["message"]
                        self.messages.append(retry_message)
                        return output_format.model_validate_json(
                            retry_message["content"]
                        )

                # if there is no structured output
                return message["content"]

            # execute tools
            for call in message["tool_calls"]:
                function = call["function"]
                name = function["name"]
                arguments = function["arguments"]

                print(f"[{self.name}] Calling tool '{name}' with {arguments}")
                result = self.execute_tool(name, arguments)
                self.messages.append({"role": "tool", "content": str(result)})


class OutputFormat(BaseModel):
    pass
