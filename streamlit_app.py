import streamlit as st
import json
from pathlib import Path
from datetime import datetime

USAGE_DATA_DIR = Path.home() / ".claude" / "usage-data"
FACETS_DIR = USAGE_DATA_DIR / "facets"
SESSION_META_DIR = USAGE_DATA_DIR / "session-meta"

st.set_page_config(
    page_title="Claude Code Insights",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed",
)

MOBILE_CSS = """
<style>
    /* Mobile-first responsive design */
    .block-container {
        padding: 1rem 0.75rem !important;
        max-width: 100% !important;
    }

    /* Larger tap targets */
    .stExpander > summary {
        padding: 1rem 0.75rem !important;
        font-size: 0.95rem !important;
        line-height: 1.4 !important;
    }

    /* Metric cards - stack friendly */
    [data-testid="stMetric"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 0.75rem !important;
        text-align: center;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.4rem !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.75rem !important;
    }

    /* Tabs - larger touch targets */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0 !important;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 0.75rem 1rem !important;
        font-size: 0.9rem !important;
    }

    /* Progress bars */
    .stProgress > div > div {
        height: 1.2rem !important;
        border-radius: 8px !important;
    }

    /* Cards for sections */
    .insight-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 0.75rem;
    }

    /* Responsive columns - stack on small screens */
    @media (max-width: 640px) {
        [data-testid="column"] {
            width: 50% !important;
            flex: 0 0 50% !important;
            min-width: 0 !important;
        }
        .block-container {
            padding: 0.5rem !important;
        }
    }

    /* Better spacing */
    .stMarkdown p {
        font-size: 0.9rem;
        line-height: 1.6;
    }

    /* Warning/info boxes */
    .stAlert {
        border-radius: 10px !important;
        font-size: 0.85rem !important;
    }
</style>
"""

st.markdown(MOBILE_CSS, unsafe_allow_html=True)


def load_json_files(directory: Path) -> list[dict]:
    files = []
    if directory.exists():
        for f in sorted(directory.glob("*.json")):
            with open(f) as fh:
                files.append(json.load(fh))
    return files


def render_header(sessions: list[dict], facets: list[dict]):
    st.markdown("## 📊 Claude Code Insights")

    total_sessions = len(sessions)
    analyzed = len(facets)
    total_messages = sum(s.get("user_message_count", 0) + s.get("assistant_message_count", 0) for s in sessions)
    total_hours = sum(s.get("duration_minutes", 0) for s in sessions) / 60
    total_commits = sum(s.get("git_commits", 0) for s in sessions)

    row1 = st.columns(3)
    row1[0].metric("Sessions", total_sessions)
    row1[1].metric("Analyzed", analyzed)
    row1[2].metric("Messages", total_messages)

    row2 = st.columns(2)
    row2[0].metric("Hours", f"{total_hours:.1f}h")
    row2[1].metric("Commits", total_commits)


def render_at_a_glance(facets: list[dict]):
    if not facets:
        st.info("No analyzed sessions yet. Use Claude Code more to generate insights.")
        return

    outcomes = {}
    frictions = {}
    for f in facets:
        outcome = f.get("outcome", "unknown")
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        for fric, count in f.get("friction_counts", {}).items():
            frictions[fric] = frictions.get(fric, 0) + count

    st.markdown("### At a Glance")

    st.markdown("**Session Outcomes**")
    for outcome, count in sorted(outcomes.items(), key=lambda x: -x[1]):
        label = outcome.replace("_", " ").title()
        st.write(f"- {label}: **{count}**")

    st.markdown("**Friction Points**")
    if frictions:
        for fric, count in sorted(frictions.items(), key=lambda x: -x[1]):
            label = fric.replace("_", " ").title()
            st.write(f"- {label}: **{count}**")
    else:
        st.write("No friction points recorded. 🎉")


def render_session_details(sessions: list[dict], facets: list[dict]):
    st.markdown("### Sessions")

    facet_map = {f["session_id"]: f for f in facets if "session_id" in f}

    for session in sorted(sessions, key=lambda s: s.get("start_time", ""), reverse=True):
        sid = session.get("session_id", "unknown")
        start = session.get("start_time", "")
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            time_str = dt.strftime("%d %b %H:%M")
        except (ValueError, AttributeError):
            time_str = start

        first_prompt = session.get("first_prompt", "No prompt")
        duration = session.get("duration_minutes", 0)
        facet = facet_map.get(sid)

        outcome = facet.get("outcome", "—") if facet else "—"
        outcome_label = outcome.replace("_", " ").title() if outcome != "—" else "—"

        with st.expander(f"🕐 {time_str} · {first_prompt[:50]}"):
            c1, c2 = st.columns(2)
            c1.metric("Duration", f"{duration}m")
            msgs = session.get("user_message_count", 0) + session.get("assistant_message_count", 0)
            c2.metric("Messages", msgs)

            c3, c4 = st.columns(2)
            c3.metric("Outcome", outcome_label)
            helpfulness = facet.get("claude_helpfulness", "—") if facet else "—"
            c4.metric("Helpfulness", helpfulness.replace("_", " ").title() if helpfulness != "—" else "—")

            tool_counts = session.get("tool_counts", {})
            if tool_counts:
                st.markdown("**Tools:** " + ", ".join(f"`{t}` ×{c}" for t, c in tool_counts.items()))

            added = session.get("lines_added", 0)
            removed = session.get("lines_removed", 0)
            files = session.get("files_modified", 0)
            commits = session.get("git_commits", 0)
            if added or removed or files:
                st.markdown(f"**Code:** +{added} / -{removed} lines · {files} files · {commits} commits")

            inp = session.get("input_tokens", 0)
            out = session.get("output_tokens", 0)
            st.caption(f"Tokens: {inp:,} in · {out:,} out")

            if facet:
                summary = facet.get("brief_summary")
                if summary:
                    st.info(summary)
                friction = facet.get("friction_detail")
                if friction:
                    st.warning(friction)


def render_tool_usage(sessions: list[dict]):
    st.markdown("### Tool Usage")

    all_tools = {}
    for s in sessions:
        for tool, count in s.get("tool_counts", {}).items():
            all_tools[tool] = all_tools.get(tool, 0) + count

    if not all_tools:
        st.info("No tool usage recorded yet.")
        return

    sorted_tools = sorted(all_tools.items(), key=lambda x: -x[1])
    st.bar_chart({t[0]: t[1] for t in sorted_tools})


def render_token_summary(sessions: list[dict]):
    st.markdown("### Token Usage")

    total_input = sum(s.get("input_tokens", 0) for s in sessions)
    total_output = sum(s.get("output_tokens", 0) for s in sessions)
    total = total_input + total_output

    c1, c2 = st.columns(2)
    c1.metric("Input", f"{total_input:,}")
    c2.metric("Output", f"{total_output:,}")
    st.metric("Total", f"{total:,}")


def render_activity_patterns(sessions: list[dict]):
    st.markdown("### Activity by Hour")

    hours = [0] * 24
    for s in sessions:
        for h in s.get("message_hours", []):
            if 0 <= h < 24:
                hours[h] += 1

    if any(hours):
        hour_labels = [f"{h:02d}" for h in range(24)]
        st.bar_chart(dict(zip(hour_labels, hours)))
    else:
        st.info("Not enough data yet.")


def render_goal_categories(facets: list[dict]):
    st.markdown("### Goal Categories")

    categories = {}
    for f in facets:
        for cat, count in f.get("goal_categories", {}).items():
            categories[cat] = categories.get(cat, 0) + count

    if not categories:
        st.info("No goal categories recorded.")
        return

    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        label = cat.replace("_", " ").title()
        st.write(f"- **{label}**: {count}")


def render_feature_usage(sessions: list[dict]):
    st.markdown("### Feature Adoption")

    features = {
        "Task Agents": sum(1 for s in sessions if s.get("uses_task_agent")),
        "MCP": sum(1 for s in sessions if s.get("uses_mcp")),
        "Web Search": sum(1 for s in sessions if s.get("uses_web_search")),
        "Web Fetch": sum(1 for s in sessions if s.get("uses_web_fetch")),
    }

    total = len(sessions) or 1
    for feature, count in features.items():
        pct = count / total * 100
        st.progress(pct / 100, text=f"{feature}: {count}/{len(sessions)} ({pct:.0f}%)")


def main():
    sessions = load_json_files(SESSION_META_DIR)
    facets = load_json_files(FACETS_DIR)

    render_header(sessions, facets)

    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Sessions", "Tokens", "Patterns"])

    with tab1:
        render_at_a_glance(facets)
        render_goal_categories(facets)
        render_feature_usage(sessions)

    with tab2:
        render_session_details(sessions, facets)

    with tab3:
        render_tool_usage(sessions)
        render_token_summary(sessions)

    with tab4:
        render_activity_patterns(sessions)

    st.divider()
    st.caption("~/.claude/usage-data · Claude Code Insights")


if __name__ == "__main__":
    main()
