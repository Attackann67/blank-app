from flask import Flask, render_template, jsonify
import json
from pathlib import Path

app = Flask(__name__)

USAGE_DATA_DIR = Path.home() / ".claude" / "usage-data"
FACETS_DIR = USAGE_DATA_DIR / "facets"
SESSION_META_DIR = USAGE_DATA_DIR / "session-meta"

EMBEDDED_SESSIONS = []
EMBEDDED_FACETS = []

for d, store in [(SESSION_META_DIR, EMBEDDED_SESSIONS), (FACETS_DIR, EMBEDDED_FACETS)]:
    if d.exists():
        for f in sorted(d.glob("*.json")):
            with open(f) as fh:
                store.append(json.load(fh))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def api_data():
    sessions = EMBEDDED_SESSIONS
    facets = EMBEDDED_FACETS

    total_sessions = len(sessions)
    analyzed = len(facets)
    total_messages = sum(s.get("user_message_count", 0) + s.get("assistant_message_count", 0) for s in sessions)
    total_hours = round(sum(s.get("duration_minutes", 0) for s in sessions) / 60, 1)
    total_commits = sum(s.get("git_commits", 0) for s in sessions)
    total_input = sum(s.get("input_tokens", 0) for s in sessions)
    total_output = sum(s.get("output_tokens", 0) for s in sessions)

    hours = [0] * 24
    for s in sessions:
        for h in s.get("message_hours", []):
            if 0 <= h < 24:
                hours[h] += 1

    all_tools = {}
    for s in sessions:
        for tool, count in s.get("tool_counts", {}).items():
            all_tools[tool] = all_tools.get(tool, 0) + count

    outcomes = {}
    frictions = {}
    for f in facets:
        o = f.get("outcome", "unknown")
        outcomes[o] = outcomes.get(o, 0) + 1
        for fric, c in f.get("friction_counts", {}).items():
            frictions[fric] = frictions.get(fric, 0) + c

    categories = {}
    for f in facets:
        for cat, c in f.get("goal_categories", {}).items():
            categories[cat] = categories.get(cat, 0) + c

    features = {
        "Task Agents": sum(1 for s in sessions if s.get("uses_task_agent")),
        "MCP": sum(1 for s in sessions if s.get("uses_mcp")),
        "Web Search": sum(1 for s in sessions if s.get("uses_web_search")),
        "Web Fetch": sum(1 for s in sessions if s.get("uses_web_fetch")),
    }

    session_list = []
    facet_map = {f["session_id"]: f for f in facets if "session_id" in f}
    for s in sorted(sessions, key=lambda x: x.get("start_time", ""), reverse=True):
        sid = s.get("session_id", "")
        facet = facet_map.get(sid, {})
        session_list.append({
            "time": s.get("start_time", ""),
            "prompt": s.get("first_prompt", "No prompt"),
            "duration": s.get("duration_minutes", 0),
            "messages": s.get("user_message_count", 0) + s.get("assistant_message_count", 0),
            "tools": s.get("tool_counts", {}),
            "lines_added": s.get("lines_added", 0),
            "lines_removed": s.get("lines_removed", 0),
            "files": s.get("files_modified", 0),
            "commits": s.get("git_commits", 0),
            "input_tokens": s.get("input_tokens", 0),
            "output_tokens": s.get("output_tokens", 0),
            "outcome": facet.get("outcome", "—"),
            "helpfulness": facet.get("claude_helpfulness", "—"),
            "summary": facet.get("brief_summary", ""),
            "friction": facet.get("friction_detail", ""),
        })

    return jsonify({
        "stats": {
            "sessions": total_sessions,
            "analyzed": analyzed,
            "messages": total_messages,
            "hours": total_hours,
            "commits": total_commits,
            "input_tokens": total_input,
            "output_tokens": total_output,
        },
        "activity_hours": hours,
        "tools": all_tools,
        "outcomes": outcomes,
        "frictions": frictions,
        "categories": categories,
        "features": features,
        "sessions": session_list,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
