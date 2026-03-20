import streamlit as st
import json
import os
from pathlib import Path
from datetime import datetime

USAGE_DATA_DIR = Path.home() / ".claude" / "usage-data"
FACETS_DIR = USAGE_DATA_DIR / "facets"
SESSION_META_DIR = USAGE_DATA_DIR / "session-meta"

st.set_page_config(page_title="Claude Code Insights", page_icon="📊", layout="wide")


def load_json_files(directory: Path) -> list[dict]:
    """Load all JSON files from a directory."""
    files = []
    if directory.exists():
        for f in sorted(directory.glob("*.json")):
            with open(f) as fh:
                files.append(json.load(fh))
    return files


def load_insights_report() -> dict | None:
    """Load the generated insights report data by parsing the HTML for embedded JSON, or reconstruct from facets."""
    return None


def render_header(sessions: list[dict], facets: list[dict]):
    """Render the top-level stats header."""
    st.title("📊 Claude Code Insights")

    total_sessions = len(sessions)
    analyzed = len(facets)
    total_messages = sum(s.get("user_message_count", 0) + s.get("assistant_message_count", 0) for s in sessions)
    total_hours = sum(s.get("duration_minutes", 0) for s in sessions) / 60
    total_commits = sum(s.get("git_commits", 0) for s in sessions)

    cols = st.columns(5)
    cols[0].metric("Total Sessions", total_sessions)
    cols[1].metric("Analyzed", analyzed)
    cols[2].metric("Messages", total_messages)
    cols[3].metric("Hours", f"{total_hours:.1f}h")
    cols[4].metric("Commits", total_commits)


def render_at_a_glance(facets: list[dict]):
    """Render the At a Glance summary section."""
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

    st.subheader("At a Glance")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Session Outcomes**")
        for outcome, count in sorted(outcomes.items(), key=lambda x: -x[1]):
            label = outcome.replace("_", " ").title()
            st.write(f"- {label}: **{count}**")

    with col2:
        st.markdown("**Friction Points**")
        if frictions:
            for fric, count in sorted(frictions.items(), key=lambda x: -x[1]):
                label = fric.replace("_", " ").title()
                st.write(f"- {label}: **{count}**")
        else:
            st.write("No friction points recorded.")


def render_session_details(sessions: list[dict], facets: list[dict]):
    """Render detailed session information."""
    st.subheader("Session Details")

    facet_map = {f["session_id"]: f for f in facets if "session_id" in f}

    for session in sorted(sessions, key=lambda s: s.get("start_time", ""), reverse=True):
        sid = session.get("session_id", "unknown")
        start = session.get("start_time", "")
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            time_str = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, AttributeError):
            time_str = start

        first_prompt = session.get("first_prompt", "No prompt recorded")
        duration = session.get("duration_minutes", 0)
        facet = facet_map.get(sid)

        helpfulness = facet.get("claude_helpfulness", "N/A") if facet else "N/A"
        outcome = facet.get("outcome", "N/A") if facet else "N/A"

        with st.expander(f"🕐 {time_str} — {first_prompt[:80]}"):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Duration", f"{duration}m")
            c2.metric("Messages", session.get("user_message_count", 0) + session.get("assistant_message_count", 0))
            c3.metric("Outcome", outcome.replace("_", " ").title())
            c4.metric("Helpfulness", helpfulness.replace("_", " ").title())

            st.markdown("**Tools Used**")
            tool_counts = session.get("tool_counts", {})
            if tool_counts:
                st.write(", ".join(f"{tool} ({count})" for tool, count in tool_counts.items()))
            else:
                st.write("No tools used")

            st.markdown("**Code Changes**")
            st.write(f"+{session.get('lines_added', 0)} / -{session.get('lines_removed', 0)} lines · {session.get('files_modified', 0)} files · {session.get('git_commits', 0)} commits")

            st.markdown("**Tokens**")
            st.write(f"Input: {session.get('input_tokens', 0):,} · Output: {session.get('output_tokens', 0):,}")

            if facet:
                st.markdown("**Summary**")
                st.write(facet.get("brief_summary", "No summary available."))

                if facet.get("friction_detail"):
                    st.warning(f"**Friction:** {facet['friction_detail']}")


def render_tool_usage(sessions: list[dict]):
    """Render aggregate tool usage stats."""
    st.subheader("Tool Usage")

    all_tools = {}
    for s in sessions:
        for tool, count in s.get("tool_counts", {}).items():
            all_tools[tool] = all_tools.get(tool, 0) + count

    if not all_tools:
        st.info("No tool usage recorded yet.")
        return

    sorted_tools = sorted(all_tools.items(), key=lambda x: -x[1])
    tool_names = [t[0] for t in sorted_tools]
    tool_values = [t[1] for t in sorted_tools]

    st.bar_chart(dict(zip(tool_names, tool_values)))


def render_activity_patterns(sessions: list[dict]):
    """Render activity timing patterns."""
    st.subheader("Activity Patterns")

    hours = [0] * 24
    for s in sessions:
        for h in s.get("message_hours", []):
            if 0 <= h < 24:
                hours[h] += 1

    if any(hours):
        hour_labels = [f"{h:02d}:00" for h in range(24)]
        st.bar_chart(dict(zip(hour_labels, hours)))
    else:
        st.info("Not enough data for activity patterns.")


def render_token_summary(sessions: list[dict]):
    """Render token usage summary."""
    st.subheader("Token Usage")

    total_input = sum(s.get("input_tokens", 0) for s in sessions)
    total_output = sum(s.get("output_tokens", 0) for s in sessions)

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Input Tokens", f"{total_input:,}")
    c2.metric("Total Output Tokens", f"{total_output:,}")
    c3.metric("Total Tokens", f"{total_input + total_output:,}")


def render_goal_categories(facets: list[dict]):
    """Render goal category breakdown."""
    st.subheader("Goal Categories")

    categories = {}
    for f in facets:
        for cat, count in f.get("goal_categories", {}).items():
            categories[cat] = categories.get(cat, 0) + count

    if not categories:
        st.info("No goal categories recorded.")
        return

    sorted_cats = sorted(categories.items(), key=lambda x: -x[1])
    for cat, count in sorted_cats:
        label = cat.replace("_", " ").title()
        st.write(f"- **{label}**: {count}")


def render_feature_usage(sessions: list[dict]):
    """Render feature adoption summary."""
    st.subheader("Feature Adoption")

    features = {
        "Task Agents": sum(1 for s in sessions if s.get("uses_task_agent")),
        "MCP": sum(1 for s in sessions if s.get("uses_mcp")),
        "Web Search": sum(1 for s in sessions if s.get("uses_web_search")),
        "Web Fetch": sum(1 for s in sessions if s.get("uses_web_fetch")),
    }

    total = len(sessions) or 1
    for feature, count in features.items():
        pct = count / total * 100
        st.progress(pct / 100, text=f"{feature}: {count}/{len(sessions)} sessions ({pct:.0f}%)")


def main():
    sessions = load_json_files(SESSION_META_DIR)
    facets = load_json_files(FACETS_DIR)

    render_header(sessions, facets)

    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Sessions", "Tools & Tokens", "Patterns"])

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
    st.caption("Data sourced from ~/.claude/usage-data · Generated by Claude Code Insights")


if __name__ == "__main__":
    main()
