#!/usr/bin/env bash
# ============================================================================
#  cleanup_venv_history.sh
#  Remove .venv/ from the ENTIRE git history of Traffic_controll_system
#
#  ⚠️  THIS REWRITES HISTORY — every collaborator must re-clone afterwards.
#  ⚠️  Back up the repo before running this script.
# ============================================================================

set -euo pipefail

REPO_DIR="/Users/akash/Desktop/minor"   # adjust if needed
REMOTE_URL="origin"                      # your GitHub remote name

cd "$REPO_DIR"

echo "============================================"
echo "  Step 0 — Safety: create a full backup"
echo "============================================"
BACKUP_DIR="${REPO_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
cp -R "$REPO_DIR" "$BACKUP_DIR"
echo "✅ Backup created at: $BACKUP_DIR"

echo ""
echo "============================================"
echo "  Step 1 — Untrack .venv/ from the index"
echo "============================================"
# Remove from Git's index without deleting the local folder
git rm -r --cached .venv/ 2>/dev/null || echo "ℹ️  .venv/ was not in the index (already untracked)"

echo ""
echo "============================================"
echo "  Step 2 — Ensure .venv/ is in .gitignore"
echo "============================================"
if grep -qxF '.venv/' .gitignore 2>/dev/null; then
    echo "✅ .venv/ already in .gitignore"
else
    echo '.venv/' >> .gitignore
    echo "✅ Added .venv/ to .gitignore"
fi

echo ""
echo "============================================"
echo "  Step 3 — Commit the untrack + .gitignore"
echo "============================================"
git add .gitignore
git commit -m "chore: untrack .venv/ and update .gitignore" --allow-empty

echo ""
echo "============================================"
echo "  Step 4 — Rewrite history with git filter-repo"
echo "============================================"
# Install git-filter-repo if not present:
#   brew install git-filter-repo          (macOS)
#   pip install git-filter-repo           (any platform)
#
# If you prefer BFG Repo Cleaner instead, replace this step with:
#   java -jar bfg.jar --delete-folders .venv --no-blob-protection .
#   git reflog expire --expire=now --all
#   git gc --prune=now --aggressive

if command -v git-filter-repo &>/dev/null; then
    echo "Using git-filter-repo..."
    git filter-repo --invert-paths --path .venv/ --force
else
    echo "❌ git-filter-repo not found."
    echo "   Install it with:  brew install git-filter-repo"
    echo "   Or with:          pip install git-filter-repo"
    echo ""
    echo "   Alternatively, use BFG Repo Cleaner:"
    echo "   java -jar bfg.jar --delete-folders .venv --no-blob-protection ."
    echo "   git reflog expire --expire=now --all"
    echo "   git gc --prune=now --aggressive"
    exit 1
fi

echo ""
echo "============================================"
echo "  Step 5 — Clean up refs and garbage-collect"
echo "============================================"
git reflog expire --expire=now --all
git gc --prune=now --aggressive
echo "✅ Repo cleaned and compacted"

echo ""
echo "============================================"
echo "  Step 6 — Re-add remote (filter-repo removes it)"
echo "============================================"
# git-filter-repo strips remotes for safety; re-add yours
git remote add "$REMOTE_URL" "https://github.com/Akash243-Sadhukhan/Traffic_controll_system.git" 2>/dev/null \
    || echo "ℹ️  Remote '$REMOTE_URL' already exists"

echo ""
echo "============================================"
echo "  Step 7 — Force push ALL branches"
echo "============================================"
echo "⚠️  This will overwrite the remote history!"
read -rp "   Proceed with force push? (y/N): " confirm
if [[ "$confirm" =~ ^[Yy]$ ]]; then
    git push "$REMOTE_URL" --force --all
    git push "$REMOTE_URL" --force --tags
    echo "✅ Force push complete"
else
    echo "⏭️  Skipped force push. Run manually when ready:"
    echo "   git push origin --force --all"
    echo "   git push origin --force --tags"
fi

echo ""
echo "============================================"
echo "  🔔 IMPORTANT: Notify all collaborators!"
echo "============================================"
cat <<'EOF'

All collaborators MUST re-clone the repository:

  1. Delete their local copy
  2. Clone fresh:

     git clone https://github.com/Akash243-Sadhukhan/Traffic_controll_system.git

  ⚠️  DO NOT run `git pull` on an old clone — it will
     re-introduce the old history and cause conflicts.

EOF

echo "✅ Done! .venv/ has been purged from all history."
