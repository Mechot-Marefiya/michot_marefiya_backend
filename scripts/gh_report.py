import os
import sys
from datetime import datetime, timedelta, timezone
from github import Github
import requests

# --- Configuration ---
ORG_NAME = "Michot-IT-Solutions"
REPOS = [
    "michot_marefiya_backend",
    "michot_marefiya_ui",
    "michot_marefiya_mobile"
]
PROJECT_OWNER = ORG_NAME  # Can be a user or org
DAYS_LOOKBACK = 7

# --- GraphQL Queries ---
PROJECT_V2_QUERY = """
query($login: String!, $number: Int!) {
  organization(login: $login) {
    projectV2(number: $number) {
      title
      items(first: 100) {
        nodes {
          content {
            ... on Issue {
              title
              url
              number
              state
            }
            ... on PullRequest {
              title
              url
              number
              state
            }
          }
          fieldValues(first: 10) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field {
                  ... on ProjectV2Field {
                    name
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

class GitHubReporter:
    def __init__(self, token):
        self.g = Github(token)
        self.token = token
        self.since = datetime.now(timezone.utc) - timedelta(days=DAYS_LOOKBACK)
        self.report_data = {repo: {"commits": [], "issues": [], "comments": []} for repo in REPOS}
        self.project_updates = []

    def fetch_repo_activity(self):
        print(f"Fetching activity since {self.since}...")
        for repo_name in REPOS:
            full_name = f"{ORG_NAME}/{repo_name}"
            print(f"  Processing {full_name}...")
            repo = self.g.get_repo(full_name)

            # Commits
            commits = repo.get_commits(since=self.since)
            for commit in commits:
                self.report_data[repo_name]["commits"].append({
                    "sha": commit.sha[:7],
                    "msg": commit.commit.message.split('\n')[0],
                    "author": commit.commit.author.name,
                    "date": commit.commit.author.date
                })

            # Issues & Comments (Closed or updated recently)
            issues = repo.get_issues(state='all', since=self.since)
            for issue in issues:
                self.report_data[repo_name]["issues"].append({
                    "number": issue.number,
                    "title": issue.title,
                    "state": issue.state,
                    "url": issue.html_url
                })
                
                # Fetch comments
                comments = issue.get_comments(since=self.since)
                for comment in comments:
                    self.report_data[repo_name]["comments"].append({
                        "issue_number": issue.number,
                        "author": comment.user.login,
                        "body": comment.body[:100] + "..." if len(comment.body) > 100 else comment.body,
                        "url": comment.html_url
                    })

    def fetch_project_v2(self, project_number):
        # Note: This logic assumes an Organization project. 
        # If it's a User project, the query needs to change from 'organization' to 'user'
        headers = {"Authorization": f"token {self.token}"}
        variables = {"login": ORG_NAME, "number": project_number}
        
        response = requests.post(
            "https://api.github.com/graphql",
            json={"query": PROJECT_V2_QUERY, "variables": variables},
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            # Basic parsing of project items - this is a simplified version
            # A truly "professional" one would compare states from a cache, 
            # but here we just list current items in 'Done' or 'In Progress'
            items = data.get("data", {}).get("organization", {}).get("projectV2", {}).get("items", {}).get("nodes", [])
            for item in items:
                content = item.get("content", {})
                fields = item.get("fieldValues", {}).get("nodes", [])
                status = "Unknown"
                for f in fields:
                    if f.get("field", {}).get("name") == "Status":
                        status = f.get("name")
                
                if status in ["Done", "In Progress"]:
                    self.project_updates.append({
                        "title": content.get("title"),
                        "status": status,
                        "url": content.get("url")
                    })
        else:
            print(f"Error fetching project: {response.status_code}")

    def generate_markdown(self):
        report = f"# 🚀 Weekly Activity Report: {datetime.now().strftime('%Y-%m-%d')}\n\n"
        report += f"Generated for **{ORG_NAME}** (Last {DAYS_LOOKBACK} days)\n\n"

        # Executive Summary
        total_commits = sum(len(d["commits"]) for d in self.report_data.values())
        total_issues = sum(len(d["issues"]) for d in self.report_data.values())
        report += "## 📊 Executive Summary\n"
        report += f"- **Total Commits:** {total_commits}\n"
        report += f"- **Active Issues/PRs:** {total_issues}\n"
        report += f"- **Project Updates:** {len(self.project_updates)}\n\n"

        # Project Status
        if self.project_updates:
            report += "## 🏗️ Project Board Highlights\n"
            done = [i for i in self.project_updates if i["status"] == "Done"]
            ip = [i for i in self.project_updates if i["status"] == "In Progress"]
            
            if done:
                report += "### ✅ Completed\n"
                for i in done: report += f"- [{i['title']}]({i['url']})\n"
            if ip:
                report += "\n### 🚧 In Progress\n"
                for i in ip: report += f"- [{i['title']}]({i['url']})\n"
            report += "\n"

        # Repo Breakdown
        report += "## 💻 Development Activity\n"
        for repo_name in REPOS:
            data = self.report_data[repo_name]
            if data["commits"] or data["issues"] or data["comments"]:
                report += f"### 📦 {repo_name.replace('_', ' ').title()}\n"
                if data["commits"]:
                    report += f"**Recent Commits ({len(data['commits'])}):**\n"
                    for c in data["commits"][:5]:  # Show top 5
                        report += f"- `{c['sha']}` {c['msg']} (by {c['author']})\n"
                
                if data["issues"]:
                    report += f"\n**Active Issues/PRs:**\n"
                    for i in data["issues"][:5]:
                        state_icon = "🟢" if i["state"] == "open" else "🔴"
                        report += f"- {state_icon} #{i['number']} [{i['title']}]({i['url']})\n"
                report += "\n"

        return report

def main():
    import argparse
    parser = argparse.ArgumentParser(description="GitHub Weekly Report Generator")
    parser.add_argument("--mock", action="store_true", help="Generate a mock report for testing")
    args = parser.parse_args()

    token = os.getenv("GITHUB_TOKEN")
    project_num = os.getenv("PROJECT_NUMBER") # e.g. 1
    
    if args.mock:
        print("Running in MOCK mode...")
        reporter = GitHubReporter("mock_token")
        reporter.report_data["michot_marefiya_backend"]["commits"] = [
            {"sha": "a1b2c3d", "msg": "Fixed auth bug", "author": "John Doe", "date": datetime.now()},
            {"sha": "e5f6g7h", "msg": "Updated API docs", "author": "Jane Smith", "date": datetime.now()}
        ]
        reporter.report_data["michot_marefiya_ui"]["commits"] = [
            {"sha": "i9j0k1l", "msg": "Added new dashboard component", "author": "Alice", "date": datetime.now()}
        ]
        reporter.project_updates = [
            {"title": "Implement User Profiles", "status": "Done", "url": "https://github.com/org/repo/issues/1"},
            {"title": "Fix Payment Gateway", "status": "In Progress", "url": "https://github.com/org/repo/issues/2"}
        ]
        report_md = reporter.generate_markdown()
    else:
        if not token:
            print("Error: GITHUB_TOKEN environment variable not set.")
            sys.exit(1)

        reporter = GitHubReporter(token)
        reporter.fetch_repo_activity()
        
        if project_num:
            try:
                reporter.fetch_project_v2(int(project_num))
            except ValueError:
                print("Invalid project number.")

        report_md = reporter.generate_markdown()
    
    # Write to file
    with open("weekly_report.md", "w", encoding="utf-8") as f:
        f.write(report_md)
    
    print("\nReport generated successfully in weekly_report.md")
    if args.mock:
        print("--- MOCK REPORT PREVIEW ---")
        print(report_md)

if __name__ == "__main__":
    main()
