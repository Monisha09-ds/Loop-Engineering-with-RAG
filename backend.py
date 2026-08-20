import os
from typing import Any, Literal, TypedDict

from dotenv import load_dotenv
from groq import Groq
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field


load_dotenv()
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_REVISIONS = int(os.getenv("MAX_REVISIONS", "2"))

DEFAULT_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]
AVAILABLE_MODELS = list(dict.fromkeys(
    model_name.strip()
    for model_name in os.getenv("GROQ_MODELS", ",".join(DEFAULT_MODELS)).split(",")
    if model_name.strip()
))
if MODEL not in AVAILABLE_MODELS:
    AVAILABLE_MODELS.insert(0, MODEL)


def list_available_models(api_key: str) -> list[str]:
    """Return models currently available to the supplied Groq account."""
    client = Groq(api_key=api_key)
    models = client.models.list()
    return sorted(model.id for model in models.data)

class Review(BaseModel):
    decision: Literal["PASS", "REVISE"] = Field(
        description="PASS only if the answer satisfies every review rule; otherwise REVISE."
    )
    feedback: str = Field(
        description="Short, specific feedback. Empty string when decision is PASS."
    )
    
class State(TypedDict):
    topic: str
    draft: str
    feedback: str
    decision: str
    revision_count: int
    
    
def writer(state: State, model: Any):
    """Agent 1: create the first answer."""
    response = model.invoke(
        [
            {
                "role": "system",
                "content": (
                    "You are a beginner-friendly teacher. Explain the topic in 120-160 words. "
                    "Use simple language, one everyday analogy, and one tiny example."
                ),
            },
            {"role": "user", "content": f"Explain: {state['topic']}"},
        ]
    )
    return {
        **state,
        "draft": response.content,
        "feedback": "",
        "decision": "",
        "revision_count": 0,
    }

def reviewer(state: State, reviewer_model: Any):
    """Agent 2: review the answer and provide feedback."""
    response = reviewer_model.invoke(
        [
            {
                "role": "system",
                "content": (
                    "You are a strict reviewer. Review the answer based on the following rules:\n"
                    "1. The answer must be between 120-160 words.\n"
                    "2. The answer must use simple language.\n"
                    "3. The answer must include one everyday analogy.\n"
                    "4. The answer must include one tiny example.\n"
                    "If the answer satisfies all rules, return PASS with empty feedback. "
                    "Otherwise, return REVISE with specific feedback."
                ),
            },
            {
                "role": "user",
                "content": f"Review: {state['draft']}"},
        ]
    )
    return {
        **state,
        "feedback": response.feedback,
        "decision": response.decision,
    }
    
def reviser(state: State, model: Any):
    """Agent 3: revise the answer based on feedback."""
    response = model.invoke(
        [
            {
                "role": "system",
                "content": (
                    "You are a helpful teacher. Revise the answer based on the feedback provided. "
                    "Ensure the revised answer satisfies all review rules."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Original Answer: {state['draft']}\n"
                    f"Feedback: {state['feedback']}\n"
                    f"Please provide a revised answer."
                ),
            },
        ]
    )
    return {
        **state,
        "draft": response.content,
        "feedback": "",
        "decision": "",
        "revision_count": state["revision_count"] + 1,
    }

def route_after_review(state: State):
    """Route the state based on the review decision."""
    if state["decision"] == "REVISE" and state["revision_count"] < MAX_REVISIONS:
        return "revise"
    return "done"
    
def build_graph(model: Any, max_revisions: int):
    """Build a loop bound to the model selected for this run."""
    reviewer_model = model.with_structured_output(Review)
    builder = StateGraph(State)
    builder.add_node("writer", lambda state: writer(state, model))
    builder.add_node("reviewer", lambda state: reviewer(state, reviewer_model))
    builder.add_node("reviser", lambda state: reviser(state, model))
    builder.add_edge(START, "writer")
    builder.add_edge("writer", "reviewer")
    builder.add_conditional_edges(
        "reviewer",
        lambda state: "revise" if (
            state["decision"] == "REVISE"
            and state["revision_count"] < max_revisions
        ) else "done",
        {"revise": "reviser", "done": END},
    )
    builder.add_edge("reviser", "reviewer")
    return builder.compile()
  
  
def run_loop(topic: str, api_key: str | None = None, model_name: str | None = None):
    """Run the loop workflow for a given topic."""
    selected_model = model_name or MODEL
    selected_api_key = api_key or os.getenv("GROQ_API_KEY")
    if not selected_api_key:
        raise ValueError("A Groq API key is required. Add it to .env or provide a BYOK key.")
    model = ChatGroq(
        model=selected_model,
        temperature=0,
        api_key=selected_api_key,
    )
    graph = build_graph(model, MAX_REVISIONS)
    state: State = {
        "topic": topic,
        "draft": "",
        "feedback": "",
        "decision": "",
        "revision_count": 0,
    }
    
    final_state = state.copy()
    events = []
    
    for update in graph.stream(input=state, stream_mode="updates"):
        for node_name, node_state in update.items():
            final_state.update(node_state)
            events.append({
                "agent": node_name,
                "draft": node_state.get("draft", ""),
                "decision": node_state.get("decision", ""), 
                "feedback": node_state.get("feedback", ""),
                "reviser_count": node_state.get("revision_count", 0),
                "state": node_state})
            # final_state.update(node_state)
    
    # return {
    #     "final_state": final_state,
    #     "events": events,
    # }
    return {
            "topic": topic,
            "events": events,
            "final_answer": final_state["draft"],
            "final_decision": final_state["decision"],
            "revision_count": final_state["revision_count"],
            "provider": "Groq",
            "model": selected_model,
        }
    

def run_demo(topic: str):
    """Small CLI version, useful if you want to demo without the browser."""
    result = run_loop(topic)

    print("\n=== SELF-CORRECTING MULTI-AGENT DEMO ===")
    print(f"Provider: {result['provider']}")
    print(f"Model: {result['model']}")
    print(f"Topic: {topic}\n")

    for event in result["events"]:
        print(f"\n--- {event['agent'].upper()} ---")
        if event["agent"] in {"writer", "reviser"}:
            print(event["draft"])
        elif event["agent"] == "reviewer":
            print("Decision:", event["decision"])
            print("Feedback:", event["feedback"] or "No changes needed")

    print("\n=== FINAL ANSWER ===")
    print(result["final_answer"])
    print(f"\nFinal decision: {result['final_decision']}")
    print(f"Revisions used: {result['revision_count']}")


if __name__ == "__main__":
    topic = input("Enter a topic (example: What is an AI agent?): ").strip()
    if not topic:
        topic = "What is an AI agent?"
    run_demo(topic)
