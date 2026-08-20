import streamlit as st

from backend import (
    AVAILABLE_MODELS,
    MODEL,
    MAX_REVISIONS,
    list_available_models,
    run_loop,
)


st.set_page_config(
    page_title="Learning Loop Engineering",
    page_icon="↻",
    layout="wide",
)


def show_event(event: dict, index: int) -> None:
    agent = event["agent"].capitalize()
    label = f"{index}. {agent}"

    with st.expander(label, expanded=index == 1):
        if event["agent"] in {"writer", "reviser"}:
            st.markdown(event["draft"])
            st.caption(f"Revision count: {event['reviser_count']}")
        else:
            decision = event["decision"]
            if decision == "PASS":
                st.success("PASS - the draft satisfies the review rules.")
            else:
                st.warning("REVISE - the reviewer found something to improve.")
            st.write(event["feedback"] or "No changes needed.")


st.title("Learning Loop Engineering")
st.write(
    "Explore a self-correcting multi-agent workflow: a writer creates an answer, "
    "a reviewer checks it, and a reviser improves it when needed."
)

with st.sidebar:
    st.header("About this loop")
    st.markdown(
        "**Writer -> Reviewer -> Reviser**\n\n"
        "The reviewer decides whether the answer passes. The graph loops back to "
        "the reviser until it passes or reaches the revision limit."
    )
    st.divider()
    st.subheader("Bring your own key")
    st.caption("Your key is used only for this session and is not saved by the app.")
    api_key = st.text_input(
        "Groq API key",
        value="",
        type="password",
        placeholder="gsk_... (or leave blank to use .env)",
    )
    if "available_models" not in st.session_state:
        st.session_state["available_models"] = AVAILABLE_MODELS
    if st.button("Load available models"):
        if not api_key.strip():
            st.warning("Enter a BYOK key before loading account models.")
        else:
            try:
                models = list_available_models(api_key.strip())
                if models:
                    st.session_state["available_models"] = models
                    st.success(f"Loaded {len(models)} models.")
                else:
                    st.warning("No models were returned; keeping the configured list.")
            except Exception as exc:
                st.error(f"Could not load models: {exc}")
    model_options = st.session_state["available_models"]
    default_index = model_options.index(MODEL) if MODEL in model_options else 0
    selected_model = st.selectbox(
        "Model",
        options=model_options,
        index=default_index,
        help="Use the button above to load models available to your BYOK account.",
    )
    st.caption(f"Maximum revisions: `{MAX_REVISIONS}`")

with st.form("learning_loop_form"):
    topic = st.text_area(
        "What should the agents explain?",
        value="What is an AI agent?",
        height=100,
        placeholder="For example: Explain how a bicycle stays balanced.",
    )
    submitted = st.form_submit_button("Run learning loop", type="primary")

if submitted:
    if not topic.strip():
        st.error("Please enter a topic first.")
    else:
        with st.spinner("The agents are thinking and reviewing..."):
            try:
                st.session_state["result"] = run_loop(
                    topic.strip(),
                    api_key=api_key.strip() or None,
                    model_name=selected_model,
                )
            except Exception as exc:
                st.error(f"The loop could not run: {exc}")

result = st.session_state.get("result")
if result:
    st.divider()
    st.subheader(f"Final answer: {result['topic']}")
    st.markdown(result["final_answer"])

    decision = result["final_decision"]
    if decision == "PASS":
        st.success("Final review: PASS")
    else:
        st.warning("Final review: REVISE limit reached")
    st.caption(f"Revisions used: {result['revision_count']}")

    st.subheader("What happened inside the loop")
    for index, event in enumerate(result["events"], start=1):
        show_event(event, index)
