#!/system/bin/sh
# Capture diagnostics only; no privilege-escalation payload is executed here.
set -eu
D="$1"
PREFIX=/data/local/tmp/nx819j-publish-
SUFFIX=${D#"$PREFIX"}
[ "$SUFFIX" != "$D" ] && [ "${#SUFFIX}" -eq 32 ] || exit 90
case "$SUFFIX" in *[!0-9a-f]*) exit 90;; esac
T=/sys/kernel/tracing
ORIG_EVENT=$(cat "$T/events/sched/sched_blocked_reason/enable")
ORIG_ON=$(cat "$T/tracing_on")
READERS=""
restore() {
  for p in $READERS; do kill "$p" 2>/dev/null || :; done
  wait 2>/dev/null || :
  printf '%s\n' "$ORIG_EVENT" > "$T/events/sched/sched_blocked_reason/enable"
  printf '%s\n' "$ORIG_ON" > "$T/tracing_on"
}
trap restore EXIT INT TERM HUP
mkdir -p "$D/bl"
cat /proc/sys/kernel/random/boot_id > "$D/bl/boot_id.txt"
cat "$T/events/sched/sched_blocked_reason/format" > "$D/bl/event-format.txt"
chmod 755 "$D/forker" "$D/prep_solve"
echo 1 > "$T/events/sched/sched_blocked_reason/enable"
echo 1 > "$T/tracing_on"
i=0
while [ "$i" -lt 100 ]; do "$D/forker" 2 30 >/dev/null 2>&1; i=$((i+1)); done
# This non-consuming snapshot must precede the raw pipe readers.
grep sched_blocked_reason "$T/trace" > "$D/bl/bl_text.txt" || :
echo "TEXT_ANCHOR_LINES=$(wc -l < "$D/bl/bl_text.txt")"
for c in 0 1 2 3 4 5 6 7; do
  cat "$T/per_cpu/cpu$c/trace_pipe_raw" > "$D/bl/bl_$c.bin" 2>"$D/bl/cpu$c.err" &
  READERS="$READERS $!"
done
i=0
while [ "$i" -lt 100 ]; do "$D/forker" 2 30 >/dev/null 2>&1; i=$((i+1)); done
sleep 1
for p in $READERS; do kill "$p" 2>/dev/null || :; done
wait 2>/dev/null || :
READERS=""
cd "$D"
./prep_solve bl syms.txt
