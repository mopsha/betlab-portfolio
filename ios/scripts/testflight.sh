#!/bin/sh
# Archive BetLab, sign it for the App Store and upload it to App Store Connect for TestFlight. Signing and the upload use
# Mike's App Store Connect API key (Oct 14), so Xcode's sign-in can't lapse mid-upload: the .p8 lives only on the Mac in
# ~/.appstoreconnect/private_keys/ (never in the repo); its key id and issuer id below aren't secret. Each upload gets a new build number
# (the git commit count), as App Store Connect requires. Run from anywhere: sh ios/scripts/testflight.sh
set -eu
ios=$(cd "$(dirname "$0")/.." && pwd)
cd "$ios"
build=$(git rev-list --count HEAD)
key_id=YOUR_KEY_ID
issuer=YOUR_ISSUER_ID
key="$HOME/.appstoreconnect/private_keys/AuthKey_$key_id.p8"
[ -f "$key" ] || { echo "No App Store Connect key at $key (Mike downloads it from App Store Connect > Users and Access > Integrations)"; exit 1; }
auth="-authenticationKeyPath $key -authenticationKeyID $key_id -authenticationKeyIssuerID $issuer"
out="$ios/build/testflight"
rm -rf "$out"
mkdir -p "$out"
cat > "$out/export.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>app-store-connect</string>
  <key>destination</key><string>upload</string>
  <key>teamID</key><string>YOUR_TEAM_ID</string>
  <key>signingStyle</key><string>automatic</string>
  <key>manageAppVersionAndBuildNumber</key><false/>
</dict></plist>
PLIST
# each step's full log goes to a file; a failure stops the script with its last lines (a pipe to tail would hide it)
if ! xcodebuild -project BetLab.xcodeproj -scheme BetLab -configuration Release -destination 'generic/platform=iOS' \
     -archivePath "$out/BetLab.xcarchive" -allowProvisioningUpdates $auth CURRENT_PROJECT_VERSION="$build" archive > "$out/archive.log" 2>&1; then
  tail -20 "$out/archive.log"; echo "Archive failed (full log: $out/archive.log)"; exit 1
fi
# Xcode's own upload with the key fails ("Cannot verify client's JWT headers", Oct 14-15) though the key is a valid Admin
# team key: altool authenticates with it fine. So Xcode signs and exports the .ipa with the key, altool uploads it, and
# only if that fails does Xcode's signed-in account upload the archive.
sed 's#<string>upload</string>#<string>export</string>#' "$out/export.plist" > "$out/export_ipa.plist"
if xcodebuild -exportArchive -archivePath "$out/BetLab.xcarchive" -exportOptionsPlist "$out/export_ipa.plist" \
     -exportPath "$out/ipa" -allowProvisioningUpdates $auth > "$out/export.log" 2>&1 \
   && xcrun altool --upload-app -f "$out/ipa/BetLab.ipa" -t ios --apiKey "$key_id" --apiIssuer "$issuer" > "$out/upload.log" 2>&1; then
  :
else
  grep -E "error|ERROR" "$out/export.log" "$out/upload.log" 2>/dev/null | tail -3
  echo "The API key export or upload failed; trying Xcode's signed-in account"
  if ! xcodebuild -exportArchive -archivePath "$out/BetLab.xcarchive" -exportOptionsPlist "$out/export.plist" \
       -exportPath "$out/export" -allowProvisioningUpdates > "$out/upload_xcode.log" 2>&1; then
    grep -E "error|Error" "$out/upload_xcode.log" | tail -10
    echo "Upload failed both ways (logs in $out). If it says \"Failed to Use Accounts\", Mike re-signs in Xcode > Settings > Accounts."
    exit 1
  fi
fi
echo "Uploaded build $build. App Store Connect processes it in about 5-15 minutes; then it shows in TestFlight."
