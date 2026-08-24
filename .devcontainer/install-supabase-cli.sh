#!/usr/bin/env bash
# Codespaces postCreateCommand: install the Supabase CLI on the Codespace host,
# matching this repo's convention (AGENTS.md 11.1: "Supabase CLI はホスト側").
# Runs once when the Codespace container is created.
set -euo pipefail

echo "Installing Supabase CLI..."
curl -fsSL https://github.com/supabase/cli/releases/latest/download/supabase_linux_amd64.deb -o /tmp/supabase.deb
sudo dpkg -i /tmp/supabase.deb
rm -f /tmp/supabase.deb
supabase --version
