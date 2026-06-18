#!/usr/bin/env python3
"""
jira_helper.py — Jira REST API v3 CLI helper for GHAS workflows

Auth (required in environment or .env at repo root):
  JIRA_URL          https://tanishqshrivas.atlassian.net
  JIRA_EMAIL        your-atlassian-account-email
  JIRA_API_TOKEN    your-atlassian-api-token

Commands:
  search      --jql "project=HMS AND labels=GHAS AND statusCategory in ('To Do','In Progress')"
  create      --project HMS --summary "..." --priority High --labels "GHAS,HMS,security" --description-json /tmp/adf.json
  comment     --ticket HMS-16 --body "..." | --body-file /tmp/report.txt
  transitions --ticket HMS-16
  transition  --ticket HMS-16 --name "Done"
"""

import argparse
import base64
import json
import os
import sys

import requests

# ---------------------------------------------------------------------------
# Load .env from repo root if python-dotenv is available
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    for _level in range(4):
        _candidate = os.path.join(_script_dir, *(['..'] * _level), '.env')
        _candidate = os.path.normpath(_candidate)
        if os.path.isfile(_candidate):
            load_dotenv(_candidate)
            break
except ImportError:
    pass


def _get_auth():
    url = (os.environ.get('JIRA_URL') or os.environ.get('JIRA_BASE_URL') or '').rstrip('/')
    email = os.environ.get('JIRA_EMAIL', '')
    token = os.environ.get('JIRA_API_TOKEN', '')
    if not url or not email or not token:
        print(
            'ERROR: JIRA_URL (or JIRA_BASE_URL), JIRA_EMAIL, and JIRA_API_TOKEN must be set '
            'in the environment or in .env at the repo root.',
            file=sys.stderr,
        )
        sys.exit(1)
    cred = base64.b64encode(f'{email}:{token}'.encode()).decode()
    headers = {
        'Authorization': f'Basic {cred}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    return url, headers


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------
def cmd_search(args):
    url, headers = _get_auth()
    payload = {
        'jql': args.jql,
        'fields': ['summary', 'status', 'labels', 'priority', 'key'],
        'maxResults': 50,
    }
    r = requests.post(
        f'{url}/rest/api/3/issue/search',
        headers=headers,
        json=payload,
        timeout=30,
    )
    if not r.ok:
        print(f'ERROR {r.status_code}: {r.text}', file=sys.stderr)
        sys.exit(1)
    data = r.json()
    issues = [
        {
            'key': i['key'],
            'summary': i['fields']['summary'],
            'status': i['fields']['status']['name'],
        }
        for i in data.get('issues', [])
    ]
    print(json.dumps({'total': data.get('total', 0), 'issues': issues}, indent=2))


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------
def cmd_create(args):
    url, headers = _get_auth()
    labels = [l.strip() for l in args.labels.split(',')] if args.labels else []

    if args.description_json:
        with open(args.description_json, encoding='utf-8') as f:
            description = json.load(f)
    else:
        description = {
            'version': 1,
            'type': 'doc',
            'content': [
                {
                    'type': 'paragraph',
                    'content': [{'type': 'text', 'text': 'Auto-created by GHAS Vulnerability Management.'}],
                }
            ],
        }

    payload = {
        'fields': {
            'project': {'key': args.project},
            'summary': args.summary,
            'issuetype': {'name': 'Bug'},
            'priority': {'name': args.priority},
            'labels': labels,
            'description': description,
        }
    }
    r = requests.post(f'{url}/rest/api/3/issue', headers=headers, json=payload, timeout=30)
    if not r.ok:
        print(f'ERROR {r.status_code}: {r.text}', file=sys.stderr)
        sys.exit(1)
    data = r.json()
    print(json.dumps({
        'key': data['key'],
        'id': data['id'],
        'url': f"{url}/browse/{data['key']}",
    }))


# ---------------------------------------------------------------------------
# comment
# ---------------------------------------------------------------------------
def cmd_comment(args):
    url, headers = _get_auth()

    if args.body_file:
        with open(args.body_file, encoding='utf-8') as f:
            text = f.read()
    else:
        text = args.body

    # Wrap in ADF codeBlock to preserve ASCII art / monospace formatting
    adf_body = {
        'version': 1,
        'type': 'doc',
        'content': [
            {
                'type': 'codeBlock',
                'attrs': {'language': 'text'},
                'content': [{'type': 'text', 'text': text}],
            }
        ],
    }
    r = requests.post(
        f'{url}/rest/api/3/issue/{args.ticket}/comment',
        headers=headers,
        json={'body': adf_body},
        timeout=30,
    )
    if not r.ok:
        print(f'ERROR {r.status_code}: {r.text}', file=sys.stderr)
        sys.exit(1)
    data = r.json()
    print(json.dumps({'id': data['id'], 'created': data.get('created', '')}))


# ---------------------------------------------------------------------------
# transitions (list)
# ---------------------------------------------------------------------------
def cmd_transitions(args):
    url, headers = _get_auth()
    r = requests.get(
        f'{url}/rest/api/3/issue/{args.ticket}/transitions',
        headers=headers,
        timeout=30,
    )
    if not r.ok:
        print(f'ERROR {r.status_code}: {r.text}', file=sys.stderr)
        sys.exit(1)
    transitions = [
        {'id': t['id'], 'name': t['name']}
        for t in r.json().get('transitions', [])
    ]
    print(json.dumps({'transitions': transitions}, indent=2))


# ---------------------------------------------------------------------------
# transition (apply)
# ---------------------------------------------------------------------------
def cmd_transition(args):
    url, headers = _get_auth()
    r = requests.get(
        f'{url}/rest/api/3/issue/{args.ticket}/transitions',
        headers=headers,
        timeout=30,
    )
    if not r.ok:
        print(f'ERROR {r.status_code}: {r.text}', file=sys.stderr)
        sys.exit(1)
    transitions = r.json().get('transitions', [])
    match = next((t for t in transitions if args.name.lower() in t['name'].lower()), None)
    if not match:
        names = [t['name'] for t in transitions]
        print(
            f'ERROR: No transition matching "{args.name}". Available: {names}',
            file=sys.stderr,
        )
        sys.exit(1)
    payload = {'transition': {'id': match['id']}}
    r = requests.post(
        f'{url}/rest/api/3/issue/{args.ticket}/transitions',
        headers=headers,
        json=payload,
        timeout=30,
    )
    if not r.ok:
        print(f'ERROR {r.status_code}: {r.text}', file=sys.stderr)
        sys.exit(1)
    print(json.dumps({'transitioned': True, 'to': match['name']}))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='Jira REST API helper for GHAS workflows',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('search', help='JQL search for issues')
    p.add_argument('--jql', required=True)

    p = sub.add_parser('create', help='Create a new issue')
    p.add_argument('--project', required=True)
    p.add_argument('--summary', required=True)
    p.add_argument('--priority', default='High', choices=['Highest', 'High', 'Medium', 'Low', 'Lowest'])
    p.add_argument('--labels', default='', help='Comma-separated labels')
    p.add_argument('--description-json', dest='description_json',
                   help='Path to ADF JSON file for the issue description')

    p = sub.add_parser('comment', help='Post a comment on an issue')
    p.add_argument('--ticket', required=True)
    body_grp = p.add_mutually_exclusive_group(required=True)
    body_grp.add_argument('--body', help='Comment text (inline)')
    body_grp.add_argument('--body-file', dest='body_file', help='Path to file containing comment text')

    p = sub.add_parser('transitions', help='List available transitions for an issue')
    p.add_argument('--ticket', required=True)

    p = sub.add_parser('transition', help='Apply a transition to an issue')
    p.add_argument('--ticket', required=True)
    p.add_argument('--name', required=True, help='Transition name (case-insensitive partial match)')

    args = parser.parse_args()
    {
        'search': cmd_search,
        'create': cmd_create,
        'comment': cmd_comment,
        'transitions': cmd_transitions,
        'transition': cmd_transition,
    }[args.command](args)


if __name__ == '__main__':
    main()
