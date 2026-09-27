from agent_library import Agent, tool, OutputFormat
import math


class MathsOutput(OutputFormat):
    result: float
    rounding: str
    steps: list[str]


class Mathemetician(Agent):
    def __init__(self, name: str):
        systemprompt = "You are a mathemetician who will be given basic sums. Please use the tools available to you to calculate these sums."
        tools = ["add", "root"]
        super().__init__(name, "qwen3:8b", systemprompt, tools)


@tool("add", "Adds together two number, a and b.")
def add(a: float, b: float) -> float:
    print(f"Adding together: {a} and {b} with result {a + b}")
    return a + b


@tool("root", "Finds the square root of a number.")
def root(a: float) -> float:
    print(f"Rooting: {a} with result {math.sqrt(a)}")
    return math.sqrt(a)


ai = Mathemetician("Mathemetician1")

print(
    ai.ask(
        "Calculate the square root of (144.543 + 12456.98786) to 6 decimal places.",
        output_format=MathsOutput,
    )
)
