#!/usr/bin/env bash
set -euo pipefail

: "${TAG:?TAG is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"

# Check the complete, authenticated release list: the tag endpoint alone does not
# reliably find drafts. A failed request or malformed response must stop the run.
releases_for_tag() {
  gh api --paginate --slurp "repos/$GITHUB_REPOSITORY/releases?per_page=100" |
    jq --arg tag "$TAG" '
      if type != "array" or (all(.[]; type == "array") | not) then
        error("Unexpected releases response")
      else
        (add // []) |
        if all(.[]; type == "object" and (.tag_name | type == "string") and
                     (.id | type == "number") and (.draft | type == "boolean")) then
          map(select(.tag_name == $tag))
        else
          error("Unexpected release entry")
        end
      end'
}

assert_our_only_draft() {
  local releases
  releases=$(releases_for_tag)
  if ! jq -e --argjson id "$release_id" \
    'length == 1 and .[0].id == $id and .[0].draft == true' <<<"$releases" >/dev/null; then
    echo "Release state changed for $TAG; leaving our draft $release_id untouched." >&2
    exit 1
  fi
}

# Fail before creating a draft if a build artifact is missing or empty.
assets=(
  release-assets/tesseract-arm64-linux.tar.gz
  release-assets/tesseract-x64-linux.tar.gz
  release-assets/tesseract-x64-windows-static.zip
  release-assets/tesseract-arm64-osx.tar.gz
)
for asset in "${assets[@]}"; do
  if [[ ! -s "$asset" || ! -f "$asset" ]]; then
    echo "Missing or empty release asset: $asset" >&2
    exit 1
  fi
done

releases=$(releases_for_tag)
if ! jq -e 'length == 0' <<<"$releases" >/dev/null; then
  echo "A release or draft already exists for $TAG; refusing to modify it." >&2
  exit 1
fi

# Do not let the releases API create a tag if it has been deleted since the push.
git ls-remote --exit-code origin "refs/tags/$TAG" >/dev/null

# Create, never look up by tag for mutation. GitHub may allow multiple drafts
# for one tag, so recheck after creation and address only the returned release ID.
created=$(gh api --method POST "repos/$GITHUB_REPOSITORY/releases" \
  -f tag_name="$TAG" -f name="$TAG" -F draft=true -F generate_release_notes=true)
release_id=$(jq -er --arg tag "$TAG" \
  'select(.tag_name == $tag and .draft == true) | .id | select(type == "number" and . > 0 and floor == .)' <<<"$created")
printf 'Created draft %s for %s\n' "$release_id" "$TAG"
assert_our_only_draft

for asset in "${assets[@]}"; do
  # --input streams the file; include its length as required by the upload API.
  gh api --method POST \
    "https://uploads.github.com/repos/$GITHUB_REPOSITORY/releases/$release_id/assets" \
    -H 'Content-Type: application/octet-stream' \
    -H "Content-Length: $(wc -c < "$asset" | tr -d '[:space:]')" \
    --input "$asset" -f "name=${asset##*/}" >/dev/null
done

# Refuse to publish if another release appeared or our draft changed meanwhile.
assert_our_only_draft
gh api --method PATCH "repos/$GITHUB_REPOSITORY/releases/$release_id" \
  -F draft=false >/dev/null
printf 'Published release %s for %s\n' "$release_id" "$TAG"
