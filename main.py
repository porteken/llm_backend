from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from semantic_flow import SemanticRoutingFlow

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


@app.get("/")
async def root():
    return {"response": "Hello World"}


from pydantic import BaseModel


class Body(BaseModel):
    prompt: str


@app.post("/query")
async def query(body: Body):
    flow = SemanticRoutingFlow()
    response = await flow.kickoff_async(inputs={"prompt": body.prompt})
    return response
