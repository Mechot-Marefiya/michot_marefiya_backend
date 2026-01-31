import os
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from github import Github, Auth
import requests

# --- Configuration ---
ORG_NAME = "Michot-IT-Solutions"
REPOS = [
    "michot_marefiya_backend",
    "michot_marefiya_ui",
    "michot_marefiya_mobile"
]
DAYS_LOOKBACK = 7
STALE_DAYS = 7
HOT_TOPIC_THRESHOLD = 3

# --- GraphQL for Projects ---
PROJECT_V2_QUERY = """
query($login: String!, $number: Int!) {
  organization(login: $login) {
    projectV2(number: $number) {
      title
      items(first: 100) {
        nodes {
          content {
            ... on Issue { title, url, number, state }
            ... on PullRequest { title, url, number, state }
          }
          fieldValues(first: 10) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2Field { name } }
              }
            }
          }
        }
      }
    }
  }
}
"""

class CommitAnalyzer:
    CATEGORIES = {
        "✨ Features": ["feat", "feature", "add", "implement"],
        "🐛 Bug Fixes": ["fix", "bug", "patch", "resolve", "handle", "hotfix"],
        "♻️ Refactor": ["refactor", "cleanup", "structure", "move", "remove", "delete"],
        "🔧 Chore & CI": ["chore", "ci", "build", "test", "docs", "merge", "bump"],
        "🚀 Performance": ["perf", "optimize"],
        "💄 UI/Style": ["style", "ui", "css", "design", "theme"]
    }

    @staticmethod
    def categorize(message):
        lower_msg = message.lower()
        for category, keywords in CommitAnalyzer.CATEGORIES.items():
            for kw in keywords:
                if lower_msg.startswith(kw) or f": {kw}" in lower_msg:
                    return category
        return "📦 Other Changes"

class ReportFormatter:
    @staticmethod
    def create_table(headers, rows):
        if not rows: return ""
        header_row = "| " + " | ".join(headers) + " |"
        separator = "| " + " | ".join(["---"] * len(headers)) + " |"
        data_rows = ""
        for row in rows:
            data_rows += "| " + " | ".join(str(x) for x in row) + " |\n"
        return f"\n{header_row}\n{separator}\n{data_rows}\n"

class GitHubReporterV3:
    def __init__(self, token):
        auth = Auth.Token(token)
        self.g = Github(auth=auth)
        self.token = token
        self.since = datetime.now(timezone.utc) - timedelta(days=DAYS_LOOKBACK)
        self.repo_data = {} 
        self.project_updates = []
        self.update_log = []
        self.contributors = defaultdict(lambda: {"commits": 0, "prs": 0})
        self.hot_topics = []
        self.stale_prs = []

    def fetch_data(self):
        print(f"Fetching V3 Enterprise data since {self.since}...")
        for repo_name in REPOS:
            full_name = f"{ORG_NAME}/{repo_name}"
            print(f"  Processing {full_name}...")
            
            repo_stats = {
                "commits": defaultdict(list),
                "open_prs": [],
                "merged_prs": [],
                "issues": []
            }

            try:
                repo = self.g.get_repo(full_name)

                commits = repo.get_commits(since=self.since)
                for c in commits:
                    msg = c.commit.message.split('\n')[0]
                    author = c.commit.author.name or c.author.login if c.author else "Unknown"
                    category = CommitAnalyzer.categorize(msg)
                    
                    repo_stats["commits"][category].append({
                        "sha": c.sha[:7], 
                        "msg": msg, 
                        "author": author,
                        "url": c.html_url
                    })
                    self.contributors[author]["commits"] += 1

                items = repo.get_issues(state='all')
                
                for item in items:
                    is_recent = item.updated_at >= self.since
                    is_stale = item.state == 'open' and (datetime.now(timezone.utc) - item.created_at).days > STALE_DAYS
                    
                    if not (is_recent or (is_stale and item.pull_request)):
                        continue

                    if item.comments >= HOT_TOPIC_THRESHOLD and is_recent:
                        self.hot_topics.append({
                            "title": item.title,
                            "url": item.html_url,
                            "comments": item.comments,
                            "repo": repo_name,
                            "type": "PR" if item.pull_request else "Issue"
                        })

                    if item.pull_request:
                        pr = item.as_pull_request()
                        pr_info = {
                            "number": pr.number,
                            "title": pr.title,
                            "user": pr.user.login,
                            "url": pr.html_url,
                            "created_at": pr.created_at
                        }
                        
                        if pr.merged and pr.merged_at and pr.merged_at >= self.since:
                            repo_stats["merged_prs"].append(pr_info)
                            self.contributors[pr.user.login]["prs"] += 1
                        elif pr.state == 'open':
                            repo_stats["open_prs"].append(pr_info)
                            days_open = (datetime.now(timezone.utc) - pr.created_at).days
                            if days_open > STALE_DAYS:
                                self.stale_prs.append({
                                    "title": pr.title,
                                    "url": pr.html_url,
                                    "days": days_open,
                                    "repo": repo_name,
                                    "user": pr.user.login
                                })
                    else:
                        if is_recent:
                            repo_stats["issues"].append({
                                "number": item.number,
                                "title": item.title,
                                "state": item.state,
                                "url": item.html_url
                            })

                self.repo_data[repo_name] = repo_stats

            except Exception as e:
                print(f"  [ERROR] access failed for {full_name}: {e}")

    def fetch_project_v2(self, project_number):
        headers = {"Authorization": f"token {self.token}"}
        variables = {"login": ORG_NAME, "number": project_number}
        try:
            resp = requests.post("https://api.github.com/graphql", json={"query": PROJECT_V2_QUERY, "variables": variables}, headers=headers)
            if resp.status_code == 200:
                data = resp.json().get("data", {}).get("organization", {}).get("projectV2", {}).get("items", {}).get("nodes", [])
                for item in data:
                    status = next((f["name"] for f in item.get("fieldValues", {}).get("nodes", []) if f.get("field", {}).get("name") == "Status"), "Unknown")
                    if status in ["Done", "In Progress", "Todo"]:
                        self.project_updates.append({
                            "title": item.get("content", {}).get("title"),
                            "status": status,
                            "url": item.get("content", {}).get("url")
                        })
        except Exception as e:
            print(f"Project fetch error: {e}")

    def generate_report(self):
        date_str = datetime.now().strftime('%Y-%m-%d')
        md = f"# 🚀 Michot Marefia Weekly Report: {date_str}\n\n"
        
        total_commits = sum(sum(len(v) for v in d["commits"].values()) for d in self.repo_data.values())
        total_merged = sum(len(d["merged_prs"]) for d in self.repo_data.values())
        total_open_prs = sum(len(d["open_prs"]) for d in self.repo_data.values())
        
        md += "## 📊 Executive Overview\n"
        md += f"| Metric | Count | Status |\n|---|---|---|\n"
        md += f"| 🔨 **Commits** | {total_commits} | 🟢 Active |\n"
        md += f"| 🚢 **Shipped** | {total_merged} | 🟣 Delivered |\n"
        md += f"| 🚧 **In Progress** | {total_open_prs} | 🟡 Continued |\n\n"

        if self.stale_prs:
            md += "## 🚨 Needs Attention (Stale PRs > 7 days)\n"
            md += "> *These items are blocking flow. Please review.* \n\n"
            rows = [[p['repo'], f"[{p['title']}]({p['url']})", f"{p['days']} days", p['user']] for p in self.stale_prs]
            md += ReportFormatter.create_table(["Repo", "PR Title", "Age", "Author"], rows)
        
        if self.hot_topics:
            md += "## 🔥 Hot Topics (High Activity)\n"
            md += "> *Discussions with high engagement recently.* \n\n"
            rows = [[t['repo'], t['type'], f"[{t['title']}]({t['url']})", f"💬 {t['comments']}"] for t in self.hot_topics]
            md += ReportFormatter.create_table(["Repo", "Type", "Topic", "Comments"], rows)

        if self.contributors:
            md += "## 🏆 Top Contributors\n"
            sorted_contribs = sorted(self.contributors.items(), key=lambda x: x[1]['commits'], reverse=True)[:5]
            rows = [[user, data['commits'], data['prs']] for user, data in sorted_contribs]
            md += ReportFormatter.create_table(["User", "Commits", "Shipped"], rows)

        if self.project_updates:
            md += "## 🏗️ Project Board Snapshot\n"
            by_status = defaultdict(list)
            for p in self.project_updates: by_status[p["status"]].append(p)
            
            for status in ["Done", "In Progress", "Todo"]:
                if by_status[status]:
                    icon = "✅" if status == "Done" else "🚧" if status == "In Progress" else "📋"
                    md += f"### {icon} {status}\n"
                    rows = [[f"[{item['title']}]({item['url']})"] for item in by_status[status][:5]]

                    for item in by_status[status][:5]:
                        md += f"- [{item['title']}]({item['url']})\n"
                    if len(by_status[status]) > 5: md += f"- *...and {len(by_status[status])-5} more*\n"
                    md += "\n"

        md += "## 💻 Repository Deep Dive\n"
        for repo_name, data in self.repo_data.items():
            if not any(data.values()): continue 
            
            md += f"### 📦 {repo_name.replace('_', ' ').title()}\n"
            
            # PRs Table
            rows = []
            for pr in data["merged_prs"]: rows.append(["🟣 Merged", f"#{pr['number']} {pr['title']}", pr['user']])
            for pr in data["open_prs"]: rows.append(["🟢 Open", f"#{pr['number']} {pr['title']}", pr['user']])
            
            if rows:
                md += "**Pull Request Velocity**\n"
                md += ReportFormatter.create_table(["State", "PR", "Author"], rows)

            if data["commits"]:
                md += "<details><summary><b>View Recent Commits (Categorized)</b></summary>\n\n"
                for cat, commit_list in data["commits"].items():
                    md += f"#### {cat}\n"
                    for c in commit_list:
                        md += f"- [`{c['sha']}`]({c['url']}) {c['msg']} - *{c['author']}*\n"
                md += "\n</details>\n\n"
            
            md += "---\n"

        return md

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    if args.mock:
        print("Mock mode not fully supported in V3 snippet.")
        return

    token = os.getenv("GITHUB_TOKEN")
    project_num = os.getenv("PROJECT_NUMBER")

    if not token:
        print("Error: GITHUB_TOKEN not set.")
        sys.exit(1)

    reporter = GitHubReporterV3(token)
    reporter.fetch_data()
    if project_num:
        reporter.fetch_project_v2(int(project_num))
    
    report = reporter.generate_report()
    
    with open("weekly_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    print("Report generated: weekly_report.md")

if __name__ == "__main__":
    main()
