#!/bin/sh
# The commit an image is built from: /health's `version`, the error tracker's release.
#
#   sh build-commit.sh <git dir> [<GIT_SHA build arg>]
#
# Prints a commit (exactly 40 lowercase hex digits) or "unknown", nothing else:
#   1. the build arg, when it is a commit: CI's `docker build --build-arg GIT_SHA=$GITHUB_SHA`;
#   2. else the commit HEAD names in <git dir>, detached or through its branch (the ref's own
#      file, else its line in packed-refs): Dokploy, whose depth-1 clone reaches the build as
#      the named context `gitmeta` (docker-compose.dokploy.yml; the root .dockerignore lets
#      only .git/HEAD, .git/refs and .git/packed-refs through);
#   3. else "unknown": the E2E stack, a bare `docker build` (`gitmeta` is then the empty
#      `FROM scratch` stage of the Dockerfile).
#
# POSIX sh, no git: dash in the backend image, BusyBox ash in nginx's. The file exists twice,
# backend/scripts/ and front/scripts/, because each image's build context is its own
# directory; backend/tests/api/test_build_commit.py runs it and checks the two are the same.

is_commit() {
    [ "${#1}" -eq 40 ] || return 1
    case "$1" in
        *[!0-9a-f]*) return 1 ;;
    esac
    return 0
}

if is_commit "${2:-}"; then
    printf '%s\n' "$2"
    exit 0
fi

git_dir="${1:-}"
commit=""
head_ref="$(cat "$git_dir/HEAD" 2>/dev/null)" || head_ref=""
case "$head_ref" in
    "ref: refs/"*)
        ref="${head_ref#ref: }"
        case "$ref" in
            *..*) ref="" ;;
        esac
        if [ -n "$ref" ]; then
            commit="$(cat "$git_dir/$ref" 2>/dev/null)" || commit=""
            if ! is_commit "$commit" && [ -f "$git_dir/packed-refs" ]; then
                commit=""
                while read -r sha name; do
                    if [ "$name" = "$ref" ]; then
                        commit="$sha"
                        break
                    fi
                done < "$git_dir/packed-refs"
            fi
        fi
        ;;
    "ref: "*) ;;
    *) commit="$head_ref" ;;
esac

if is_commit "$commit"; then
    printf '%s\n' "$commit"
else
    echo unknown
fi
