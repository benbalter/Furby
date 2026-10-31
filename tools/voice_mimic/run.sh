#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
#
# The pipeline's entry point; run2.sh does the work (see its header for options).
exec "$(dirname "$0")/run2.sh" "$@"
