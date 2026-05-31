#!/usr/bin/env bash
# version-compare.sh — strict semver comparison.
#
# CC's marketplace does NOT parse semver — it treats `version` as opaque strings
# and only checks "did this string change?". WE OWN the semver semantics. This
# script implements them.
#
# Pre-release suffix sort order (per semver.org):
#   1.2.5 < 1.3.0-alpha < 1.3.0-alpha.1 < 1.3.0-alpha.beta < 1.3.0-beta
#   < 1.3.0-beta.2 < 1.3.0-beta.11 < 1.3.0-rc.1 < 1.3.0
#   1.3.0 < 1.3.1 < 2.0.0-rc.1 < 2.0.0
#
# Numeric identifiers in pre-release: compared numerically.
# Alphanumeric identifiers: compared lexicographically.
# Numeric identifiers always sort lower than alphanumeric (per spec § 11.4.3).
#
# Usage:
#   version-compare.sh <A> <B>
#     Prints: "lt" if A < B, "eq" if A == B, "gt" if A > B
#     Exit:   0 always (unless invalid input → exit 2 + stderr error)
#
#   version-compare.sh --bump <A> <B>
#     Prints: "patch" | "minor" | "major" | "downgrade" | "equal" | "prerelease"
#     Classifies the kind of bump from A → B.
#     "prerelease" = within the same MAJOR.MINOR.PATCH, prerelease suffix changed
#
# Test cases (run with --self-test): see end of file.

set -euo pipefail

# Parse "1.2.3-rc.4+build.5" into numeric, prerelease, build components
parse_semver() {
  local v="${1#v}"
  # Strip build metadata (ignored for ordering per semver § 10)
  v="${v%%+*}"
  # Split version and prerelease
  local main="${v%%-*}"
  local pre=""
  if [[ "$v" == *-* ]]; then
    pre="${v#*-}"
  fi
  # Split main into major.minor.patch
  IFS='.' read -ra parts <<< "$main"
  if [[ ${#parts[@]} -ne 3 ]]; then
    echo "ERROR: invalid semver: $1" >&2
    return 2
  fi
  for p in "${parts[@]}"; do
    if ! [[ "$p" =~ ^[0-9]+$ ]]; then
      echo "ERROR: invalid semver (non-numeric main component): $1" >&2
      return 2
    fi
  done
  echo "${parts[0]} ${parts[1]} ${parts[2]} ${pre}"
}

# Compare two prerelease identifiers (single identifier, not dot-separated list)
# Returns: -1, 0, 1
compare_identifier() {
  local a="$1" b="$2"
  if [[ "$a" =~ ^[0-9]+$ && "$b" =~ ^[0-9]+$ ]]; then
    # Numeric: integer compare
    if (( a < b )); then echo -1
    elif (( a > b )); then echo 1
    else echo 0
    fi
  elif [[ "$a" =~ ^[0-9]+$ ]]; then
    # Numeric always < alphanumeric (semver § 11.4.3)
    echo -1
  elif [[ "$b" =~ ^[0-9]+$ ]]; then
    echo 1
  else
    # Both alphanumeric: lexical
    if [[ "$a" < "$b" ]]; then echo -1
    elif [[ "$a" > "$b" ]]; then echo 1
    else echo 0
    fi
  fi
}

# Compare two prerelease strings (dot-separated identifier lists)
# Returns: -1 (a<b), 0 (a==b), 1 (a>b)
compare_prerelease() {
  local a_pre="$1" b_pre="$2"

  # Per semver § 11.3: "A version without a pre-release has higher precedence
  # than one with a pre-release." So no-prerelease > any prerelease.
  if [[ -z "$a_pre" && -z "$b_pre" ]]; then echo 0; return; fi
  if [[ -z "$a_pre" ]]; then echo 1; return; fi
  if [[ -z "$b_pre" ]]; then echo -1; return; fi

  IFS='.' read -ra a_ids <<< "$a_pre"
  IFS='.' read -ra b_ids <<< "$b_pre"

  local i max=${#a_ids[@]}
  if (( ${#b_ids[@]} > max )); then max=${#b_ids[@]}; fi

  for (( i=0; i<max; i++ )); do
    local ai="${a_ids[i]:-}"
    local bi="${b_ids[i]:-}"
    if [[ -z "$ai" ]]; then echo -1; return; fi
    if [[ -z "$bi" ]]; then echo 1; return; fi
    local r
    r=$(compare_identifier "$ai" "$bi")
    if [[ "$r" != "0" ]]; then echo "$r"; return; fi
  done
  echo 0
}

# Compare two full semver strings.
# Returns "lt", "eq", or "gt".
compare_semver() {
  local a_parts b_parts
  a_parts=$(parse_semver "$1") || return 2
  b_parts=$(parse_semver "$2") || return 2

  read -r a_maj a_min a_pat a_pre <<< "$a_parts"
  read -r b_maj b_min b_pat b_pre <<< "$b_parts"

  if (( a_maj < b_maj )); then echo lt; return; fi
  if (( a_maj > b_maj )); then echo gt; return; fi
  if (( a_min < b_min )); then echo lt; return; fi
  if (( a_min > b_min )); then echo gt; return; fi
  if (( a_pat < b_pat )); then echo lt; return; fi
  if (( a_pat > b_pat )); then echo gt; return; fi

  # Same X.Y.Z — compare prereleases
  local r
  r=$(compare_prerelease "$a_pre" "$b_pre")
  case "$r" in
    -1) echo lt ;;
    0)  echo eq ;;
    1)  echo gt ;;
  esac
}

# Classify a bump from A → B.
classify_bump() {
  local a="$1" b="$2"
  local cmp
  cmp=$(compare_semver "$a" "$b")
  if [[ "$cmp" == "eq" ]]; then echo equal; return; fi
  if [[ "$cmp" == "gt" ]]; then echo downgrade; return; fi

  # a < b: figure out the granularity of the bump
  local a_parts b_parts
  a_parts=$(parse_semver "$a")
  b_parts=$(parse_semver "$b")
  read -r a_maj a_min a_pat a_pre <<< "$a_parts"
  read -r b_maj b_min b_pat b_pre <<< "$b_parts"

  if (( b_maj > a_maj )); then echo major; return; fi
  if (( b_min > a_min )); then echo minor; return; fi
  if (( b_pat > a_pat )); then echo patch; return; fi
  # Same X.Y.Z, b > a → prerelease moved forward (e.g. rc.1 → rc.2 or rc.5 → stable)
  echo prerelease
}

# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--self-test" ]]; then
  declare -a tests=(
    "1.0.0 1.0.0 eq"
    "1.0.0 1.0.1 lt"
    "1.0.1 1.0.0 gt"
    "1.0.0 2.0.0 lt"
    "1.0.0-rc.1 1.0.0 lt"
    "1.0.0-rc.1 1.0.0-rc.2 lt"
    "1.0.0-rc.2 1.0.0-rc.10 lt"
    "1.0.0-alpha 1.0.0-beta lt"
    "1.0.0-alpha.1 1.0.0-alpha.2 lt"
    "1.0.0-1 1.0.0-alpha lt"
    "v1.2.3 1.2.3 eq"
    "1.0.0+build.1 1.0.0+build.2 eq"
  )
  fail=0
  for t in "${tests[@]}"; do
    read -r a b expected <<< "$t"
    got=$(compare_semver "$a" "$b")
    if [[ "$got" == "$expected" ]]; then
      echo "  PASS: compare $a $b → $got"
    else
      echo "  FAIL: compare $a $b → got '$got' expected '$expected'"
      fail=1
    fi
  done

  declare -a bump_tests=(
    "1.0.0 1.0.0 equal"
    "1.0.0 1.0.1 patch"
    "1.0.0 1.1.0 minor"
    "1.0.0 2.0.0 major"
    "1.0.0 0.9.0 downgrade"
    "1.0.0-rc.1 1.0.0-rc.2 prerelease"
    "1.0.0-rc.1 1.0.0 prerelease"
    "1.2.5 1.3.0-rc.1 minor"
  )
  for t in "${bump_tests[@]}"; do
    read -r a b expected <<< "$t"
    got=$(classify_bump "$a" "$b")
    if [[ "$got" == "$expected" ]]; then
      echo "  PASS: bump $a → $b: $got"
    else
      echo "  FAIL: bump $a → $b: got '$got' expected '$expected'"
      fail=1
    fi
  done

  exit $fail
fi

case "${1:-}" in
  --bump)
    shift
    classify_bump "$1" "$2"
    ;;
  "")
    echo "usage: version-compare.sh <A> <B>" >&2
    echo "       version-compare.sh --bump <A> <B>" >&2
    echo "       version-compare.sh --self-test" >&2
    exit 2
    ;;
  *)
    compare_semver "$1" "$2"
    ;;
esac
