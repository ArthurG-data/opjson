#!/usr/bin/env bash
# Build the release files and attach them to the GitHub release of a tag, creating the release if it is missing.
#
#     tools/release.sh v0.3.1 [<commit>]
#
# A pushed tag, or a release published in the UI, already exists: its files are replaced (--clobber, so a second
# run is safe). A new version from CI does not: the release is created at <commit>, which also creates its tag.
# Needs uv, gh and GH_TOKEN. build.py stamps the release with today's date and the version from the tag.
set -euo pipefail
cd "$(dirname "$0")/.."

TAG=$1
TARGET=${2:-}
uv run python tools/build.py --version "${TAG#v}"
files=()
for name in AllSets AllCards AllPrintings AllProducts AllUuids Legality; do
    files+=("dist/$name.json")
done
if gh release view "$TAG" > /dev/null 2>&1; then
    gh release upload "$TAG" "${files[@]}" --clobber
else
    gh release create "$TAG" "${files[@]}" --generate-notes ${TARGET:+--target "$TARGET"}
fi
