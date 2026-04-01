#!/bin/bash
# Collect git project status and output data/projects.json

OUTPUT=~/projects/openclaw-dashboard/data/projects.json
NOW=$(date -Iseconds)

PROJECTS=(
  "helloquant:$HOME/trading/helloquant"
  "openclaw-dashboard:$HOME/projects/openclaw-dashboard"
  "autonomous-driving:$HOME/projects/autonomous-driving"
  "researchhub:$HOME/projects/researchhub"
  "kliai:$HOME/projects/backend/kliai"
  "ai-tools:$HOME/projects/ai-tools"
)

echo '{"updated_at":"'"$NOW"'","projects":[' > "$OUTPUT"

FIRST=true
for entry in "${PROJECTS[@]}"; do
  NAME="${entry%%:*}"
  DIR="${entry#*:}"

  if [ ! -d "$DIR/.git" ]; then
    continue
  fi

  cd "$DIR" 2>/dev/null || continue

  BRANCH=$(git branch --show-current 2>/dev/null || echo "detached")
  UNCOMMITTED=$(git status --porcelain 2>/dev/null | wc -l)
  LAST_COMMIT=$(git log -1 --format="%ar — %s" 2>/dev/null | head -c 80 || echo "no commits")

  # Escape JSON strings
  LAST_COMMIT=$(echo "$LAST_COMMIT" | sed 's/"/\\"/g')

  if [ "$FIRST" = true ]; then
    FIRST=false
  else
    echo ',' >> "$OUTPUT"
  fi

  cat >> "$OUTPUT" << ENTRY
{"name":"$NAME","path":"$DIR","branch":"$BRANCH","uncommitted":$UNCOMMITTED,"last_commit":"$LAST_COMMIT","status":"active"}
ENTRY

done

echo ']}' >> "$OUTPUT"

echo "Updated $OUTPUT"
