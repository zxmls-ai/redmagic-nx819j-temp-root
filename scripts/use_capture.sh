#!/system/bin/sh
set -eu
D=${NX819J_DIR:?}
test "$(uname -r)" = '6.18.21-android17-5-g11fe19e75a18-ab16017504-4k'
test "$(cat /proc/sys/kernel/random/boot_id)" = "$(cat "$D/bl/boot_id.txt")"
test "$(wc -l < "$D/bl/bl_text.txt")" -gt 0
echo 'Reusing independently checked current-boot capture; original checks follow.'
