#!/bin/sh
# Writes ios/Config/Secrets.xcconfig from web/.env.local (the same Supabase address and public anon key the
# web app uses). It never prints the values. Run from anywhere: sh ios/scripts/make_secrets.sh
set -eu
root=$(cd "$(dirname "$0")/../.." && pwd)
src="$root/web/.env.local"
out="$root/ios/Config/Secrets.xcconfig"
[ -f "$src" ] || { echo "web/.env.local not found: copy it from the PC first"; exit 1; }
val() { sed -n "s/^$1=//p" "$src" | tail -1 | tr -d '"\r'; }
url=$(val NEXT_PUBLIC_SUPABASE_URL)
key=$(val NEXT_PUBLIC_SUPABASE_ANON_KEY)
[ -n "$url" ] && [ -n "$key" ] || { echo "web/.env.local is missing the Supabase URL or anon key"; exit 1; }
# xcconfig treats // as a comment, so the scheme's slashes are split with an empty variable
url=$(printf %s "$url" | sed 's#://#:/$()/#')
umask 077
printf '// Written by ios/scripts/make_secrets.sh; git ignores it.\nSUPABASE_URL = %s\nSUPABASE_ANON_KEY = %s\n' "$url" "$key" > "$out"
echo "Wrote ios/Config/Secrets.xcconfig (Supabase URL: set, anon key: set)"
