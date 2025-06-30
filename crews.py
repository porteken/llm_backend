from KubernetesInterpreter import KubernetesExecutionTool
from crewai import Agent, Task, Crew, Process
from pydantic import BaseModel, Field

kubernetes_tool = KubernetesExecutionTool()

model = "gemini/gemini-2.0-flash"

python_agent = Agent(
    role="Autonomous Python Software Engineer",
    goal=(
        "Understand a user's request, write the necessary Python code, "
        "and execute it to provide a final answer along with the code used in markdown format. You must ensure the code runs successfully. "
        "If the execution fails, you MUST analyze the error, rewrite the code to fix it, "
        "and execute it again. Repeat this process until you get a successful result."
    ),
    backstory=(
        "You are a highly skilled, autonomous software engineer. You have access to a secure "
        "code execution environment. Your job is not just to write code, but to deliver a "
        "working result. You are persistent and methodical, using execution feedback to "
        "iteratively improve your code until it meets the objective."
    ),
    tools=[kubernetes_tool],
    llm=model,
    verbose=True,
)


class PythonSchema(BaseModel):

    code: str = Field(..., description="Python3 code used to generate final answer.")
    answer: str = Field(..., description="answer from executed python code")


class GenericSchema(BaseModel):
    answer: str = Field(..., descritpion="answer from LLM")


python_task = Task(
    description="{prompt}",
    expected_output="{prompt}. Return code used",
    agent=python_agent,
    output_pydantic=PythonSchema,
)

# Create and run the crew
python_crew = Crew(
    agents=[python_agent],
    tasks=[python_task],
    process=Process.sequential,
)
generic_agent = Agent(
    role="Language Model",
    goal="Process and respond to the given input accurately.",
    backstory=(
        "You are a standard large language model. You do not have a personality, "
        "history, or any specific expertise beyond your training data. Your sole "
        "function is to process the input you receive and generate a relevant, "
        "fact-based response."
    ),
    llm=model,
    verbose=True,
)
generic_task = Task(
    description="{prompt}",
    expected_output="{prompt}",
    output_pydantic=GenericSchema,
    agent=generic_agent,
)

# Create and run the crew
generic_crew = Crew(
    agents=[generic_agent],
    tasks=[generic_task],
    process=Process.sequential,
)
