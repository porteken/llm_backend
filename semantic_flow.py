from crewai.flow.flow import Flow, listen, start,router
from typing import Dict, Any
from pydantic import BaseModel 
from crews import python_crew,generic_crew
from semantic_router import Route
from semantic_router.encoders import MistralEncoder
from semantic_router.routers import SemanticRouter
class SemanticState(BaseModel):
    prompt: str = ""
    results: Dict = {}
class SemanticRoutingFlow(Flow[SemanticState]):
    
    """
    A CrewAI Flow that uses a semantic router to conditionally
    route a query to either a coding crew or a general knowledge crew.
    """
    @start()
    def start_flow(self) -> Dict[str,Any]:
        return {"prompt":self.state.prompt}

    @router(start_flow)
    def classify_query(self):
        """Classifies the query using semantic-router and updates the state."""
        print("--- [Classification Step] ---")
        
        coding_route = Route(name="coding", utterances=["What is the current stock price of apple?","How many r's are in strawberry?","what is 8^2"])
        general_route = Route(name="generic", utterances=["who was", "history of", "capital of"])
        routes = [coding_route, general_route]
        encoder = MistralEncoder(
            name="mistral-embed",
            score_threshold=0.4,
        )
                
        rl = SemanticRouter(encoder=encoder, routes=routes, auto_sync="local")
        
        classification = rl(self.state.prompt).name
        return classification
        
    @listen("coding")
    def handle_coding_path(self):
        result = python_crew.kickoff(inputs={"prompt":self.state.prompt})
        results={"method":"python","answer":result.raw}
        return {"results":results}

    @listen("generic")
    def handle_generic_path(self):
        result = generic_crew.kickoff(inputs={"prompt":self.state.prompt})
        results={"method":"llm","answer":result.raw}
        return {"results":results}
            
