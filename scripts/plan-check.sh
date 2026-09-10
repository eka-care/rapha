#!/bin/sh
# Fails when the plan has changed but the manifest, the compiled skills, or a
# cited section id has not kept up. Run in CI and before any plugin release.
# No deps beyond shasum, sed and grep.
set -e
cd "$(dirname "$0")/.."

plan=$(sed -n 's/.*"plan_path": "\([^"]*\)".*/\1/p' manifest.json)
want=$(sed -n 's/.*"plan_hash": "sha256:\([^"]*\)".*/\1/p' manifest.json)
ver=$(sed -n 's/.*"plan_version": "\([^"]*\)".*/\1/p' manifest.json)
have=$(shasum -a 256 "$plan" | cut -d' ' -f1)
fail=0

# 1. the plan matches what the manifest declares
if [ "$have" != "$want" ]; then
  echo "FAIL plan changed but manifest.json was not bumped"
  echo "  plan:     $plan"
  echo "  manifest: sha256:$want (plan_version $ver)"
  echo "  actual:   sha256:$have"
  echo "  fix: copy the old plan into plan-history/, bump plan_version and plan_hash,"
  echo "       recompile the plan-derived skills, set breaking if a principle,"
  echo "       a date, an owner or a done criterion changed."
  fail=1
else
  echo "ok   plan matches manifest, plan_version $ver"
fi

# 2. every compiled skill is stamped with that version and hash
for s in $(sed -n 's/^    "\([a-z-]*\)".*/\1/p' manifest.json); do
  f="plugin/skills/$s/SKILL.md"
  [ -f "$f" ] || { echo "FAIL $s named in compiled_skills but $f is missing"; fail=1; continue; }
  got=$(sed -n 's/^plan_version: *//p' "$f")
  goth=$(sed -n 's/^plan_hash: *sha256://p' "$f")
  if [ "$got" != "$ver" ]; then
    echo "FAIL $s stamped plan_version '$got', manifest says '$ver'"
    fail=1
  elif [ "$goth" != "$want" ]; then
    echo "FAIL $s stamped a plan_hash that is not the manifest's"
    fail=1
  else
    echo "ok   $s built from plan_version $got"
  fi
done

# 3. the gantt generator is built from that version too. Its TASKS table is
#    compiled from plan#p8-schedule, so a schedule change that misses it ships a
#    gantt partners read as current.
g=plan-archive/gantt/build_gantt.py
if [ ! -f "$g" ]; then
  echo "warn $g missing, no gantt to check"
else
  gver=$(sed -n 's/^PLAN_VERSION = "\(.*\)"$/\1/p' "$g")
  if [ "$gver" != "$ver" ]; then
    echo "FAIL $g stamped PLAN_VERSION '$gver', manifest says '$ver'"
    echo "  fix: update the TASKS table to match plan#p8-schedule, restamp,"
    echo "       rebuild with --status and re-import into the shared Sheet."
    fail=1
  else
    echo "ok   gantt built from plan_version $gver"
  fi
fi

# 4. every plan#id cited anywhere in the plugin exists in the plan
#    ponytail: grep, not a markdown parser. Fine while ids are plain anchor tags.
for id in $(grep -rho 'plan#[a-z0-9.-]*' plugin/ plan-archive/gantt/ | sed -e 's/^plan#//' -e 's/\.$//' | sort -u); do
  if grep -q "<a id=\"$id\"></a>" "$plan"; then
    echo "ok   plan#$id resolves"
  else
    echo "FAIL plan#$id cited in the plugin but no such section id in $plan"
    fail=1
  fi
done

# 5. the version being replaced was archived, not overwritten
if [ ! -d plan-archive/plan-history ]; then
  echo "warn plan-history/ missing, nothing archived yet"
elif [ -z "$(ls -A plan-archive/plan-history 2>/dev/null)" ]; then
  echo "warn plan-history/ is empty, nothing archived yet"
else
  echo "ok   plan-history/ holds $(ls plan-archive/plan-history | wc -l | tr -d ' ') superseded version(s)"
fi

exit $fail
