#!/bin/sh
# Owner-approved continuous diagnostics add-on. Never control vendor services.
# Fail closed; not part of the frozen D5 release manifest.
umask 077
_cfg=/customer/minieye/config/.c2m-continuous-diag
_once=/tmp/c2m-continuous-diag-start.once
_bin=/customer/c2m/c2m-diag
[ -d /customer/c2m ] && [ ! -L /customer/c2m ] || exit 0
[ -d /customer/minieye/config ] && [ ! -L /customer/minieye/config ] || exit 0
[ -d "$_cfg" ] && [ ! -L "$_cfg" ] || exit 0
[ -f "$_cfg/disabled" ] && exit 0
[ ! -L "$_cfg/disabled" ] || exit 0
[ -f "$_bin" ] && [ ! -L "$_bin" ] && [ -x "$_bin" ] || exit 0
[ ! -e "$_once" ] && [ ! -L "$_once" ] || exit 0
mkdir "$_once" 2>/dev/null || exit 0
# Logger handles its own singleton lock, card-mount validation and rotation.
# No health/calibration/startup-check script, stdin, network listener or retry loop.
"$_bin" --run </dev/null >/dev/null 2>&1 &
exit 0
