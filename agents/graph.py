from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from agents.state import ClinicalState
from agents.psychologist import psychologist_node
from agents.psychiatrist import psychiatrist_node
from agents.tools import psychiatrist_tools
from config import get_config

CFG = get_config()

def severity_router(state: ClinicalState) -> str:
    """
    Determines whether the Psychologist should handle the turn, 
    or if we need to escalate to the Psychiatrist.
    """
    severity = state.get("current_severity", 0.0)
    
    # Check if we should escalate
    if severity >= CFG.SEVERITY_ESCALATION_THRESHOLD:
        # If the last message was already from the psychiatrist, keep them active
        # unless they finished their assessment.
        if state.get("current_agent") == "psychiatrist":
            # If the last message is a tool call, we must go to tools
            last_msg = state["messages"][-1]
            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                return "tools"
            return "psychiatrist"
        else:
            # Transition to psychiatrist
            state["current_agent"] = "psychiatrist"
            state["escalation_reason"] = f"Severity ({severity:.2f}) exceeded {CFG.SEVERITY_ESCALATION_THRESHOLD}"
            return "psychiatrist"
    
    # Normal flow: Psychologist
    state["current_agent"] = "psychologist"
    return "psychologist"


def build_clinical_graph() -> StateGraph:
    """Build the multi-agent clinical state graph."""
    workflow = StateGraph(ClinicalState)
    
    # Add Nodes
    workflow.add_node("psychologist", psychologist_node)
    workflow.add_node("psychiatrist", psychiatrist_node)
    
    # The Tool node for the Psychiatrist's EHR lookups
    workflow.add_node("tools", ToolNode(psychiatrist_tools))
    
    # Edges from tools always return to Psychiatrist
    workflow.add_edge("tools", "psychiatrist")
    
    # Routing logic from START
    workflow.set_conditional_entry_point(
        severity_router,
        {
            "psychologist": "psychologist",
            "psychiatrist": "psychiatrist",
            "tools": "tools"
        }
    )
    
    # After an agent speaks, we wait for user input (END the current graph execution)
    workflow.add_edge("psychologist", END)
    
    # For Psychiatrist, if it output a tool call, go to tools, otherwise END
    def psychiatrist_router(state: ClinicalState):
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        return END
        
    workflow.add_conditional_edges("psychiatrist", psychiatrist_router)
    
    return workflow.compile()

if __name__ == "__main__":
    # Test compilation
    app = build_clinical_graph()
    print("Graph compiled successfully!")
