"""
LangGraph workflow — wires agent nodes into a state graph.

Agent logic lives in each agent module (router, retrieval, response, …).
This file only defines nodes, edges, and compilation.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.comparison import comparison_node
from app.agents.eligibility import eligibility_node
from app.agents.graph_edges import (
    after_check_index,
    after_load,
    after_retrieve,
    after_route,
)
from app.agents.graph_state import GovGraphState
from app.agents.graph_utils import split_reply
from app.agents.nodes.load import check_index_node, finalize_node, first_query_prep_node, load_node
from app.agents.nodes.static import feedback_node, help_node, welcome_back_node, welcome_first_node
from app.agents.response import default_branch_node, detail_branch_node, search_list_node, select_node
from app.agents.retrieval import retrieve_node
from app.agents.router import route_node


def build_gov_graph():
    graph = StateGraph(GovGraphState)

    # Pipeline nodes (each implemented in its agent module)
    graph.add_node("load", load_node)
    graph.add_node("route", route_node)
    graph.add_node("first_query_prep", first_query_prep_node)
    graph.add_node("check_index", check_index_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("eligibility", eligibility_node)
    graph.add_node("compare", comparison_node)
    graph.add_node("search_list", search_list_node)
    graph.add_node("detail_branch", detail_branch_node)
    graph.add_node("default_branch", default_branch_node)
    graph.add_node("select", select_node)
    graph.add_node("welcome_first", welcome_first_node)
    graph.add_node("welcome_back", welcome_back_node)
    graph.add_node("help", help_node)
    graph.add_node("feedback", feedback_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "load")
    graph.add_conditional_edges("load", after_load, {"finalize": "finalize", "route": "route"})

    graph.add_conditional_edges(
        "route",
        after_route,
        {
            "welcome_first": "welcome_first",
            "first_query": "first_query_prep",
            "welcome_back": "welcome_back",
            "help": "help",
            "feedback": "feedback",
            "select": "select",
            "check_index": "check_index",
        },
    )

    graph.add_edge("first_query_prep", "check_index")
    graph.add_conditional_edges(
        "check_index",
        after_check_index,
        {"finalize": "finalize", "retrieve": "retrieve"},
    )

    graph.add_conditional_edges(
        "retrieve",
        after_retrieve,
        {
            "eligibility": "eligibility",
            "compare": "compare",
            "search_list": "search_list",
            "detail_branch": "detail_branch",
            "default_branch": "default_branch",
        },
    )

    for specialist in (
        "eligibility",
        "compare",
        "search_list",
        "detail_branch",
        "default_branch",
    ):
        graph.add_edge(specialist, "finalize")

    for static in ("welcome_first", "welcome_back", "help", "feedback", "select"):
        graph.add_edge(static, "finalize")

    graph.add_edge("finalize", END)
    return graph.compile()


gov_graph = build_gov_graph()


def run_graph(chat_id: str, message: str) -> list[str]:
    """Invoke the LangGraph pipeline and return WhatsApp message parts."""
    from app.whatsapp.formatting import unwrap_whatsapp_transcript

    message = unwrap_whatsapp_transcript(message or "")
    result = gov_graph.invoke({"chat_id": chat_id, "user_message": message})
    parts = result.get("parts")
    if parts:
        return parts
    reply = result.get("reply") or "Something went wrong. Please try again."
    return split_reply(reply)
