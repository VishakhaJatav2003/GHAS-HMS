#!/bin/sh
set -eu

# ---------------------------------------------------------------------------
# PATH bootstrap — add gh and jq to PATH if not already visible
# ---------------------------------------------------------------------------
if ! command -v gh >/dev/null 2>&1; then
  if [ -f "/c/Program Files/GitHub CLI/gh.exe" ]; then
    export PATH="/c/Program Files/GitHub CLI:$PATH"
  else
    echo "ERROR: gh CLI not found. Install from https://cli.github.com" >&2
    exit 1
  fi
fi

if ! command -v jq >/dev/null 2>&1; then
  for _jq_dir in \
    "/c/Users/TanishqShrivas/.local/bin" \
    "/c/ProgramData/chocolatey/bin" \
    "/usr/local/bin" \
    "/usr/bin"; do
    if [ -f "$_jq_dir/jq" ] || [ -f "$_jq_dir/jq.exe" ]; then
      export PATH="$_jq_dir:$PATH"
      break
    fi
  done
  if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq not found. Install from https://jqlang.github.io/jq/" >&2
    exit 1
  fi
fi

# Default path (Windows Git Bash format) — timestamped so each run produces a unique file
DEFAULT_OUT_PATH="/c/Users/TanishqShrivas/DummyProj/GHAS-dummy-projects/HMS/github_alerts_$(date +%Y%m%d_%H%M%S).csv"

if [ "$#" -gt 1 ]; then
  echo "Usage: $0 [output.csv]" >&2
  exit 2
fi

out_path="${1:-$DEFAULT_OUT_PATH}"
mkdir -p "$(dirname "$out_path")"

# ---------------------------------------------------------------------------
# Cleanup — remove CSV files from previous runs before writing a fresh one
# ---------------------------------------------------------------------------
_repo_dir="$(dirname "$out_path")"
for _old_csv in "$_repo_dir"/github_alerts_*.csv; do
  [ -f "$_old_csv" ] && rm -f "$_old_csv" && echo "Removed old CSV: $_old_csv" >&2
done

printf '%s\n' 'service,type,ghsa_id,cve_id,title,severity,created,due,url,Application,nonCompliant,ageDays' > "$out_path"

_gh_out=$(mktemp)
_gh_err=$(mktemp)
trap 'rm -f "$_gh_out" "$_gh_err"' EXIT

_total_rows=0

_count_rows() {
  if [ -s "$_gh_out" ]; then
    wc -l < "$_gh_out" | tr -d ' '
  else
    printf '0'
  fi
}

for entry in \
  "HMS Hospital-Management-System" \
; do

  svc="${entry%% *}"
  Application="${entry#* }"

  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
  echo "Service: $svc" >&2

  # =======================
  # Dependabot
  # =======================
  echo "  [1/3] Fetching Dependabot alerts..." >&2
  if gh api "repos/tanishq-sh17/${svc}/dependabot/alerts?state=open&per_page=100" --paginate \
    --jq '.[] |
      .created_at as $created |
      (.security_advisory.severity // "") as $s |
      (if $s == "critical" then ($created | fromdateiso8601 + 1296000 | strftime("%Y-%m-%d"))
       elif $s == "high" then ($created | fromdateiso8601 + 2592000 | strftime("%Y-%m-%d"))
       elif $s == "medium" then ($created | fromdateiso8601 + 7776000 | strftime("%Y-%m-%d"))
       elif $s == "low" then ($created | fromdateiso8601 + 10368000 | strftime("%Y-%m-%d"))
       else "" end) as $due |
      (((now - ($created | fromdateiso8601)) / 86400) | floor) as $age |
      {
        type: "dependabot",
        ghsa_id: (.security_advisory.ghsa_id // ""),
        cve_id: ((.security_advisory.identifiers[]? | select(.type=="CVE") | .value) // ""),
        title: (.security_advisory.summary // ""),
        severity: $s,
        created: ($created | fromdateiso8601 | strftime("%Y-%m-%d")),
        due: $due,
        url: (.html_url // ""),
        non_compliant: (if $s=="critical" and $age>15 then 1
                        elif $s=="high" and $age>30 then 1
                        elif $s=="medium" and $age>90 then 1
                        elif $s=="low" and $age>120 then 1 else 0 end),
        age_days: $age
      }' > "$_gh_out" 2>"$_gh_err"; then

    _n=$(_count_rows)
    jq -rc --arg svc "$svc" --arg Application "$Application" \
      '. | [$svc,.type,.ghsa_id,.cve_id,.title,.severity,.created,.due,.url,$Application,.non_compliant,.age_days] | @csv' \
      "$_gh_out" >> "$out_path"
    echo "  ✓ Dependabot: $_n alert(s) found" >&2
    _total_rows=$(( _total_rows + _n ))
  else
    _err=$(cat "$_gh_err" 2>/dev/null | head -3)
    echo "  ✗ Dependabot fetch failed: $_err" >&2
  fi

  # =======================
  # Code Scanning
  # =======================
  echo "  [2/3] Fetching Code Scanning alerts..." >&2
  if gh api "repos/tanishq-sh17/${svc}/code-scanning/alerts?state=open&per_page=100" --paginate \
    --jq '.[] |
      .created_at as $created |
      ((.rule.security_severity_level // .rule.severity // .severity //"") | ascii_downcase) as $s |
      (((now - ($created | fromdateiso8601)) / 86400) | floor) as $age |
      {
        type:"code-scanning",
        ghsa_id:"",
        cve_id:"",
        title:(.rule.description // .rule.name // ""),
        severity:$s,
        created:($created | fromdateiso8601 | strftime("%Y-%m-%d")),
        due:"",
        url:(.html_url // ""),
        non_compliant:0,
        age_days:$age
      }' > "$_gh_out" 2>"$_gh_err"; then

    _n=$(_count_rows)
    jq -rc --arg svc "$svc" --arg Application "$Application" \
      '. | [$svc,.type,.ghsa_id,.cve_id,.title,.severity,.created,.due,.url,$Application,.non_compliant,.age_days] | @csv' \
      "$_gh_out" >> "$out_path"
    echo "  ✓ Code Scanning: $_n alert(s) found" >&2
    _total_rows=$(( _total_rows + _n ))
  else
    _err=$(cat "$_gh_err" 2>/dev/null | head -3)
    echo "  ✗ Code Scanning fetch failed (may not be enabled): $_err" >&2
  fi

  # =======================
  # Secret Scanning
  # =======================
  echo "  [3/3] Fetching Secret Scanning alerts..." >&2
  if gh api "repos/tanishq-sh17/${svc}/secret-scanning/alerts?state=open&per_page=100" --paginate \
    --jq '.[] |
      .created_at as $created |
      ((.severity // .rule.severity //"") | ascii_downcase) as $s |
      (((now - ($created | fromdateiso8601)) / 86400) | floor) as $age |
      {
        type:"secret-scanning",
        ghsa_id:"",
        cve_id:"",
        title:(.secret_type_display_name // .secret_type // ""),
        severity:$s,
        created:($created | fromdateiso8601 | strftime("%Y-%m-%d")),
        due:"",
        url:(.html_url // ""),
        non_compliant:0,
        age_days:$age
      }' > "$_gh_out" 2>"$_gh_err"; then

    _n=$(_count_rows)
    jq -rc --arg svc "$svc" --arg Application "$Application" \
      '. | [$svc,.type,.ghsa_id,.cve_id,.title,.severity,.created,.due,.url,$Application,.non_compliant,.age_days] | @csv' \
      "$_gh_out" >> "$out_path"
    echo "  ✓ Secret Scanning: $_n alert(s) found" >&2
    _total_rows=$(( _total_rows + _n ))
  else
    _err=$(cat "$_gh_err" 2>/dev/null | head -3)
    echo "  ✗ Secret Scanning fetch failed (may not be enabled): $_err" >&2
  fi

done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
echo "Total alerts written: $_total_rows" >&2
printf '%s\n' "Wrote CSV to: $out_path"
