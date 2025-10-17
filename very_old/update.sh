#!/bin/bash
# Initialize the repository by pulling the latest changes from the remote repository
git pull origin main
# Add all changes to the staging area
git add .
# Commit the changes with a message
git commit -m "update"
# Push the changes to the remote repository
git push origin main
# --- IGNORE ---